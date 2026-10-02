# -*- coding: utf-8 -*-

# ==============================================================================
#   This source file is part of SBEMimage (github.com/SBEMimage)
#   (c) 2018-2026 Friedrich Miescher Institute for Biomedical Research, Basel,
#   and the SBEMimage developers.
#   This software is licensed under the terms of the MIT License.
#   See LICENSE.txt in the project root folder.
# ==============================================================================

"""Unit and integration tests for focus/stig transfer from grid to overview (feat/focus-stig-to-ov)."""

import os
import sys
from configparser import ConfigParser
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from PyQt5.QtWidgets import QApplication
app = QApplication.instance()
if app is None:
    app = QApplication(['sbemimage_test'])

from coordinate_system import CoordinateSystem
from sem_control import SEM
from grid_manager import GridManager
from overview_manager import OverviewManager


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
def test_setup(test_configs):
    cfg, syscfg = test_configs
    cs = CoordinateSystem(cfg, syscfg)
    sem = SEM(cfg, syscfg)
    gm = GridManager(cfg, sem, cs)
    ovm = OverviewManager(cfg, sem, cs)
    return gm, ovm


@pytest.fixture
def grid_manager_setup(test_setup):
    gm, _ = test_setup
    return gm


def test_get_first_active_tile_index(grid_manager_setup):
    gm = grid_manager_setup
    assert gm.number_grids >= 1
    # Grid 0 by default has tiles
    grid = gm[0]
    grid.deactivate_all_tiles()
    assert gm.get_first_active_tile_index(0) is None

    # Activate tile 2 only
    grid.active_tiles = [2]
    assert gm.get_first_active_tile_index(0) == 2

    # Activate tiles 4 and 1 -> first active should be min index (1)
    grid.active_tiles = [4, 1]
    assert gm.get_first_active_tile_index(0) == 1

    # Out of range grid index
    assert gm.get_first_active_tile_index(999) is None
    assert gm.get_first_active_tile_index(-1) is None


def test_get_first_active_tile_wd_stig_valid(grid_manager_setup):
    gm = grid_manager_setup
    grid = gm[0]
    grid.active_tiles = [0]
    grid[0].wd = 0.0055  # 5.5 mm in meters
    grid[0].stig_xy = (-0.12, 0.34)

    res = gm.get_first_active_tile_wd_stig(0)
    assert res is not None
    wd, stig_xy = res
    assert wd == pytest.approx(0.0055)
    assert stig_xy[0] == pytest.approx(-0.12)
    assert stig_xy[1] == pytest.approx(0.34)


def test_get_first_active_tile_wd_stig_missing_or_uninitialized(grid_manager_setup):
    gm = grid_manager_setup
    grid = gm[0]

    # No active tiles -> returns None
    grid.deactivate_all_tiles()
    assert gm.get_first_active_tile_wd_stig(0) is None

    # Active tile with wd = 0 (uninitialized) -> returns None
    grid.active_tiles = [0]
    grid[0].wd = 0.0
    grid[0].stig_xy = (0.0, 0.0)
    assert gm.get_first_active_tile_wd_stig(0) is None

    # Invalid / out of bounds grid index
    assert gm.get_first_active_tile_wd_stig(99) is None
    assert gm.get_first_active_tile_wd_stig(-1) is None


def test_apply_focus_stig_from_grids_happy_path(test_setup):
    gm, ovm = test_setup
    assert ovm.number_ov >= 1
    assert gm.number_grids >= 1

    # Configure Grid 0
    grid0 = gm[0]
    grid0.active = True
    grid0.active_tiles = [0]
    grid0[0].wd = 0.0062
    grid0[0].stig_xy = (1.25, -0.75)

    # Overview 0 active with initial different values
    ov0 = ovm[0]
    ov0.active = True
    ov0.wd_stig_xy = [0.0050, 0.0, 0.0]

    res = ovm.apply_focus_stig_from_grids(gm)
    assert res is True
    assert ov0.wd_stig_xy[0] == pytest.approx(0.0062)
    assert ov0.wd_stig_xy[1] == pytest.approx(1.25)
    assert ov0.wd_stig_xy[2] == pytest.approx(-0.75)


