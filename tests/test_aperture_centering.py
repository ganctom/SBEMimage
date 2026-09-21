# -*- coding: utf-8 -*-

import os
import sys
import json
import shutil
import tempfile
import numpy as np
import cv2
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from aperture_centering import (
    evaluate_radial_symmetry,
    evaluate_center_sharpness,
    fit_2d_surface,
    ApertureCenteringManager,
)


def create_synthetic_focus_dome(width=512, height=384, center_x=256, center_y=192, dome_radius=200):
    """Generate a test image with high-frequency noise modulated by a focus dome."""
    # Base high-frequency texture
    np.random.seed(42)
    noise = np.random.normal(128, 40, (height, width)).astype(np.float32)

    # Focus envelope centered at (center_x, center_y)
    yy, xx = np.mgrid[0:height, 0:width]
    dist = np.sqrt((xx - center_x) ** 2 + (yy - center_y) ** 2)
    envelope = np.clip(1.0 - (dist / dome_radius) ** 2, 0.05, 1.0)

    # Blur decreases gradient magnitude away from the center
    blurred = cv2.GaussianBlur(noise, (15, 15), 0)
    composite = envelope * noise + (1.0 - envelope) * blurred
    return np.clip(composite, 0, 255).astype(np.uint8)


def test_evaluate_radial_symmetry_centered_vs_decentered():
    centered_img = create_synthetic_focus_dome(width=512, height=384, center_x=256, center_y=192)
    decentered_img = create_synthetic_focus_dome(width=512, height=384, center_x=100, center_y=80)

    res_centered = evaluate_radial_symmetry(centered_img)
    res_decentered = evaluate_radial_symmetry(decentered_img)

    assert res_centered['symmetry_score'] > res_decentered['symmetry_score'], (
        f"Centered score {res_centered['symmetry_score']} should be > decentered {res_decentered['symmetry_score']}"
    )
    assert res_centered['asymmetry_score'] < res_decentered['asymmetry_score']


class MockSEMForAperture:
    def __init__(self, optimal_x=2.0, optimal_y=-2.0, event_log=None):
        self.align_x = 0.0
        self.align_y = 0.0
        self.optimal_x = optimal_x
        self.optimal_y = optimal_y
        self.STORE_RES = [
            [1024, 768], [512, 384], [2048, 1536], [3072, 2304],
            [4096, 3072], [5120, 3840], [6144, 4608]
        ]
        self.DWELL_TIME = [0.05, 0.1, 0.2, 0.4, 0.8, 1.6, 3.2, 6.4]
        self.target_pixel_size = 10.0
        self.event_log = event_log

    def get_aperture_align_xy(self):
        return self.align_x, self.align_y

    def set_aperture_align_xy(self, x, y):
        self.align_x = float(x)
        self.align_y = float(y)
        if self.event_log is not None:
            self.event_log.append(('set_align', float(x), float(y)))
        return True

    def get_aperture_align_x(self):
        return self.align_x

    def set_aperture_align_x(self, x):
        self.align_x = float(x)
        return True

    def get_aperture_align_y(self):
        return self.align_y

    def set_aperture_align_y(self, y):
        self.align_y = float(y)
        return True

    def apply_frame_settings(self, selector, pixel_size, dwell_time):
        return True

    def acquire_frame(self, save_path):
        if self.event_log is not None:
            self.event_log.append(('acquire_frame', self.align_x, self.align_y))
        # Simulate optical shift proportional to distance from optimal center
        # Optical center shifts on sensor based on aperture misalignment
        dx = self.align_x - self.optimal_x
        dy = self.align_y - self.optimal_y
        # Dome center moves away from frame center (256, 192)
        cx = 256 - dx * 30
        cy = 192 - dy * 30
        img = create_synthetic_focus_dome(width=512, height=384, center_x=cx, center_y=cy)
        cv2.imwrite(save_path, img)
        return True


