# Verification Protocol: ov-rotation

## Automated Testing

1. **Token-optimized test runner**:
   ```bash
   ~/miniforge3/envs/sbem-py37/bin/python agent_test.py tests/test_ov_rotation.py
   ```
   (And OverviewManager test suite from `src/`):
   ```bash
   cd src && ~/miniforge3/envs/sbem-py37/bin/python ../agent_test.py test_overview_manager.py
   ```

2. **Python 3.7 syntax and bytecode compilation**:
   ```bash
   ~/miniforge3/envs/sbem-py37/bin/python -m py_compile src/overview_manager.py src/acquisition.py src/viewport.py src/main_controls_dlg_windows.py src/main_controls.py
   ```

3. **Coverage of automated test suite (`tests/test_ov_rotation.py` + `src/test_overview_manager.py`)**:
   - `test_overview_bounding_box_unaffected_by_rotation`: Bounding box returns unrotated coordinate reference regardless of rotation.
   - `test_overview_rotation_persistence`: Save/load rotation to/from session cfg, backward compatibility with older configs.
   - `test_add_new_overview_rotation`: Setting rotation on newly added overviews.
   - `test_acquire_overview_rotation_applied_and_reset`: Polarity $(360-\theta)\bmod 360$ applied before acquisition, restored to 0° after.
   - `test_acquire_overview_zero_rotation_no_scan_rotation_calls`: 0° rotation makes no unnecessary SEM calls.
   - `test_acquire_overview_exception_still_resets_scan_rotation`: `try...finally` guarantees reset on beam or communication exception.
   - `test_ov_settings_dlg_inherit_rotation_and_save`: GUI spinbox initialization, grid selection, "Get rotation angle" button inheritance, and save.
   - `test_sem_zeiss_set_scan_rotation_order`: SmartSEM parameter ordering (`DP_SCAN_ROT=1` before `AP_SCANROTATION`), and only `DP_SCAN_ROT=0` on reset so tick mark clears.
   - `test_debris_detection_area_with_rotated_ov`: Active tile debris detection coordinates projected accurately into rotated OV image frame.
   - `test_acq_func_acquire_ov_scan_rotation`: Viewport 'Refresh OV' applies scan rotation and resets in finally block.
   - `test_grid_tile_corners`: Tile corners computed accurately at arbitrary rotation angles.
   - `test_debris_detection_area_encloses_active_tiles_at_various_angles`: Active tiles are strictly enclosed at all rotation angles without missing parts.

## Physical Instrument Manual Verification Routine

1. **Launch SBEMimage with Mock or Zeiss SEM**:
   - Open Overview Setup (`OVSettingsDlg`).
   - Verify `Rotation (°)` spinbox appears directly below Dwell Time with step 1.0 and range 0–360°.
   - Verify `comboBox_inheritGrid` displays all existing grids with default index matching current OV.
   - Click `Get rotation angle` and verify the spinbox updates to match the selected grid's angle.
   - Save settings and verify viewport re-draws OV rotated around its centre.
2. **Viewport Refresh OV Verification**:
   - Click `Refresh OV(s)` in Viewport for an OV with non-zero rotation angle.
   - Verify SmartSEM displays the correct rotation angle during acquisition, and unticks the box after acquisition finishes.
3. **Tile-Grid Acquisition Verification**:
   - Verify that acquiring rotated tile-grids applies the correct rotation angle to the SEM during acquisition, and turns OFF scan rotation when the grid completes.
4. **Debris Detection Verification**:
   - With margin set to 0 and OV rotation set to 30°, verify that the debris detection rectangle tightly encloses active tiles in the Viewport without missing any tile corners.
