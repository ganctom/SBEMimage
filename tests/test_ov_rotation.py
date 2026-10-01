# -*- coding: utf-8 -*-

# ==============================================================================
#   This source file is part of SBEMimage (github.com/SBEMimage)
#   (c) 2018-2026 Friedrich Miescher Institute for Biomedical Research, Basel,
#   and the SBEMimage developers.
#   This software is licensed under the terms of the MIT License.
#   See LICENSE.txt in the project root folder.
# ==============================================================================

"""Unit and integration tests for Overview rotation (feat/ov-rotation)."""

import os
import sys
from configparser import ConfigParser
from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from PyQt5.QtWidgets import QApplication
app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from coordinate_system import CoordinateSystem
from sem_control import SEM
from overview_manager import Overview, OverviewManager
from acquisition import Acquisition
from main_controls_dlg_windows import OVSettingsDlg


@pytest.fixture
def test_configs():
    base_src = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src', 'default_cfg'))
    cfg = ConfigParser()
    with open(os.path.join(base_src, 'default.ini'), 'r') as f:
        cfg.read_file(f)
    syscfg = ConfigParser()
    with open(os.path.join(base_src, 'system.cfg'), 'r') as f:
        syscfg.read_file(f)
    return cfg, syscfg


@pytest.fixture
def ov_setup(test_configs):
    cfg, syscfg = test_configs
    cs = CoordinateSystem(cfg, syscfg)
    sem = SEM(cfg, syscfg)
    ovm = OverviewManager(cfg, sem, cs)
    return ovm, sem, cs, cfg


def test_overview_bounding_box_unaffected_by_rotation(ov_setup):
    """Overview bounding box returns unrotated frame extents regardless of rotation,
    preserving relative coordinate indexing for debris detection reference."""
    ovm, _, _, _ = ov_setup
    ov = ovm[0]
    ov.centre_sx_sy = [0.0, 0.0]
    width = ov.width_d()
    height = ov.height_d()

    for angle in [0.0, 45.0, 90.0, 180.0]:
        ov.rotation = angle
        t_left_x, t_left_y, b_right_x, b_right_y = ov.bounding_box()
        assert pytest.approx(t_left_x) == -width / 2.0
        assert pytest.approx(t_left_y) == -height / 2.0
        assert pytest.approx(b_right_x) == width / 2.0
        assert pytest.approx(b_right_y) == height / 2.0


def test_overview_rotation_persistence(ov_setup):
    """Overview rotation should persist correctly to and from config."""
    ovm, sem, cs, cfg = ov_setup
    ovm[0].rotation = 37.5
    ovm.save_to_cfg()

    # Re-instantiate OverviewManager from the modified cfg
    ovm_reloaded = OverviewManager(cfg, sem, cs)
    assert ovm_reloaded[0].rotation == 37.5

    # Test backward compatibility when ov_rotation is shorter than number_ov
    cfg['overviews']['number_ov'] = '2'
    cfg['overviews']['ov_rotation'] = '[15.0]'
    cfg['overviews']['ov_active'] = '[1, 1]'
    cfg['overviews']['ov_centre_sx_sy'] = '[[0, 0], [10, 10]]'
    cfg['overviews']['ov_size'] = '[[2048, 1536], [2048, 1536]]'
    cfg['overviews']['ov_size_selector'] = '[2, 2]'
    cfg['overviews']['ov_pixel_size'] = '[155.0, 155.0]'
    cfg['overviews']['ov_dwell_time'] = '[0.8, 0.8]'
    cfg['overviews']['ov_dwell_time_selector'] = '[4, 4]'
    cfg['overviews']['ov_wd_stig_xy'] = '[[0, 0, 0], [0, 0, 0]]'
    cfg['overviews']['ov_acq_interval'] = '[1, 1]'
    cfg['overviews']['ov_acq_interval_offset'] = '[0, 0]'
    cfg['overviews']['ov_viewport_images'] = '["", ""]'
    cfg['debris']['detection_area'] = '[[], []]'

    ovm_compat = OverviewManager(cfg, sem, cs)
    assert ovm_compat.number_ov == 2
    assert ovm_compat[0].rotation == 0.0
    assert ovm_compat[1].rotation == 0.0


def test_add_new_overview_rotation(ov_setup):
    """add_new_overview should accept and store the rotation parameter."""
    ovm, _, _, _ = ov_setup
    initial_count = ovm.number_ov
    ovm.add_new_overview(rotation=123.4)
    assert ovm.number_ov == initial_count + 1
    assert ovm[initial_count].rotation == 123.4
    ovm.delete_overview()