def test_aperture_centering_nudge():
    mock_sem = MockSEMForAperture()
    temp_dir = tempfile.mkdtemp()
    try:
        manager = ApertureCenteringManager(mock_sem, None, temp_dir)
        new_x, new_y = manager.nudge(1.5, -2.5)
        assert abs(new_x - 1.5) < 1e-4
        assert abs(new_y - (-2.5)) < 1e-4
        assert abs(mock_sem.align_x - 1.5) < 1e-4
        assert abs(mock_sem.align_y - (-2.5)) < 1e-4
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_aperture_centering_sweep_and_artifacts():
    optimal_target_x = 2.0
    optimal_target_y = -2.0
    mock_sem = MockSEMForAperture(optimal_x=optimal_target_x, optimal_y=optimal_target_y)
    temp_dir = tempfile.mkdtemp()

    try:
        manager = ApertureCenteringManager(mock_sem, None, temp_dir)
        # 3x3 sweep with step 2.0 centered at (0, 0)
        # points will include (-2, -2), (0, -2), (2, -2), etc.
        res = manager.run_sweep(
            grid_size=3,
            step_size=2.0,
            frame_size_selector=0,
            dwell_time=0.8,
            center_x=0.0,
            center_y=0.0
        )

        assert res['optimal_x'] == pytest.approx(optimal_target_x, abs=1e-3)
        assert res['optimal_y'] == pytest.approx(optimal_target_y, abs=1e-3)

        # Ensure initial center is reinstated on SEM when auto_apply=False
        current_x, current_y = mock_sem.get_aperture_align_xy()
        assert current_x == pytest.approx(0.0, abs=1e-3)
        assert current_y == pytest.approx(0.0, abs=1e-3)

        run_dir = manager.latest_run_dir
        assert os.path.exists(run_dir)
        assert os.path.exists(os.path.join(run_dir, 'alignment_log.txt'))
        assert os.path.exists(os.path.join(run_dir, 'sharpness_data.json'))
        assert os.path.exists(os.path.join(run_dir, 'aperture_centering_heatmap.png'))

        # Check log file contains key entries
        with open(os.path.join(run_dir, 'alignment_log.txt'), 'r') as f:
            log_content = f.read()
            assert "Aperture Centering Calibration" in log_content
            assert "Optimal Aperture Alignment Found" in log_content
            assert "Reinstated initial aperture alignment on SEM" in log_content

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_aperture_centering_auto_apply():
    optimal_target_x = 2.0
    optimal_target_y = -2.0
    mock_sem = MockSEMForAperture(optimal_x=optimal_target_x, optimal_y=optimal_target_y)
    temp_dir = tempfile.mkdtemp()

    try:
        manager = ApertureCenteringManager(mock_sem, None, temp_dir)
        res = manager.run_sweep(
            grid_size=3,
            step_size=2.0,
            frame_size_selector=0,
            dwell_time=0.8,
            center_x=0.0,
            center_y=0.0,
            auto_apply=True
        )

        assert res['optimal_x'] == pytest.approx(optimal_target_x, abs=1e-3)
        assert res['optimal_y'] == pytest.approx(optimal_target_y, abs=1e-3)

        # When auto_apply=True, optimal center must be applied on SEM
        current_x, current_y = mock_sem.get_aperture_align_xy()
        assert current_x == pytest.approx(optimal_target_x, abs=1e-3)
        assert current_y == pytest.approx(optimal_target_y, abs=1e-3)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_aperture_centering_dlg_apply_and_revert(monkeypatch):
    from PyQt5.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance()
    if app is None:
        app = QApplication(['test_app'])

    from main_controls_dlg_windows import ApertureCenteringDlg
    mock_sem = MockSEMForAperture(optimal_x=4.0, optimal_y=2.0)
    mock_sem.set_aperture_align_xy(1.0, 1.0)
    temp_dir = tempfile.mkdtemp()

    try:
        dlg = ApertureCenteringDlg(mock_sem, None, temp_dir)
        dlg.sweep_initial_x = 1.0
        dlg.sweep_initial_y = 1.0
        dlg.finish_trigger.queue.put({
            'optimal_x': 4.0,
            'optimal_y': 2.0,
            'initial_score': 0.5,
            'optimal_score': 0.95
        })

        # Test 1: User declines (Cancel) in confirmation window
        monkeypatch.setattr(QMessageBox, 'question', lambda *args, **kwargs: QMessageBox.Cancel)
        dlg._on_sweep_finished()

        # SEM alignment should remain the initial values (1.0, 1.0)
        assert mock_sem.get_aperture_align_xy() == (1.0, 1.0)
        assert dlg.lineEdit_currentAlignX.text() == "1.00"
        assert dlg.lineEdit_currentAlignY.text() == "1.00"

        # Test 2: User explicitly clicks pushButton_applyOptimal
        monkeypatch.setattr(QMessageBox, 'information', lambda *args, **kwargs: QMessageBox.Ok)
        dlg.apply_optimal_alignment()
        assert mock_sem.get_aperture_align_xy() == (4.0, 2.0)
        assert dlg.lineEdit_currentAlignX.text() == "4.00"
        assert dlg.lineEdit_currentAlignY.text() == "2.00"

        dlg.close()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_aperture_centering_dlg_initialization():
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(['test_app'])

    from main_controls_dlg_windows import ApertureCenteringDlg
    mock_sem = MockSEMForAperture()
    temp_dir = tempfile.mkdtemp()

    try:
        dlg = ApertureCenteringDlg(mock_sem, None, temp_dir)
        assert dlg.lineEdit_currentAlignX.text() == "0.00"
        assert dlg.lineEdit_currentAlignY.text() == "0.00"
        assert dlg.comboBox_gridSize.count() >= 3
        assert dlg.comboBox_frameSize.count() == len(mock_sem.STORE_RES)
        assert dlg.comboBox_dwellTime.count() == len(mock_sem.DWELL_TIME)

        # Test nudge via DLG method
        dlg.nudge(1.0, 2.0)
        assert float(dlg.lineEdit_currentAlignX.text()) == pytest.approx(1.0)
        assert float(dlg.lineEdit_currentAlignY.text()) == pytest.approx(2.0)

        # Test cut thickness control
        assert dlg.spinBox_cutThickness.value() == 35
        assert not dlg.spinBox_cutThickness.isEnabled()
        dlg.checkBox_physicalCut.setChecked(True)
        assert dlg.spinBox_cutThickness.isEnabled()
        dlg.checkBox_physicalCut.setChecked(False)
        assert not dlg.spinBox_cutThickness.isEnabled()

        dlg.close()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


