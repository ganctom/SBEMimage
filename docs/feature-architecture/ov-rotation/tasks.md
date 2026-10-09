# Execution Ledger: feat/ov-rotation

## Phase 1: Specification & Interface Design
- [x] 1.1 Reverse-engineer existing architecture and define top-down interfaces.
- [x] 1.2 Document domain physics and hardware constraints in `knowledge.md`.
- [x] 1.3 Review and align PRD boundaries with user (comments ingested 2026-09-30).

## Phase 2: Implementation & Verification

### 2.1 Fix rotation data flow in `overview_manager.py`
- [x] Pass `ov_rotation[i]` into `Overview.__init__()` (remove hardcoded `rotation=0`).
- [x] Retain unrotated coordinates in `bounding_box()` as coordinate origin reference for debris detection.

### 2.2 Apply scan rotation in `acquisition.py` and `sem_control_zeiss.py`
- [x] In `acquire_overview()`: read `self.ovm[ov_index].rotation`,
      apply `(360-θ)%360` polarity for non-MagC, call `set_scan_rotation()`
      before frame grab (guard: `if theta_sem > 0`).
- [x] After frame grab: call `set_scan_rotation(0)` if `theta_sem > 0`
      (protects subsequent 0°-rotation OVs or grids from inheriting the angle).
- [x] In `sem_control_zeiss.py`: set `AP_SCANROTATION` first and `DP_SCAN_ROT` second
      so `DP_SCAN_ROT=0` turns off the tick mark in SmartSEM without being re-triggered.

### 2.3 Viewport rotation in `viewport.py`
- [x] In `_vp_place_overview()`: use `QPainter.save/translate/rotate/restore`
      to rotate the OV pixmap and bounding rect around the OV viewport centre,
      mirroring the grid rotation pattern (`viewport.py:1764–1768`).

### 2.4 GUI: rotation row + inherit-from-grid in `gui/overview_settings_dlg.ui`
- [x] Add `doubleSpinBox_rotation` (range 0–360, step 1.0, decimals 1) with
      label "Rotation (°):", placed immediately below the Dwell Time row.
- [x] Add `comboBox_inheritGrid` (w=68) + `pushButton_inheritRotation`
      (w=128, "Get rotation angle") in a row below the rotation spinbox.
- [x] Shift all widgets below (acqInterval through Close button) down by ~60 px.
- [x] Expand dialog height from 499 → 560 px.
- [x] Update `<tabstops>` to include new widgets in logical tab order.

### 2.5 Wire new GUI in `src/main_controls_dlg_windows.py`
- [x] `OVSettingsDlg.__init__()`: populate `comboBox_inheritGrid` with
      active-grid labels; default index = `min(current_ov, gm.number_grids - 1)`.
- [x] Connect `pushButton_inheritRotation.clicked` → copy selected grid's
      rotation into `doubleSpinBox_rotation`.
- [x] `show_current_settings()`: set `doubleSpinBox_rotation` from
      `self.ovm[self.current_ov].rotation`.
- [x] `save_current_settings()`: write `doubleSpinBox_rotation.value()` back.
- [x] `update_active_status()`: include all three new widgets in enable/disable.
- [x] `change_ov()`: update `comboBox_inheritGrid` default index to
      `min(new_ov_index, gm.number_grids - 1)`.

### 2.6 Tests in `tests/test_overview_manager.py` and `tests/test_ov_rotation.py`
- [x] `test_rotation_loaded_from_config`: verify `Overview.rotation` matches
      `ov_rotation` loaded from config (non-zero value).
- [x] `test_bounding_box_unaffected_by_rotation`: verify bounds remain unrotated
      reference coordinate frame.
- [x] `test_sem_zeiss_set_scan_rotation_order`: verify `DP_SCAN_ROT=1` is set first
      and `AP_SCANROTATION` is set second (and only `DP_SCAN_ROT=0` when disabling).
- [x] `test_acquire_overview_sets_scan_rotation`: mock `sem.set_scan_rotation`;
      assert it's called with `(360-θ)%360` before acquire and with `0` after.
- [x] `test_acquire_overview_zero_rotation_no_scan_rotation_call`: assert
      `set_scan_rotation` is NOT called when OV rotation is 0°.
- [x] `test_debris_detection_area_with_rotated_ov`: active tile debris detection
      projected accurately into rotated OV image frame.
- [x] `test_acq_func_acquire_ov_scan_rotation`: Viewport 'Refresh OV' applies
      rotation and resets in finally guard.
- [x] `test_grid_tile_corners`: verify 4 corners of tile at arbitrary rotation.
- [x] `test_debris_detection_area_encloses_active_tiles_at_various_angles`: verify
      active tiles are strictly enclosed at all rotation angles.

## Phase 3: Physical Testing Refinements & Release Candidate
- [x] 3.1 Rename button to 'Get rotation angle', narrow grid combobox, and rename label to 'Rotation angle (°):'.
- [x] 3.2 Add `Grid.tile_corners` and project active tile corners into OV coordinate frame
      for debris detection, ensuring active tiles are tightly enclosed without missing parts.
- [x] 3.3 Fix SmartSEM `set_scan_rotation` to enable `DP_SCAN_ROT=1` before `AP_SCANROTATION`,
      and only disable `DP_SCAN_ROT=0` on reset so the tick mark stays OFF.
- [x] 3.4 Support scan rotation and reset guard in Viewport 'Refresh OV' (`acq_func.acquire_ov`).
- [x] 3.5 Fix stale image display in Viewport by clearing `QPixmapCache` and loading via `QImage`.
- [x] 3.6 Remove scan rotation info from main log window as requested.
- [x] 3.7 Update user documentation (`docs/ov-rotation_help.md`) and architecture docs.
- [x] 3.8 Run full automated test suite (19/19 passing).
- [ ] 3.9 Squash development commits into a single commit and fast-forward merge into `dev-tomgan-rel` in `main_repo`.
- [ ] 3.10 Push to remotes (`origin` and `usb`).

