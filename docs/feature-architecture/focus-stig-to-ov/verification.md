# Verification Protocol: focus-stig-to-ov

## Automated Testing Suite
1. Dedicated test runner for `focus-stig-to-ov` (tests T-001 through T-006):
   ```bash
   /Users/ganctoma/miniforge3/envs/sbem-py37/bin/pytest tests/test_focus_stig_to_ov.py -v
   ```
   **Result:** 11 passed in 2.51s (100% pass rate).
   - `test_get_first_active_tile_index`: validates lowest active tile index lookup and boundary checks.
   - `test_get_first_active_tile_wd_stig_valid`: validates WD in meters and stigmation (x, y) % extraction.
   - `test_get_first_active_tile_wd_stig_missing_or_uninitialized`: validates `wd <= 0` or missing active tile handling.
   - `test_apply_focus_stig_from_grids_happy_path`: validates 1:1 transfer from Grid 0 to OV 0 and ensures no noisy transfer log messages.
   - `test_apply_focus_stig_from_grids_1_to_1_isolation_and_skip`: validates isolation and missing grid skip without error.
   - `test_apply_focus_stig_from_grids_afss_active_guard`: validates AFSS sweep completed state allows transfer of converged settings.
   - `test_apply_focus_stig_from_grids_afss_unperturbed_memory`: validates active AFSS sweep falls back to unperturbed settings stored in AFSS memory.
   - `test_ov_settings_dlg_manual_copy_button`: validates GUI button in `OVSettingsDlg` transfers parameters and emits notification.
   - `test_autofocus_settings_dlg_sync_checkbox`: validates live activation/deactivation during ongoing acquisition without sending SEM commands, with action logged to `SBEMimage.log`.
   - `test_autofocus_settings_dlg_no_ui_overlap`: validates layout geometry of `AutofocusSettingsDlg` to prevent widget collisions.
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
   - Notice the button: `Copy Focus/Stig from Grid`.
   - Click the button: confirm the message box displays the updated WD (in mm) and Stig (%) transferred from the active grid.
3. Open **Autofocus/Tracking Settings** (`AutofocusSettingsDlg`):
   - Inspect General settings under Tracking mode.
   - Notice the checkbox: `Sync OV focus/stig from grids before OV acq.`.
   - Confirm layout has no widget overlap.
   - Confirm it is checked by default.
   - Test toggling ON/OFF during idle and running acquisition: confirms in-memory metadata update without physical SEM calls.
4. Run an acquisition:
   - Verify that prior to OV frame acquisition, overview focus settings are kept in sync with the primary grid's first active tile.