def test_apply_focus_stig_from_grids_1_to_1_isolation_and_skip(test_setup):
    gm, ovm = test_setup
    # Add second overview if needed
    if ovm.number_ov < 2:
        ovm.add_new_overview(ov_active=True)

    # Grid 0 exists and is active
    grid0 = gm[0]
    grid0.active = True
    grid0.active_tiles = [0]
    grid0[0].wd = 0.0071
    grid0[0].stig_xy = (0.5, 0.5)

    # Overview 0 active
    ov0 = ovm[0]
    ov0.active = True
    ov0.wd_stig_xy = [0.005, 0.0, 0.0]

    # Ensure Grid 1 does NOT exist
    while gm.number_grids > 1:
        gm.delete_grid()

    # Overview 1 active but has no matching Grid 1
    ov1 = ovm[1]
    ov1.active = True
    ov1.wd_stig_xy = [0.0042, 0.1, 0.2]

    res = ovm.apply_focus_stig_from_grids(gm)
    assert res is True
    # OV 0 updated from Grid 0
    assert ov0.wd_stig_xy[0] == pytest.approx(0.0071)
    assert ov0.wd_stig_xy[1] == pytest.approx(0.5)
    assert ov0.wd_stig_xy[2] == pytest.approx(0.5)

    # OV 1 remains unchanged
    assert ov1.wd_stig_xy[0] == pytest.approx(0.0042)
    assert ov1.wd_stig_xy[1] == pytest.approx(0.1)
    assert ov1.wd_stig_xy[2] == pytest.approx(0.2)


def test_apply_focus_stig_from_grids_afss_active_guard(test_setup):
    class MockAutofocus:
        def __init__(self, afss_active=True):
            self.afss_active = afss_active

    gm, ovm = test_setup
    grid0 = gm[0]
    grid0.active = True
    grid0.active_tiles = [0]
    grid0[0].wd = 0.0060
    grid0[0].stig_xy = (0.1, 0.2)
    # Mark first active tile as autofocus reference tile
    grid0[0].autofocus_active = True

    ov0 = ovm[0]
    ov0.active = True
    ov0.wd_stig_xy = [0.0050, 0.0, 0.0]

    # AFSS sweep active -> should block transfer for OV 0
    af_mock = MockAutofocus(afss_active=True)
    res = ovm.apply_focus_stig_from_grids(gm, autofocus=af_mock)
    assert res is False
    assert ov0.wd_stig_xy[0] == pytest.approx(0.0050)

    # AFSS finished (afss_active=False) -> should allow transfer
    af_mock.afss_active = False
    res2 = ovm.apply_focus_stig_from_grids(gm, autofocus=af_mock)
    assert res2 is True
    assert ov0.wd_stig_xy[0] == pytest.approx(0.0060)


def test_ov_settings_dlg_manual_copy_button(test_setup, monkeypatch):
    from unittest.mock import MagicMock
    from main_controls_dlg_windows import OVSettingsDlg
    from PyQt5.QtWidgets import QMessageBox

    gm, ovm = test_setup
    sem = ovm.sem

    # Set up Grid 0 with valid focus/stig
    grid0 = gm[0]
    grid0.active = True
    grid0.active_tiles = [0]
    grid0[0].wd = 0.0065
    grid0[0].stig_xy = (0.25, -0.45)

    ovm[0].active = True
    ovm[0].wd_stig_xy = [0.0050, 0.0, 0.0]

    trigger = MagicMock()

    # Monkeypatch QMessageBox to avoid blocking dialogs
    msg_box_calls = []
    monkeypatch.setattr(QMessageBox, 'information', lambda parent, title, text: msg_box_calls.append(('info', title, text)))
    monkeypatch.setattr(QMessageBox, 'warning', lambda parent, title, text: msg_box_calls.append(('warn', title, text)))

    dlg = OVSettingsDlg(ovm, sem, 0, trigger, gm=gm)
    assert hasattr(dlg, 'pushButton_copyFocusStigFromGrid')
    assert dlg.pushButton_copyFocusStigFromGrid.text() == 'Copy Focus/Stig from Grid'

    # Click the copy button
    dlg.pushButton_copyFocusStigFromGrid.click()

    # Verify OV 0 settings updated
    assert ovm[0].wd_stig_xy[0] == pytest.approx(0.0065)
    assert ovm[0].wd_stig_xy[1] == pytest.approx(0.25)
    assert ovm[0].wd_stig_xy[2] == pytest.approx(-0.45)

    # Verify user feedback & trigger call
    assert any(c[0] == 'info' and 'Focus/Stig Updated' in c[1] for c in msg_box_calls)
    trigger.transmit.assert_called_with('OV SETTINGS CHANGED')