def test_acquire_overview_rotation_applied_and_reset(ov_setup):
    """acquire_overview must apply SmartSEM rotation polarity and reset to 0 in finally."""
    ovm, sem, cs, cfg = ov_setup
    ovm[0].rotation = 45.0  # SBEM angle = 45 -> SEM angle = (360 - 45) % 360 = 315

    acq = Acquisition.__new__(Acquisition)
    acq.ovm = ovm
    acq.sem = MagicMock()
    acq.stage = MagicMock()
    acq.stage.error_state = 0
    acq.error_state = 0
    acq.magc_mode = False
    acq.cfg = cfg
    acq.base_dir = '/tmp'
    acq.stack_name = 'test_stack'
    acq.slice_counter = 0
    acq.main_controls_trigger = MagicMock()
    acq.add_to_main_log = MagicMock()
    acq.img_inspector = MagicMock()
    acq.img_inspector.process_ov.return_value = (None, 128.0, 10.0, True, False, None, False)
    acq.first_ov = [False]
    acq.monitor_images = False
    acq.use_debris_detection = False
    acq.ask_user_mode = False
    acq.syscfg = {'device': {'microtome': '0'}}

    with patch('os.path.isfile', return_value=True), patch('acquisition.imwrite'):
        acq.acquire_overview(0, move_required=False)

    # Verify set_scan_rotation was called with 315, then reset to 0
    calls = acq.sem.set_scan_rotation.call_args_list
    assert len(calls) == 2
    assert calls[0][0][0] == 315.0
    assert calls[1][0][0] == 0


def test_acquire_overview_zero_rotation_no_scan_rotation_calls(ov_setup):
    """When rotation is 0, acquire_overview must NOT call set_scan_rotation."""
    ovm, sem, cs, cfg = ov_setup
    ovm[0].rotation = 0.0

    acq = Acquisition.__new__(Acquisition)
    acq.ovm = ovm
    acq.sem = MagicMock()
    acq.stage = MagicMock()
    acq.stage.error_state = 0
    acq.error_state = 0
    acq.magc_mode = False
    acq.cfg = cfg
    acq.base_dir = '/tmp'
    acq.stack_name = 'test_stack'
    acq.slice_counter = 0
    acq.main_controls_trigger = MagicMock()
    acq.add_to_main_log = MagicMock()
    acq.img_inspector = MagicMock()
    acq.img_inspector.process_ov.return_value = (None, 128.0, 10.0, True, False, None, False)
    acq.first_ov = [False]
    acq.monitor_images = False
    acq.use_debris_detection = False
    acq.ask_user_mode = False
    acq.syscfg = {'device': {'microtome': '0'}}

    with patch('os.path.isfile', return_value=True), patch('acquisition.imwrite'):
        acq.acquire_overview(0, move_required=False)

    acq.sem.set_scan_rotation.assert_not_called()


def test_acquire_overview_exception_still_resets_scan_rotation(ov_setup):
    """If an exception occurs during frame acquisition, scan rotation must still reset to 0."""
    ovm, sem, cs, cfg = ov_setup
    ovm[0].rotation = 30.0  # SEM angle = 330.0

    acq = Acquisition.__new__(Acquisition)
    acq.ovm = ovm
    acq.sem = MagicMock()
    acq.stage = MagicMock()
    acq.stage.error_state = 0
    acq.error_state = 0
    acq.magc_mode = False
    acq.cfg = cfg
    acq.base_dir = '/tmp'
    acq.stack_name = 'test_stack'
    acq.slice_counter = 0
    acq.main_controls_trigger = MagicMock()
    acq.add_to_main_log = MagicMock()

    # Simulate frame acquisition failure
    acq.sem.acquire_frame.side_effect = RuntimeError("Beam failure")

    with pytest.raises(RuntimeError):
        acq.acquire_overview(0, move_required=False)

    # set_scan_rotation must have been called with 330, and then reset to 0 in finally
    calls = acq.sem.set_scan_rotation.call_args_list
    assert len(calls) == 2
    assert calls[0][0][0] == 330.0
    assert calls[1][0][0] == 0


