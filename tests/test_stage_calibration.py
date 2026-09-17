# -*- coding: utf-8 -*-

# ==============================================================================
#   This source file is part of SBEMimage (github.com/SBEMimage)
#   (c) 2018-2026 Friedrich Miescher Institute for Biomedical Research, Basel,
#   and the SBEMimage developers.
#   This software is licensed under the terms of the MIT License.
#   See LICENSE.txt in the project root folder.
# ==============================================================================

"""Unit tests for Stage Calibration multi-point enhancements (feat/stage-calibration-multipoint)."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from PyQt5.QtWidgets import QApplication

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from main_controls_dlg_windows import StageCalibrationDlg
from utils import Error


@pytest.fixture(autouse=True)
def suppress_qt_dialogs(monkeypatch):
    """Prevent GUI dialogs and QMessageBoxes from popping up or blocking during tests."""
    monkeypatch.setattr('main_controls_dlg_windows.QMessageBox.warning', lambda *args, **kwargs: 0)
    monkeypatch.setattr('main_controls_dlg_windows.QMessageBox.information', lambda *args, **kwargs: 0)
    monkeypatch.setattr('main_controls_dlg_windows.QMessageBox.question', lambda *args, **kwargs: 0)
    monkeypatch.setattr(StageCalibrationDlg, 'show', lambda self: None)


@pytest.fixture
def stage_calib_fixture():
    coordinate_system = MagicMock()
    coordinate_system.stage_calibration = [1.0, 1.0, 0.0, 0.0]

    stage = MagicMock()
    stage.motor_speed_x = 100.0
    stage.motor_speed_y = 100.0
    stage.get_xy.return_value = (0.0, 0.0)
    stage.device_name.return_value = "Mock Stage"
    stage.pos_within_limits.return_value = True
    stage.error_state = Error.none
    stage.error_info = ""

    sem = MagicMock()
    sem.device_name = "Mock SEM"
    sem.simulation_mode = False
    sem.target_eht = 1.5
    sem.DWELL_TIME = [0.1, 0.2, 0.4, 0.8, 1.6]
    sem.STORE_RES = [(512, 512), (1024, 1024), (2048, 2048)]
    sem.is_eht_on.return_value = True

    base_dir = "/tmp"
    main_controls_trigger = MagicMock()
    microtome = MagicMock()
    microtome.error_state = Error.none
    microtome.error_info = ""

    return coordinate_system, stage, sem, base_dir, main_controls_trigger, microtome


def test_stage_calibration_dlg_label_calibration_radius(stage_calib_fixture):
    """Task 2.1: Verify 'Wander radius' is renamed to 'Calibration radius' in the UI."""
    cs, stage, sem, base_dir, trigger, microtome = stage_calib_fixture
    dlg = StageCalibrationDlg(cs, stage, sem, base_dir, trigger, microtome)

    assert hasattr(dlg, 'label_wander_radius')
    assert "Calibration radius" in dlg.label_wander_radius.text()
    assert "Wander" not in dlg.label_wander_radius.text()
    dlg.close()


def test_multipoint_abort_on_eht_off_at_start(stage_calib_fixture):
    """Task 2.4: Verify calibration safely aborts immediately if EHT is off."""
    cs, stage, sem, base_dir, trigger, microtome = stage_calib_fixture
    sem.is_eht_on.return_value = False
    dlg = StageCalibrationDlg(cs, stage, sem, base_dir, trigger, microtome)

    dlg.calibration_images_acq_thread_grid()

    assert dlg.calc_exception is not None
    assert "EHT" in dlg.calc_exception or "beam" in dlg.calc_exception
    stage.move_to_xy.assert_not_called()
    dlg.close()


def test_multipoint_abort_on_eht_off_during_sweep(stage_calib_fixture):
    """Task 2.4: Verify calibration aborts if EHT turns off during the acquisition sweep."""
    cs, stage, sem, base_dir, trigger, microtome = stage_calib_fixture
    # First check (start) True, second check (inside loop) False
    sem.is_eht_on.side_effect = [True, False]
    dlg = StageCalibrationDlg(cs, stage, sem, base_dir, trigger, microtome)

    with patch('main_controls_dlg_windows.sleep'):
        dlg.calibration_images_acq_thread_grid()

    assert dlg.calc_exception is not None
    assert "EHT / beam turned off" in dlg.calc_exception
    # Returned to anchor position
    assert stage.move_to_xy.call_count >= 1
    dlg.close()


def test_multipoint_abort_on_out_of_bounds(stage_calib_fixture):
    """Task 2.5: Verify calibration aborts if stage coordinates exceed limits."""
    cs, stage, sem, base_dir, trigger, microtome = stage_calib_fixture
    stage.pos_within_limits.return_value = False
    dlg = StageCalibrationDlg(cs, stage, sem, base_dir, trigger, microtome)

    with patch('main_controls_dlg_windows.sleep'):
        dlg.calibration_images_acq_thread_grid()

    assert dlg.calc_exception is not None
    assert "outside stage limits" in dlg.calc_exception
    dlg.close()


def test_multipoint_abort_on_motor_error(stage_calib_fixture):
    """Task 2.5: Verify calibration aborts if stage reports motor error."""
    cs, stage, sem, base_dir, trigger, microtome = stage_calib_fixture
    dlg = StageCalibrationDlg(cs, stage, sem, base_dir, trigger, microtome)

    def trigger_motor_error(coords):
        stage.error_state = 1
        stage.error_info = "Limit switch hit"

    stage.move_to_xy.side_effect = trigger_motor_error

    with patch('main_controls_dlg_windows.sleep'):
        dlg.calibration_images_acq_thread_grid()

    assert dlg.calc_exception is not None
    assert "Stage motor error" in dlg.calc_exception
    dlg.close()


def test_multipoint_viewport_sync(stage_calib_fixture):
    """Task 2.2: Verify UPDATE XY and DRAW VP are emitted to update viewport crosshair."""
    cs, stage, sem, base_dir, trigger, microtome = stage_calib_fixture
    dlg = StageCalibrationDlg(cs, stage, sem, base_dir, trigger, microtome)

    dlg.spinBox_gridSize.setValue(2)
    dlg.spinBox_numRuns.setValue(1)

    with patch('main_controls_dlg_windows.imread', return_value=MagicMock(shape=(100, 100), ndim=2, dtype=float, max=lambda: 0.5)):
        with patch('main_controls_dlg_windows.sleep'):
            dlg.calibration_images_acq_thread_grid()

    # Verify triggers were transmitted
    transmitted_msgs = [call[0][0] for call in trigger.transmit.call_args_list]
    assert 'UPDATE XY' in transmitted_msgs
    assert 'DRAW VP' in transmitted_msgs
    dlg.close()
