# Verification Protocol: focus-stig-to-ov

## Automated Testing Suite
1. Dedicated test runner for `focus-stig-to-ov` (tests T-001 through T-004):
   ```bash
   /Users/ganctoma/miniforge3/envs/sbem-py37/bin/pytest tests/test_focus_stig_to_ov.py -v
   ```
   **Result:** 9 passed in 1.71s (100% pass rate).
   - `test_get_first_active_tile_index`: validates lowest active tile index lookup and boundary checks.
   - `test_get_first_active_tile_wd_stig_valid`: validates WD in meters and stigmation (x, y) % extraction.
   - `test_get_first_active_tile_wd_stig_missing_or_uninitialized`: validates `wd <= 0` or missing active tile handling.
   - `test_apply_focus_stig_from_grids_happy_path`: validates 1:1 transfer from Grid 0 to OV 0.
   - `test_apply_focus_stig_from_grids_1_to_1_isolation_and_skip`: validates isolation and missing grid skip without error.
   - `test_apply_focus_stig_from_grids_afss_active_guard`: validates AFSS sweep in progress blocks transfer and unblocks once complete.
   - `test_ov_settings_dlg_manual_copy_button`: validates GUI button in `OVSettingsDlg` transfers parameters and emits notification.
   - `test_acq_settings_dlg_sync_checkbox`: validates `checkBox_syncOVFocusStig` in `AcqSettingsDlg` defaults to True and toggles properly.
   - `test_acquisition_auto_sync_before_overview`: validates pre-acquisition hook in `Acquisition.acquire_all_overviews`.

2. Regression Test Suites:
   ```bash
   /Users/ganctoma/miniforge3/envs/sbem-py37/bin/pytest tests/test_ov_rotation.py
   ```
   **Result:** 13 passed in 1.97s.

3. Python 3.7 Bytecode Compilation Check:
   ```bash
   /Users/ganctoma/miniforge3/envs/sbem-py37/bin/python -m py_compile src/grid_manager.py src/overview_manager.py src/main_controls_dlg_windows.py src/acquisition.py
   ```
   **Result:** Clean compilation without warnings or errors.

## Physical / Simulation Manual Verification Routine
1. Launch SBEMimage in simulation/mock mode.
2. Open **Overview Setup** (`OVSettingsDlg`):
   - Notice the new button: `Copy Focus/Stig from Grid`.
   - Click the button: confirm the message box displays the updated WD (in mm) and Stig (%) transferred from the active grid.
3. Open **Acquisition Settings** (`AcqSettingsDlg`):
   - Notice the checkbox: `Sync OV focus/stig from grids before OV acq.`.
   - Confirm it is checked by default.
4. Run an acquisition:
   - Verify that prior to OV frame acquisition, overview focus settings are kept in sync with the primary grid's first active tile.