def test_ov_settings_dlg_inherit_rotation_and_save(ov_setup):
    """OVSettingsDlg must populate rotation, allow inheritance from grid, and save correctly."""
    ovm, sem, _, _ = ov_setup
    ovm[0].rotation = 12.0

    # Mock GridManager
    gm = MagicMock()
    gm.number_grids = 2
    gm.grid_selector_list.return_value = ['Grid 0', 'Grid 1']
    gm.__getitem__.side_effect = lambda idx: MagicMock(rotation=55.5 if idx == 0 else 78.0)

    trigger = MagicMock()
    dlg = OVSettingsDlg(ovm, sem, 0, trigger, gm=gm)

    # Verify button label and geometry
    assert dlg.label_rotation.text() == 'Rotation angle (°):'
    assert dlg.pushButton_inheritRotation.text() == 'Get rotation angle'
    assert dlg.pushButton_inheritRotation.width() == 128
    assert dlg.comboBox_inheritGrid.width() == 68

    # Initial value matches OV rotation
    assert dlg.doubleSpinBox_rotation.value() == 12.0
    assert dlg.comboBox_inheritGrid.count() == 2
    assert dlg.comboBox_inheritGrid.currentIndex() == 0

    # Click inherit button -> spinbox takes Grid 0 rotation (55.5)
    dlg.pushButton_inheritRotation.click()
    assert dlg.doubleSpinBox_rotation.value() == 55.5

    # Switch to Grid 1 and inherit -> spinbox takes Grid 1 rotation (78.0)
    dlg.comboBox_inheritGrid.setCurrentIndex(1)
    dlg.pushButton_inheritRotation.click()
    assert dlg.doubleSpinBox_rotation.value() == 78.0

    # Save settings -> ovm[0].rotation is updated to 78.0
    dlg.save_current_settings()
    assert ovm[0].rotation == 78.0
    trigger.transmit.assert_called_with('OV SETTINGS CHANGED')
    dlg.close()


def test_sem_zeiss_set_scan_rotation_order(monkeypatch):
    """Verify SEM_SmartSEM sets DP_SCAN_ROT=1 first, then AP_SCANROTATION.
    When angle is 0, only DP_SCAN_ROT=0 is set (disabling rotation) without
    calling AP_SCANROTATION (which would re-trigger SmartSEM tick mark)."""
    from sem_control_zeiss import SEM_SmartSEM

    # Instantiate SEM_SmartSEM without calling COM __init__
    sem = object.__new__(SEM_SmartSEM)
    calls = []

    def mock_sem_set(key, val, convert_variant=True):
        calls.append((key, val))
        return 0

    monkeypatch.setattr(sem, 'sem_set', mock_sem_set)
    monkeypatch.setattr('sem_control_zeiss.sleep', lambda s: None)

    # 1. Enable rotation (angle > 0): DP_SCAN_ROT must be 1 first, then AP_SCANROTATION
    sem.set_scan_rotation(45.0)
    assert calls == [('DP_SCAN_ROT', 1), ('AP_SCANROTATION', 45.0)]

    # 2. Disable rotation (angle == 0): only DP_SCAN_ROT=0 called
    calls.clear()
    sem.set_scan_rotation(0)
    assert calls == [('DP_SCAN_ROT', 0)]


def test_debris_detection_area_with_rotated_ov(ov_setup):
    """Debris detection area coordinates must be projected into the OV image
    frame, properly enclosing active tiles with no missing parts."""
    ovm, _, _, _ = ov_setup
    ov = ovm[0]
    ov.centre_sx_sy = [0.0, 0.0]
    ov.rotation = 30.0

    # Mock GridManager with 1 active grid and 1 active tile, also at 30 deg
    gm = MagicMock()
    gm.number_grids = 1
    grid = MagicMock()
    grid.active = True
    grid.active_tiles = [0]
    grid.rotation = 30.0

    # Suppose tile corners are centered at (0, 0), width 20, height 20, rotated 30 deg
    cos30 = np.cos(np.radians(30.0))
    sin30 = np.sin(np.radians(30.0))
    unrot_corners = [(-10.0, -10.0), (10.0, -10.0), (10.0, 10.0), (-10.0, 10.0)]
    rot_corners = [(x * cos30 - y * sin30, x * sin30 + y * cos30) for x, y in unrot_corners]
    grid.tile_corners.return_value = rot_corners
    gm.__getitem__.return_value = grid

    ov.update_debris_detection_area(gm, auto_detection=True, margin=0)

    # Projected into OV frame, width is 20 um centered in OV image (half_w = width_d / 2)
    half_w = ov.width_d() / 2.0
    half_h = ov.height_d() / 2.0
    expected_top_left_px = int((half_w - 10.0) * 1000.0 / ov.pixel_size)
    expected_top_left_py = int((half_h - 10.0) * 1000.0 / ov.pixel_size)
    expected_bottom_right_px = int((half_w + 10.0) * 1000.0 / ov.pixel_size)
    expected_bottom_right_py = int((half_h + 10.0) * 1000.0 / ov.pixel_size)

    assert ov.debris_detection_area == [
        expected_top_left_px, expected_top_left_py,
        expected_bottom_right_px, expected_bottom_right_py]


