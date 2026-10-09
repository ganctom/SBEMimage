# PRD: feat/ov-rotation

## 1. System Objective

Enable each Overview (OV) image to be acquired and displayed with an
arbitrary scan-rotation angle (0–360°), mirroring the existing capability
already available for acquisition grids.  The rotation angle must be:

1. **Stored** per-OV in the session config (key already exists: `ov_rotation`).
2. **Applied** to the SEM scan-rotation during `acquire_overview()`, then
   conditionally reset to 0° after the OV if the angle was non-zero
   (see §2 for nuance on the guard).
3. **Displayed** in the Viewport by rotating the OV QPixmap and its bounding
   rectangle around the OV centre.
4. **Editable** via the OV Settings dialog (`OVSettingsDlg`) using a new
   `doubleSpinBox_rotation` widget placed directly below the Dwell Time row.
5. **Inheritable from a grid**: a companion `comboBox_inheritGrid` and
   `pushButton_inheritRotation` allow the user to copy an existing grid's
   rotation into the spinbox in one click. The combo pre-selects the grid
   whose index matches the current OV index (clamped to available grids).

## 2. Hard Constraints

- **Target Runtime**: Python 3.7.6 (x86_64 Rosetta / Conda `sbem-py37`).
  - NO walrus operator (`:=`).
  - NO PEP 585 generics (`list[str]`); use `typing.List[str]`.
  - NO PEP 604 unions (`int | None`); use `typing.Optional[int]`).
  - NO f-strings with `=` (`f"{var=}"`).
- **SmartSEM polarity**: For non-MagC mode, grid acquisition uses
  `theta = (360 - theta) % 360` (confirmed `acquisition.py:2165`). The same
  polarity convention **must** be applied for OVs.
- **Scan-rotation reset guard**: After each OV, `set_scan_rotation(0)` is
  called *if and only if* the OV's rotation was non-zero. This is necessary
  to protect the subsequent operation: if OV[n] has θ>0° and OV[n+1] has
  θ=0°, the `if theta > 0` entry-guard for OV[n+1] won't fire, so without the
  post-reset the SEM would acquire OV[n+1] at the wrong angle. Calling
  `set_scan_rotation(0)` redundantly (even if the next grid has the same
  rotation) is safe and adds only a few milliseconds — no separate settling
  delay is needed.
- **Backward compatibility**: Old config files have `ov_rotation = [0]` —
  already default-safe. The `OverviewManager.__init__` already loads this
  field but passes it nowhere; wiring it up must not break zero-rotation
  configs.
- **PyQt `.ui` files**: Widget additions must be made in the `.ui` file
  (`gui/overview_settings_dlg.ui`), not programmatically, to match project
  patterns.

## 3. Hardware & Physical Dynamics

- `set_scan_rotation(angle)` rotates the electron-beam scan pattern.
  The SmartSEM API accepts angles in degrees (0–360). For Zeiss/SmartSEM the
  physical direction convention requires `(360 - theta) % 360` to agree with
  the SBEMimage coordinate system (confirmed by the existing grid code).
- Scan rotation has negligible settling time at the angles used (< 1°/ms);
  no additional delay is required beyond the existing frame settle logic.
- OVs are 1×1 grids — `Overview.rotation` already exists (inherited from
  `Grid`) and is saved/loaded, but is silently ignored everywhere downstream.

## 4. In-Scope Boundaries

| File | Change |
|---|---|
| `gui/overview_settings_dlg.ui` | Add `doubleSpinBox_rotation` (0–360, step 1.0, decimals 1), `comboBox_inheritGrid`, `pushButton_inheritRotation` ("Get rotation angle"); expand dialog height |
| `src/main_controls_dlg_windows.py` | Wire new widgets in `OVSettingsDlg`; implement inherit-from-grid logic |
| `src/acquisition.py` | Apply scan rotation in `acquire_overview()` and conditionally reset after |
| `src/acq_func.py` | Apply scan rotation in Viewport `acquire_ov()` ("Refresh OV(s)") and reset after |
| `src/viewport.py` | Rotate OV image & bounding rect in `_vp_place_overview()` |
| `src/grid_manager.py` | Add `tile_corners()` to compute corner coordinates of tiles at arbitrary grid rotations |
| `src/overview_manager.py` | Fix `Overview.__init__` to pass through `rotation` instead of hardcoding 0; project tile corners into OV coordinate frame in `update_debris_detection_area` |
| `src/sem_control_zeiss.py` | Enable `DP_SCAN_ROT=1` before `AP_SCANROTATION` for angle > 0; disable only `DP_SCAN_ROT=0` for angle == 0 |
| `tests/test_overview_manager.py` | Unit tests for rotation persistence and unrotated bounding box |
| `tests/test_ov_rotation.py` | Automated unit/GUI test suite covering acquisition, refresh, and debris detection |