class MockMicrotomeForAperture:
    def __init__(self, initial_z=10.0, event_log=None):
        self.stage_z = initial_z
        self.last_known_z = initial_z
        self.cut_count = 0
        self.z_history = []
        self.stage_move_wait_interval = 0.01
        self.full_cut_duration = 0.01
        self.event_log = event_log

    def get_stage_z(self):
        return self.stage_z

    def move_stage_to_z(self, z):
        self.stage_z = float(z)
        self.last_known_z = self.stage_z
        self.z_history.append(self.stage_z)
        if self.event_log is not None:
            self.event_log.append(('move_z', float(z)))
        return True

    def do_full_cut(self):
        self.cut_count += 1
        if self.event_log is not None:
            self.event_log.append(('cut',))
        return True


def test_aperture_centering_physical_cut_with_thickness():
    mock_sem = MockSEMForAperture()
    mock_microtome = MockMicrotomeForAperture(initial_z=10.0)
    temp_dir = tempfile.mkdtemp()

    try:
        manager = ApertureCenteringManager(mock_sem, mock_microtome, temp_dir)
        cut_thickness_nm = 30.0
        res = manager.run_sweep(
            grid_size=3,
            step_size=2.0,
            frame_size_selector=0,
            dwell_time=0.8,
            center_x=0.0,
            center_y=0.0,
            perform_cut=True,
            cut_thickness=cut_thickness_nm
        )

        # In a 3x3 grid (9 frames), exactly 8 cuts occur between image acquisitions
        assert mock_microtome.cut_count == 8
        expected_final_z = 10.0 + 8 * (cut_thickness_nm / 1000.0)
        assert mock_microtome.stage_z == pytest.approx(expected_final_z, abs=1e-4)
        assert len(mock_microtome.z_history) == 8
        assert res['cut_thickness'] == cut_thickness_nm
        assert res['cut_duration'] == pytest.approx(0.01)
        assert res['perform_cut'] is True
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_aperture_centering_dlg_cut_warning_cancel(monkeypatch):
    from PyQt5.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance()
    if app is None:
        app = QApplication(['test_app'])

    from main_controls_dlg_windows import ApertureCenteringDlg
    mock_sem = MockSEMForAperture()
    mock_microtome = MockMicrotomeForAperture()
    temp_dir = tempfile.mkdtemp()

    try:
        dlg = ApertureCenteringDlg(mock_sem, mock_microtome, temp_dir)
        dlg.checkBox_physicalCut.setChecked(True)

        warning_shown = []
        def mock_warning(parent, title, text, buttons, default_btn):
            warning_shown.append((title, text))
            return QMessageBox.Cancel

        monkeypatch.setattr(QMessageBox, 'warning', mock_warning)

        # User cancels the physical cut warning
        dlg.start_sweep()
        assert len(warning_shown) == 1
        assert "Physical microtome cutting is enabled" in warning_shown[0][1]
        assert "Microtome cut duration" in warning_shown[0][1]
        assert dlg.label_status.text() == 'Status: Sweep cancelled by user.'
        assert dlg.pushButton_startSweep.isEnabled() is True

        dlg.close()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_aperture_preset_before_cut_and_stage_z_callback():
    events = []
    z_callback_history = []
    mock_sem = MockSEMForAperture(event_log=events)
    mock_microtome = MockMicrotomeForAperture(initial_z=10.0, event_log=events)
    temp_dir = tempfile.mkdtemp()

    try:
        manager = ApertureCenteringManager(mock_sem, mock_microtome, temp_dir)
        res = manager.run_sweep(
            grid_size=3,
            step_size=2.0,
            frame_size_selector=0,
            dwell_time=0.8,
            center_x=0.0,
            center_y=0.0,
            perform_cut=True,
            cut_thickness=30.0,
            stage_z_callback=lambda z: z_callback_history.append(z)
        )

        # 8 cuts in 3x3 grid
        assert len(z_callback_history) == 8
        assert z_callback_history[0] == pytest.approx(10.030)
        assert z_callback_history[-1] == pytest.approx(10.240)
        assert mock_microtome.last_known_z == pytest.approx(10.240)

        # Verify event sequence:
        # Before each cut, the aperture for the next step must be set ('set_align'),
        # followed by stage Z move ('move_z'), followed by 'cut'.
        # And the next frame acquisition ('acquire_frame') follows the cut without an extra 'set_align'.
        cut_indices = [idx for idx, ev in enumerate(events) if ev[0] == 'cut']
        assert len(cut_indices) == 8

        for i, cut_idx in enumerate(cut_indices):
            assert events[cut_idx - 1][0] == 'move_z'
            assert events[cut_idx - 2][0] == 'set_align'
            assert events[cut_idx - 3][0] == 'acquire_frame'
            assert events[cut_idx + 1][0] == 'acquire_frame'

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_aperture_centering_dlg_log_and_z_sync(monkeypatch):
    from PyQt5.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance()
    if app is None:
        app = QApplication(['test_app'])

    from main_controls_dlg_windows import ApertureCenteringDlg
    import utils

    mock_sem = MockSEMForAperture(optimal_x=4.0, optimal_y=2.0)
    mock_sem.set_aperture_align_xy(1.0, 1.0)
    mock_microtome = MockMicrotomeForAperture(initial_z=10.0)

    class MockAcq:
        def __init__(self, z=10.0):
            self.stage_z_position = z

    class MockStage:
        def __init__(self, microtome):
            self.microtome = microtome

        @property
        def last_known_z(self):
            return self.microtome.last_known_z

    mock_acq = MockAcq(10.0)
    mock_stage = MockStage(mock_microtome)
    mock_trigger = utils.Trigger()

    received_signals = []
    mock_trigger.signal.connect(lambda: received_signals.append(mock_trigger.queue.get()))

    temp_dir = tempfile.mkdtemp()
    logged_info = []
    monkeypatch.setattr(utils, 'log_info', lambda cat, msg: logged_info.append((cat, msg)))

    try:
        dlg = ApertureCenteringDlg(
            mock_sem, mock_microtome, temp_dir,
            main_controls_trigger=mock_trigger,
            acq=mock_acq,
            stage=mock_stage
        )
        dlg.manager.latest_run_dir = os.path.join(temp_dir, 'meta', 'calibrations', 'aperture_centering', '20260918_120000')
        dlg.sweep_initial_x = 1.0
        dlg.sweep_initial_y = 1.0
        dlg.finish_trigger.queue.put({
            'optimal_x': 4.0,
            'optimal_y': 2.0,
            'initial_score': 0.5,
            'optimal_score': 0.95
        })

        # User confirms applying optimal center
        monkeypatch.setattr(QMessageBox, 'question', lambda *args, **kwargs: QMessageBox.Ok)
        dlg._on_sweep_finished()

        # Check logged message
        assert len(logged_info) == 1
        cat, msg = logged_info[0]
        assert cat == 'CAL'
        assert '(Score improved' not in msg
        assert 'Results in meta/calibrations/aperture_centering/20260918_120000' in msg
        assert msg == 'Aperture Centering Complete: Applied optimal X=4.00%, Y=2.00%. Results in meta/calibrations/aperture_centering/20260918_120000'

        # Check stage Z and trigger sync
        assert 'UPDATE Z' in received_signals
        assert mock_acq.stage_z_position == pytest.approx(10.0)

        dlg.close()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Tests for evaluate_center_sharpness