def test_acq_func_acquire_ov_scan_rotation():
    """Verify acq_func.acquire_ov applies scan rotation and resets in finally block."""
    import acq_func
    base_dir = '/tmp'
    selection = 0

    import utils
    sem = MagicMock()
    sem.magc_mode = False
    stage = MagicMock()
    stage.error_state = utils.Error.none

    ov = MagicMock()
    ov.active = True
    ov.centre_sx_sy = [0.0, 0.0]
    ov.wd_stig_xy = [0, 0, 0]
    ov.frame_size_selector = 0
    ov.pixel_size = 100.0
    ov.dwell_time = 0.8
    ov.rotation = 45.0

    ovm = MagicMock()
    ovm.number_ov = 1
    ovm.__getitem__.return_value = ov

    img_inspector = MagicMock()
    img_inspector.load_and_inspect.return_value = (None, None, None, False, None, False)

    main_controls_trigger = MagicMock()
    viewport_trigger = MagicMock()

    acq_func.acquire_ov(base_dir, selection, sem, stage, ovm, img_inspector,
                        main_controls_trigger, viewport_trigger)

    # (360 - 45) % 360 = 315
    sem.set_scan_rotation.assert_has_calls([
        call(315.0),
        call(0)
    ])


def test_grid_tile_corners(ov_setup):
    """Grid.tile_corners must return 4 corners matching tile_bounding_box extents."""
    from grid_manager import Grid
    _, sem, cs, _ = ov_setup

    grid = Grid(cs, sem, active=True, origin_sx_sy=[0, 0], rotation=30.0,
                size=[1, 1], overlap=0, row_shift=0, shift_margin=0,
                active_tiles=[0], frame_size=[1024, 768], frame_size_selector=0,
                pixel_size=10.0, dwell_time=0.8, dwell_time_selector=0)

    corners = grid.tile_corners(0)
    assert len(corners) == 4
    min_x, max_x, min_y, max_y = grid.tile_bounding_box(0)
    xs = [p[0] for p in corners]
    ys = [p[1] for p in corners]
    assert pytest.approx(min(xs)) == min_x
    assert pytest.approx(max(xs)) == max_x
    assert pytest.approx(min(ys)) == min_y
    assert pytest.approx(max(ys)) == max_y


def test_debris_detection_area_encloses_active_tiles_at_various_angles(ov_setup):
    """For any OV rotation angle (0, 30, 45, 90), the debris detection area
    in OV pixel coordinates must fully and tightly enclose all active tile corners."""
    ovm, _, _, _ = ov_setup
    ov = ovm[0]
    ov.centre_sx_sy = [0.0, 0.0]

    # Grid with 2 active tiles at (5.0, 5.0) and (-5.0, -5.0)
    gm = MagicMock()
    gm.number_grids = 1
    grid = MagicMock()
    grid.active = True
    grid.active_tiles = [0, 1]

    # Tile 0 corners (-10 to 0, -10 to 0), Tile 1 corners (0 to 10, 0 to 10)
    t0_corners = [(-10.0, -10.0), (0.0, -10.0), (0.0, 0.0), (-10.0, 0.0)]
    t1_corners = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    grid.tile_corners.side_effect = lambda idx: t0_corners if idx == 0 else t1_corners
    gm.__getitem__.return_value = grid

    for angle in [0.0, 15.0, 30.0, 45.0, 90.0, 180.0]:
        ov.rotation = angle
        ov.update_debris_detection_area(gm, auto_detection=True, margin=0)

        # In OV image frame:
        cos_th = np.cos(np.radians(angle))
        sin_th = np.sin(np.radians(angle))
        half_w = ov.width_d() / 2.0
        half_h = ov.height_d() / 2.0

        all_corners = t0_corners + t1_corners
        for x, y in all_corners:
            u = (x * cos_th + y * sin_th) + half_w
            v = (-x * sin_th + y * cos_th) + half_h
            px = int(u * 1000.0 / ov.pixel_size)
            py = int(v * 1000.0 / ov.pixel_size)

            # Every tile corner must be within the debris detection area (within 1 px rounding tolerance)
            assert ov.debris_detection_area[0] <= px + 1
            assert ov.debris_detection_area[1] <= py + 1
            assert ov.debris_detection_area[2] >= px - 1
            assert ov.debris_detection_area[3] >= py - 1


def test_overview_vp_file_path_reloads_fresh_image(ov_setup, tmp_path):
    """Setting vp_file_path must reload the newly saved image from disk,
    not return a stale cached QPixmap."""
    from PyQt5.QtGui import QImage, QColor
    ovm, _, _, _ = ov_setup
    ov = ovm[0]
    img_file = str(tmp_path / 'OV000.bmp')

    # Save initial red image and load into OV
    img_red = QImage(16, 16, QImage.Format_RGB32)
    img_red.fill(QColor(255, 0, 0))
    img_red.save(img_file)
    ov.vp_file_path = img_file
    assert ov.image.toImage().pixelColor(0, 0).name() == '#ff0000'

    # Overwrite on disk with blue image
    img_blue = QImage(16, 16, QImage.Format_RGB32)
    img_blue.fill(QColor(0, 0, 255))
    img_blue.save(img_file)

    # Re-assign vp_file_path with same path
    ov.vp_file_path = img_file
    assert ov.image.toImage().pixelColor(0, 0).name() == '#0000ff'