## 5. Anti-Targets

- Do **not** change `StubOverview` — stub rotation is not in scope.
- Do **not** refactor `Grid`, `GridManager`, or any other acquisition path.
- Do **not** touch `magc/` or MagC-mode grid logic.
- Do **not** add rotation to the drag-to-draw OV mouse interaction (always
  creates OVs at 0°, same as grids drawn by mouse).
- Do **not** handle `overview_position_for_registration()` rotation in this
  feature (the existing TODO remains a deferred task).

## 6. Architectural Discussion & Design

### 6.1 Data Flow Fix

```
          ┌─────────────────────────┐
          │  OverviewManager.init() │
          │  loads ov_rotation[i]   │  ← already loaded, IGNORED
          └──────────┬──────────────┘
                     │ rotation=0  (hardcoded in Overview.__init__)
                     ▼
               Overview(Grid)
               .rotation == 0      ← BUG: rotation lost here
```

Fix: pass `ov_rotation[i]` through `Overview.__init__` → `Grid.__init__`
(remove the hardcoded `rotation=0`).

### 6.2 Debris Detection Area Projection

The debris detection area is stored in pixel coordinates of the OV image.
When the OV has a rotation $\theta$:
- Active tile corner coordinates $(x, y)$ in display coordinates are projected into
  the OV image coordinate frame $(u, v)$ relative to the OV top-left origin.
- The minimum bounding box enclosing all active tile corners that overlap the OV
  footprint is converted to pixel coordinates and expanded by `margin`.
- In the Viewport, `_vp_place_overview()` rotates the QPainter by $\theta$ before
  drawing the debris detection rectangle, which now snugly and accurately encloses
  the active tiles without cutting off corners.

### 6.3 Acquisition Guard (mirrors grid pattern, with post-reset rationale)

```python
# In acquire_overview(), before sem.acquire_frame():
theta_sbem = self.ovm[ov_index].rotation
theta_sem = (360 - theta_sbem) % 360 if not self.magc_mode else theta_sbem
if theta_sem > 0:
    self.sem.set_scan_rotation(theta_sem)
# ... acquire frame ...
# After acquire_frame():
if theta_sem > 0:
    self.sem.set_scan_rotation(0)   # always reset to protect next operation
```

The post-reset is required because a subsequent OV or grid with θ=0 would not
call `set_scan_rotation` at all (entry guard `if theta_sem > 0` would be
False), leaving the SEM at the previous angle.

### 6.4 Viewport Rotation

Use `QPainter.save()` / `QPainter.translate()` / `QPainter.rotate()` /
`QPainter.restore()` around the `drawPixmap` and `drawRect` calls in
`_vp_place_overview()`, rotating around the viewport centre of the OV.
Matches the pattern used for grid rotation in `viewport.py:1764–1768`.

### 6.5 GUI: Rotation Row + Inherit-from-Grid

**Layout** (below Dwell Time row at y≈170, shifting existing content down):

```
y=198  Label "Rotation (°):"           [10, 198, 111, 16]
y=195  doubleSpinBox_rotation          [150, 195, 62, 22]  step=1.0, dec=1, [0,360]
y=220  comboBox_inheritGrid            [10, 230, 68, 22]   (active grids)
y=220  pushButton_inheritRotation      [83, 230, 128, 22]  "Get rotation angle"
```

All widgets below (acqInterval, acqIntervalOffset, explanatory labels,
radio buttons, Clear button, separator, Save/Add/Delete buttons, Close)
shift down by ~60 px. Dialog height grows from 499 → 560 px.

**Python wiring** in `OVSettingsDlg.__init__()`:
- Populate `comboBox_inheritGrid` with active-grid labels; default index =
  `min(current_ov, gm.number_grids - 1)`.
- `pushButton_inheritRotation.clicked` → read rotation from selected grid,
  write to `doubleSpinBox_rotation`.
- `update_active_status()` enables/disables all three new widgets together
  with the existing imaging-parameter widgets.