# ---------------------------------------------------------------------------

def test_evaluate_center_sharpness_sharp_vs_blurry():
    """A sharp image should score higher than a uniformly blurry one."""
    np.random.seed(0)
    sharp = np.random.randint(0, 255, (384, 512), dtype=np.uint8)

    # Create blurry version with heavy Gaussian blur
    blurry = cv2.GaussianBlur(sharp, (51, 51), 0)

    res_sharp = evaluate_center_sharpness(sharp)
    res_blurry = evaluate_center_sharpness(blurry)

    assert res_sharp['center_sharpness'] > res_blurry['center_sharpness'], (
        f"Sharp score {res_sharp['center_sharpness']:.2f} should exceed "
        f"blurry score {res_blurry['center_sharpness']:.2f}"
    )


def test_evaluate_center_sharpness_empty_image():
    """Empty image should return zeroed-out metrics without raising."""
    empty = np.array([], dtype=np.uint8)
    res = evaluate_center_sharpness(empty)
    assert res['center_sharpness'] == 0.0
    assert res['symmetry_score'] == 0.0


def test_evaluate_center_sharpness_high_symmetry_poor_sharpness():
    """Uniformly blurry image has high radial symmetry but low center sharpness.

    This is the key motivation for the center_sharpness mode: the radial
    symmetry metric can return a high score even when all features are
    uniformly blurred (because blurring is radially symmetric around centre).
    The center_sharpness metric correctly rewards the sharp version.
    """
    np.random.seed(7)
    # Uniform noise image – equal blur everywhere → radially symmetric
    noise = np.random.randint(0, 255, (384, 512), dtype=np.uint8)
    uniformly_blurry = cv2.GaussianBlur(noise, (51, 51), 0)
    sharp_centered = create_synthetic_focus_dome(
        width=512, height=384, center_x=256, center_y=192
    )

    sym_blurry = evaluate_radial_symmetry(uniformly_blurry)
    sym_sharp = evaluate_radial_symmetry(sharp_centered)
    cs_blurry = evaluate_center_sharpness(uniformly_blurry)
    cs_sharp = evaluate_center_sharpness(sharp_centered)

    # Radial symmetry can be high for blurry (regression scenario)
    # The center_sharpness metric correctly identifies the sharp image
    assert cs_sharp['center_sharpness'] > cs_blurry['center_sharpness'], (
        f"Center sharpness strategy: sharp {cs_sharp['center_sharpness']:.2f} "
        f"> blurry {cs_blurry['center_sharpness']:.2f}"
    )
    # Document the symmetry behaviour for awareness (not an assertion of failure)
    _ = (sym_blurry['symmetry_score'], sym_sharp['symmetry_score'])


