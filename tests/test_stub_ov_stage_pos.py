# -*- coding: utf-8 -*-

# ==============================================================================
#   This source file is part of SBEMimage (github.com/SBEMimage)
#   (c) 2018-2026 Friedrich Miescher Institute for Biomedical Research, Basel,
#   and the SBEMimage developers.
#   This software is licensed under the terms of the MIT License.
#   See LICENSE.txt in the project root folder.
# ==============================================================================

"""Unit and integration tests for Stub Overview stage position button (feat/stub-ov-stage-pos)."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from PyQt5.QtWidgets import QApplication

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from viewport_dlg_windows import StubOVDlg


@pytest.fixture
def mock_dependencies():
    sem = MagicMock()
    sem.is_eht_on.return_value = True

    stage = MagicMock()
    stage.get_xy.return_value = (1234.6, -5678.2)
    stage.stage_move_duration.return_value = 0.5

    ovm = MagicMock()
    stub_ov = MagicMock()
    stub_ov.size = [5, 4]
    stub_ov.centre_sx_sy = [0, 0]
    stub_ov.frame_size = [1024, 768]
    stub_ov.overlap = 100
    stub_ov.pixel_size = 100
    stub_ov.tile_cycle_time.return_value = 1.0
    stub_ov.__getitem__.side_effect = lambda idx: MagicMock(sx_sy=(0, 0))
    ovm.__getitem__.side_effect = lambda key: stub_ov if key == 'stub' else MagicMock()

    acq = MagicMock()
    img_inspector = MagicMock()
    viewport_trigger = MagicMock()

    return sem, stage, ovm, acq, img_inspector, viewport_trigger


def test_stub_ov_button_initialization_and_width(mock_dependencies):
    """Verify that pushButton_get_stage_pos is initialized, text is 'Read XY',
    and dialog width remains 252 (not enlarged)."""
    sem, stage, ovm, acq, img_inspector, viewport_trigger = mock_dependencies

    dlg = StubOVDlg(
        centre_sx_sy=[0, 0],
        sem=sem,
        stage=stage,
        ovm=ovm,
        acq=acq,
        img_inspector=img_inspector,
        viewport_trigger=viewport_trigger
    )

    assert hasattr(dlg, 'pushButton_get_stage_pos')
    assert dlg.pushButton_get_stage_pos.text() == 'Read XY'
    assert dlg.width() == 252
    assert dlg.spinBox_X.value() == 0
    assert dlg.spinBox_Y.value() == 0
    dlg.close()


def test_stub_ov_get_current_stage_position(mock_dependencies):
    """Verify that clicking pushButton_get_stage_pos updates spinboxes with rounded stage coordinates."""
    sem, stage, ovm, acq, img_inspector, viewport_trigger = mock_dependencies
    stage.get_xy.return_value = (1234.6, -5678.2)

    dlg = StubOVDlg(
        centre_sx_sy=[0, 0],
        sem=sem,
        stage=stage,
        ovm=ovm,
        acq=acq,
        img_inspector=img_inspector,
        viewport_trigger=viewport_trigger
    )

    dlg.pushButton_get_stage_pos.click()

    stage.get_xy.assert_called_once()
    assert dlg.spinBox_X.value() == 1235
    assert dlg.spinBox_Y.value() == -5678
    dlg.close()


def test_stub_ov_get_current_stage_position_exception_handling(mock_dependencies):
    """Verify that exceptions during stage coordinate retrieval are handled gracefully."""
    sem, stage, ovm, acq, img_inspector, viewport_trigger = mock_dependencies
    stage.get_xy.side_effect = RuntimeError("Stage communication timeout")

    dlg = StubOVDlg(
        centre_sx_sy=[10, 20],
        sem=sem,
        stage=stage,
        ovm=ovm,
        acq=acq,
        img_inspector=img_inspector,
        viewport_trigger=viewport_trigger
    )

    with patch('viewport_dlg_windows.QMessageBox.warning') as mock_warning:
        dlg.pushButton_get_stage_pos.click()
        mock_warning.assert_called_once()
        assert "Could not read current stage position" in mock_warning.call_args[0][2]

    # Spinboxes remain unchanged on failure
    assert dlg.spinBox_X.value() == 10
    assert dlg.spinBox_Y.value() == 20
    dlg.close()