def test_acq_settings_dlg_sync_checkbox(test_setup):
    from unittest.mock import MagicMock
    from main_controls_dlg_windows import AcqSettingsDlg

    gm, ovm = test_setup
    cfg = ovm.cfg
    syscfg = ovm.cs.syscfg

    # Mock Acquisition object
    acq = MagicMock()
    acq.cfg = cfg
    acq.syscfg = syscfg
    acq.sem = ovm.sem
    acq.base_dir = 'C:\\test_acq'
    acq.slice_thickness = 30
    acq.slice_counter = 0
    acq.total_z_diff = 0
    acq.use_target_z_diff = False
    acq.number_slices = 100
    acq.target_z_diff = 3.0
    acq.eht_off_after_stack = False
    acq.send_metadata = False
    acq.metadata_project_name = 'test'

    notifications = MagicMock()
    notifications.metadata_server_url = 'https://remote.server.ch'
    notifications.metadata_server_admin_email = 'admin@server.ch'

    dlg = AcqSettingsDlg(acq, notifications, use_microtome=True)
    assert hasattr(dlg, 'checkBox_syncOVFocusStig')
    # Default is checked
    assert dlg.checkBox_syncOVFocusStig.isChecked() is True

    # Toggle off and accept
    dlg.checkBox_syncOVFocusStig.setChecked(False)
    # Simulate accept click logic
    dlg.accept()
    assert acq.cfg['overviews']['sync_focus_stig_from_grids'] == 'False'


def test_acquisition_auto_sync_before_overview(test_setup):
    from unittest.mock import MagicMock
    from acquisition import Acquisition

    gm, ovm = test_setup
    cfg = ovm.cfg
    syscfg = ovm.cs.syscfg

    # Ensure sync is enabled in cfg
    cfg['overviews']['sync_focus_stig_from_grids'] = 'True'

    # Set up Grid 0
    grid0 = gm[0]
    grid0.active = True
    grid0.active_tiles = [0]
    grid0[0].wd = 0.0078
    grid0[0].stig_xy = (-1.1, 2.2)

    # Overview 0 active with different initial focus
    ovm[0].active = True
    ovm[0].wd_stig_xy = [0.0050, 0.0, 0.0]

    # Initialize Acquisition instance without running full __init__ that touches disk
    acq = Acquisition.__new__(Acquisition)
    acq.cfg = cfg
    acq.syscfg = syscfg
    acq.ovm = ovm
    acq.gm = gm
    acq.sem = ovm.sem
    acq.pause_state = 0
    acq.error_state = 0
    acq.slice_counter = 0
    acq.autofocus = MagicMock()
    acq.autofocus.afss_active = False

    # Mock acquire_overview so it doesn't try to drive hardware or filesystem
    acq.acquire_overview = MagicMock(return_value=('rel/path', '/abs/path', True, False))

    acq.acquire_all_overviews()

    # Verify OV 0 wd_stig_xy was updated prior to imaging
    assert ovm[0].wd_stig_xy[0] == pytest.approx(0.0078)
    assert ovm[0].wd_stig_xy[1] == pytest.approx(-1.1)
    assert ovm[0].wd_stig_xy[2] == pytest.approx(2.2)


def test_default_cfg_entry_count_matches_template():
    """Verify that default.ini and system.cfg entry counts match CFG_NUMBER_KEYS and CFG_NUMBER_SECTIONS."""
    import os
    from configparser import ConfigParser
    from config_template import check_number_of_entries

    repo_root = os.path.dirname(os.path.dirname(__file__))
    default_ini = os.path.join(repo_root, 'src', 'default_cfg', 'default.ini')
    system_cfg = os.path.join(repo_root, 'src', 'default_cfg', 'system.cfg')

    cfg = ConfigParser()
    with open(default_ini, 'r') as f:
        cfg.read_file(f)
    syscfg = ConfigParser()
    with open(system_cfg, 'r') as f:
        syscfg.read_file(f)

    assert check_number_of_entries(cfg, is_sys_cfg=False) is True
    assert check_number_of_entries(syscfg, is_sys_cfg=True) is True