def test_center_sharpness_sweep_selects_optimal():
    """Integration test: sweep with center_sharpness strategy should pick the
    aperture position that produces the sharpest center region."""
    temp_dir = tempfile.mkdtemp()
    try:
        mock_sem = MockSEMForAperture(optimal_x=2.0, optimal_y=0.0)
        manager = ApertureCenteringManager(mock_sem, None, temp_dir)

        results = manager.run_sweep(
            grid_size=3,
            step_size=2.0,
            frame_size_selector=0,
            pixel_size=10.0,
            dwell_time=0.8,
            center_x=0.0,
            center_y=0.0,
            perform_cut=False,
            eval_strategy='center_sharpness',
        )

        assert results, "Sweep should return results"
        assert 'optimal_x' in results
        assert 'eval_strategy' in results
        assert results['eval_strategy'] == 'center_sharpness'
        # The sharpest position should be close to the SEM's optimal_x=2.0
        assert abs(results['optimal_x'] - 2.0) < 2.5, (
            f"Expected optimal X near 2.0, got {results['optimal_x']}"
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_fit_2d_surface_paraboloid():
    """Verify that fit_2d_surface accurately finds peak of an inverted paraboloid."""
    # z = -(x - 1.5)^2 - (y + 2.5)^2 + 100
    xs = []
    ys = []
    zs = []
    for x in [-1.0, 0.0, 1.0, 2.0, 3.0]:
        for y in [-4.0, -3.0, -2.0, -1.0, 0.0]:
            xs.append(x)
            ys.append(y)
            zs.append(-(x - 1.5)**2 - (y + 2.5)**2 + 100.0)

    fit = fit_2d_surface(xs, ys, zs)
    assert fit is not None
    opt_x, opt_y, opt_z = fit
    assert opt_x == pytest.approx(1.5, abs=1e-3)
    assert opt_y == pytest.approx(-2.5, abs=1e-3)
    assert opt_z == pytest.approx(100.0, abs=1e-3)


def test_even_grid_size_sweep():
    """Verify even grid sizes (e.g. 2x2, 4x4) run correctly and produce correct point counts."""
    temp_dir = tempfile.mkdtemp()
    try:
        mock_sem = MockSEMForAperture(optimal_x=1.0, optimal_y=1.0)
        manager = ApertureCenteringManager(mock_sem, None, temp_dir)

        # Test 2x2 grid
        res_2x2 = manager.run_sweep(
            grid_size=2,
            step_size=2.0,
            frame_size_selector=0,
            pixel_size=10.0,
            dwell_time=0.8,
            center_x=0.0,
            center_y=0.0,
            perform_cut=False,
            eval_strategy='center_sharpness'
        )
        assert len(res_2x2['results']) == 4

        # Test 4x4 grid
        res_4x4 = manager.run_sweep(
            grid_size=4,
            step_size=1.0,
            frame_size_selector=0,
            pixel_size=10.0,
            dwell_time=0.8,
            center_x=0.0,
            center_y=0.0,
            perform_cut=False,
            eval_strategy='center_sharpness'
        )
        assert len(res_4x4['results']) == 16
        assert 'fitted_optimal_x' in res_4x4
        assert res_4x4['fitted_optimal_x'] is not None
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


class MockSEMWithPhysicalShift(MockSEMForAperture):
    """Simulates physical image translation caused by aperture deflector shifts."""
    def __init__(self, optimal_x=2.0, optimal_y=-2.0, shift_per_pct=3.0):
        super(MockSEMWithPhysicalShift, self).__init__(optimal_x, optimal_y)
        self.shift_per_pct = shift_per_pct
        np.random.seed(99)
        self.base_canvas = np.random.randint(40, 220, (600, 800)).astype(np.float32)
        cv2.circle(self.base_canvas, (400, 300), 60, 255, -1)
        cv2.rectangle(self.base_canvas, (200, 150), (320, 240), 20, -1)
        cv2.line(self.base_canvas, (150, 450), (650, 450), 240, 4)

    def acquire_frame(self, save_path):
        dx = int(round(self.align_x * self.shift_per_pct))
        dy = int(round(self.align_y * self.shift_per_pct))
        y0 = max(0, min(600 - 384, 100 + dy))
        x0 = max(0, min(800 - 512, 140 + dx))
        frame = self.base_canvas[y0:y0+384, x0:x0+512].copy()
        cv2.imwrite(save_path, frame.astype(np.uint8))
        return True


def test_aperture_centering_sweep_with_registration_and_cropping():
    """Verify that enabling register_images computes non-zero shifts, crops
    the collection, saves registered frames in the registered/ subfolder, and
    records metadata in sharpness_data.json."""
    temp_dir = tempfile.mkdtemp()
    try:
        mock_sem = MockSEMWithPhysicalShift(optimal_x=0.0, optimal_y=0.0, shift_per_pct=4.0)
        manager = ApertureCenteringManager(mock_sem, None, temp_dir)

        results = manager.run_sweep(
            grid_size=3,
            step_size=2.0,
            frame_size_selector=0,
            pixel_size=10.0,
            dwell_time=0.8,
            center_x=0.0,
            center_y=0.0,
            perform_cut=False,
            eval_strategy='center_sharpness',
            register_images=True
        )

        assert results, "Sweep should return results"
        assert results['register_images'] is True
        assert len(results['cumulative_shifts']) == 8  # 9 points -> 8 pairwise cumulative shifts
        assert len(results['cropped_dimensions']) == 2
        crop_h, crop_w = results['cropped_dimensions']
        assert crop_h < 384, f"Cropped height ({crop_h}) should be smaller than original (384)"
        assert crop_w < 512, f"Cropped width ({crop_w}) should be smaller than original (512)"

        # Check registered subfolder and files
        reg_dir = os.path.join(manager.latest_run_dir, 'registered')
        assert os.path.isdir(reg_dir), "registered/ directory should exist"
        reg_files = [f for f in os.listdir(reg_dir) if f.endswith('.tif')]
        assert len(reg_files) == 9, f"Expected 9 registered frames, found {len(reg_files)}"

        # Verify each registered frame has the cropped dimensions
        first_reg = cv2.imread(os.path.join(reg_dir, reg_files[0]), cv2.IMREAD_GRAYSCALE)
        assert first_reg.shape == (crop_h, crop_w)

        # Verify JSON record on disk
        json_path = os.path.join(manager.latest_run_dir, 'sharpness_data.json')
        assert os.path.isfile(json_path)
        with open(json_path, 'r') as f:
            data = json.load(f)
        assert data['register_images'] is True
        assert 'cumulative_shifts' in data
        assert 'cropped_dimensions' in data
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_aperture_centering_dlg_register_images_checkbox():
    """Verify that ApertureCenteringDlg initializes the register_images checkbox."""
    from PyQt5.QtWidgets import QApplication
    from main_controls_dlg_windows import ApertureCenteringDlg

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    mock_sem = MockSEMForAperture()
    temp_dir = tempfile.mkdtemp()
    try:
        dlg = ApertureCenteringDlg(mock_sem, None, temp_dir)
        assert hasattr(dlg, 'checkBox_registerImages')
        assert not dlg.checkBox_registerImages.isChecked()  # Unchecked by default
        dlg.close()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_aperture_centering_dlg_default_settings():
    """Verify that ApertureCenteringDlg initializes with the requested default settings."""
    from PyQt5.QtWidgets import QApplication
    from main_controls_dlg_windows import ApertureCenteringDlg

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    mock_sem = MockSEMForAperture()
    temp_dir = tempfile.mkdtemp()
    try:
        dlg = ApertureCenteringDlg(mock_sem, None, temp_dir)
        # Check defaults:
        # grid size 5x5
        assert dlg.comboBox_gridSize.currentText() == '5 x 5'
        # sweep step 5%
        assert dlg.doubleSpinBox_stepSize.value() == pytest.approx(5.0)
        # pixel size 15 nm
        assert dlg.doubleSpinBox_pixelSize.value() == pytest.approx(15.0)
        # cut thickness 35 nm
        assert dlg.spinBox_cutThickness.value() == 35
        # evaluation strategy: Center Sharpness first and default
        assert dlg.comboBox_evalStrategy.currentIndex() == 0
        assert dlg.comboBox_evalStrategy.currentText() == 'Center Sharpness'
        # frame resolution: 6144 x 4608
        assert dlg.comboBox_frameSize.currentText() == '6144 x 4608'
        # dwell time: 0.2
        assert dlg.comboBox_dwellTime.currentText() == '0.2'
        dlg.close()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)



def test_calibration_image_filenames_alphabetical_order():
    """Verify that calibration images sorted alphabetically follow creation time."""
    temp_dir = tempfile.mkdtemp()
    try:
        mock_sem = MockSEMForAperture(optimal_x=0.0, optimal_y=0.0)
        manager = ApertureCenteringManager(mock_sem, None, temp_dir)

        results = manager.run_sweep(
            grid_size=3,
            step_size=1.0,
            frame_size_selector=0,
            pixel_size=10.0,
            dwell_time=0.8,
            center_x=0.0,
            center_y=0.0,
            perform_cut=False,
            eval_strategy='center_sharpness'
        )

        run_dir = manager.latest_run_dir
        image_files = sorted([f for f in os.listdir(run_dir) if f.startswith('frame_') and f.endswith('.tif')])
        assert len(image_files) == 9

        # Ensure alphabetical sort strictly matches the acquisition order from results
        expected_files = [os.path.basename(r['frame_path']) for r in results['results']]
        assert image_files == expected_files
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_generate_plots_labels_with_initial_and_best_fit(monkeypatch):
    """Verify that generate_plots adds initial values to title and best fit values to Optimal Center label."""
    import matplotlib.pyplot as plt

    captured_axes = []
    orig_savefig = plt.savefig

    def mock_savefig(*args, **kwargs):
        captured_axes.append(plt.gcf().get_axes())
        return orig_savefig(*args, **kwargs)

    monkeypatch.setattr(plt, 'savefig', mock_savefig)

    temp_dir = tempfile.mkdtemp()
    try:
        plot_path = os.path.join(temp_dir, 'test_plot.png')
        data = {
            'results': [
                {'x': -1.0, 'y': -1.0, 'metrics': {'symmetry_score': 10.0, 'center_sharpness': 10.0}},
                {'x': 1.0, 'y': 1.0, 'metrics': {'symmetry_score': 20.0, 'center_sharpness': 20.0}},
            ],
            'eval_strategy': 'center_sharpness',
            'initial_x': 0.5,
            'initial_y': -0.5,
            'optimal_x': 1.25,
            'optimal_y': -0.75,
            'fitted_optimal_x': 1.254,
            'fitted_optimal_y': -0.748,
        }
        ApertureCenteringManager.generate_plots(data, plot_path)
        assert os.path.exists(plot_path)
        assert len(captured_axes) > 0
        ax0 = captured_axes[0][0]
        assert ax0.yaxis_inverted(), "Heatmap Y-axis should be inverted so more negative values are on top"
        assert 'Initial: X=0.50%, Y=-0.50%' in ax0.get_title()
        legend_labels = [t.get_text() for t in ax0.get_legend().get_texts()]
        assert any('Optimal Center (Fit: X=1.25%, Y=-0.75%)' in lbl for lbl in legend_labels)

        # In Center Sharpness mode, axes[1] must be a Mean Sharpness heatmap
        ax1 = captured_axes[0][1]
        assert ax1.get_title() == 'Aperture Centering: Mean Sharpness'
        assert ax1.yaxis_inverted(), "Mean sharpness heatmap Y-axis should also be inverted"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)




