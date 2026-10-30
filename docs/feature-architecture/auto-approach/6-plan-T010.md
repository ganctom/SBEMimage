# Implementation Plan - T-010 Viewport Approach Tab [MUTABLE]

## Metadata [MUTABLE]
- **Task ID:** T-010
- **Task Title:** Add 4th Approach Tab (`tab_ap`) to `gui/viewport.ui` & `src/viewport.py` (Auto-Tiled Cyan/Magenta Grid, Mouse-Wheel Series Scrubbing, Step Slider, Raw Toggle, Double-Click Zoom, Archived Run Loader & Viewport Right-Click Ref Badge)
- **Agent:** `implementation-engineer`
- **PRD:** `1-prd.md`
- **ADL:** `2-adl.md`
- **Tasks:** `5-tasks.md`
- **AC IDs:** `AC-SBEM-AUTO_APPROACH-003`, `AC-SBEM-AUTO_APPROACH-007`
- Status: Completed

## Summary
Add a dedicated, high-signal 4th tab (`tab_ap`, labeled "Approach") to `SBEMimage Viewport` (`gui/viewport.ui` and `src/viewport.py`) rendering adaptive multi-tile Cyan/Magenta difference overlays with full mouse-wheel scrubbing and archived run replay:
1. `gui/viewport.ui`:
   - Add 4th tab `<widget class="QWidget" name="tab_ap">` to `tabWidget`.
   - Canvas: `QLabel` named `QLabel_ApproachCanvas` with `minimumSize` (1, 1), policy Expanding/Expanding.
   - Bottom Controls Box (`groupBox_apControls`):
     - `horizontalSlider_stepAP`: `QSlider` (horizontal, range 0 to max_steps, singleStep 1).
     - `label_stepInfoAP`: `QLabel` displaying current step metrics (`Step k / K | Slices: N | Depth: D.DD µm | State: S`).
     - `pushButton_rawToggleAP`: `QPushButton` (checkable, text "Show Raw" / "Cyan-Magenta").
     - `comboBox_runSelectorAP`: `QComboBox` listing available timestamped runs in `<base_dir>/meta/approach/`.
     - `pushButton_loadRunAP`: `QPushButton` with text `"(Re)load"`.
2. `src/viewport.py`:
   - Canvas setup & state tracking:
     - `self.ap_canvas = QPixmap(self.cs.vp_width, self.cs.vp_height)`.
     - `self.ap_qp = QPainter()`.
     - State variables: `self.ap_current_step = 0`, `self.ap_max_steps = 0`, `self.ap_steps = []`, `self.ap_raw_mode = False`, `self.ap_zoom_tile = None`, `self.ap_tile_rects = {}`, `self.ap_run_dir = None`.
     - In `resizeEvent(self, event)`: reallocate `self.ap_canvas = QPixmap(self.cs.vp_width, self.cs.vp_height)` and call `self.ap_draw()` when `tabWidget.currentIndex() == 3` (AR2-T010-006).
   - Main View (`tab_mv`) Context Menu & Tile Badging (AC-SBEM-AUTO_APPROACH-003):
     - In `vp_show_context_menu(self, p)` (AR2-T010-005): when a tile is selected, add action `"Select/Deselect tile g.t as approach ref."`, connected to `self._vp_toggle_approach_ref_tile`.
     - In `_vp_toggle_approach_ref_tile(self)`: toggles `tile.approach_active`, emits `self.main_controls_trigger.transmit('UPDATE APPROACH REF TILES')` (AR2-T010-003, AR2-T010-005), and calls `self.vp_draw()`.
     - In `_vp_place_grid(self, grid_index, tile_map, resize_ratio, show_grid)` (AR2-T010-005): render `'APPROACH'` badge on tiles (combining cleanly as `'AF + APPROACH'`, `'GRAD + APPROACH'`, or `'GRAD + AF + AP'`).
   - Mouse interactions:
     - In `wheelEvent(self, event)`: when active tab is `tab_ap` (index 3), scrolling up invokes `ap_step_fwd()`, scrolling down invokes `ap_step_bwd()`.
     - In `mouseDoubleClickEvent(self, event)`: when active tab is `tab_ap`, hit-test click position against `self.ap_tile_rects` to toggle single-tile zoom (`self.ap_zoom_tile = key` vs `None`).
   - Approach Tab Drawing Engine (`ap_draw(self)`):
     - Early Guard (AR2-T010-004): If `not self.ap_steps` or probe tiles count $N == 0$: fill `self.ap_canvas` with `Qt.black`, open `self.ap_qp.begin(self.ap_canvas)`, draw centered placeholder text `"No approach run active or loaded"`, end `self.ap_qp.end()`, set pixmap, and return immediately.
     - Clear `self.ap_canvas` with `Qt.black`.
     - Open painter `self.ap_qp.begin(self.ap_canvas)`.
     - If `self.ap_zoom_tile` is selected: render that single tile scaled to fill canvas while preserving aspect ratio.
     - Else: compute optimal grid layout columns $C = \max(1, \lceil\sqrt{N}\rceil)$, rows $R = \max(1, \lceil N / C \rceil)$ (AR2-T010-004) to display all probe tiles simultaneously.
     - For each probe tile:
       - If step $k == 0$: display baseline raw image $\tilde{I}_0$ from `step_record.tile_evaluations[tile_key].raw_image_path`.
       - If step $k > 0$:
         - If `self.ap_raw_mode` is True: render raw current image $\tilde{I}_k$ from `raw_image_path`.
         - Else: load pre-rendered overlay image directly from `step_record.tile_evaluations[tile_key].overlay_image_path` (or `<run_dir>/overlays/step_%03d_g%04d_t%04d_cm.png`); if dynamic generation is required as fallback, call `auto_approach.compose_cyan_magenta_overlay(prev_img, curr_img, shift_yx=eval_record.shift_yx_px, scale_to_width=cell_w)` with required `shift_yx` argument (AR2-T010-001).
       - Convert image/array to `QImage` / `QPixmap` and draw inside computed cell rect.
       - Store bounding box in `self.ap_tile_rects[key]`.
       - Render header text overlay on tile top edge: `Tile g.t | Step k | ΔZ µm`.
       - Draw tile border: subtle border normally, highlighted border (`#FF00FF` Magenta) if contact was detected on that tile in step $k$.
     - Close painter `self.ap_qp.end()`.
     - Set pixmap on canvas: `self.QLabel_ApproachCanvas.setPixmap(self.ap_canvas)`.
   - Step navigation & Run loading:
     - `ap_step_fwd(self)`, `ap_step_bwd(self)`, `ap_set_step(self, step_idx)`.
     - `ap_toggle_raw_mode(self)`: toggles `self.ap_raw_mode` and redraws.
     - `ap_populate_run_selector(self)`: populates `comboBox_runSelectorAP` with timestamped run directories found in `meta/approach/`.
     - `ap_load_selected_run(self, run_dir=None)`: parses `manifest.json` following `4-data-model.md §5` (AR2-T010-002), reading `raw_image_path` under `raw/` and `overlay_image_path` under `overlays/`, initializes step slider, and renders latest step.
     - `ap_update_live_step(self, progress, step_record)`: receives live updates during active runs on the main thread and immediately renders the new step (AR2-T010-003).
3. Cross-component trigger routing in `src/main_controls.py` & `src/main_controls_dlg_windows.py` (AR2-T010-003):
   - In `MainControls.process_signal`:
     - When `msg == 'UPDATE APPROACH REF TILES'`: if `self.approach_dlg is not None`, call `self.approach_dlg.sync_ref_tiles_from_grid_manager()`.
     - When `isinstance(msg, tuple) and msg[0] == 'UPDATE APPROACH PROGRESS'`: call `self.viewport.ap_update_live_step(msg[1], msg[2])`.
   - In `ApproachDlg.update_auto_approach_progress`: transmit `('UPDATE APPROACH PROGRESS', progress, step_record)` to `self.main_controls_trigger`.
4. Unit tests in `tests/test_auto_approach.py` (§1.4.5, §1.4.7) (AR2-T010-007):
   - Add `test_viewport_approach_tab_and_wheel_scrubbing()`:
     - Verify `tab_ap` UI loading in `gui/viewport.ui` at tab index 3.
     - Verify right-click approach ref toggle updates `Tile.approach_active`, `GridManager.approach_ref_tiles`, and transmits `'UPDATE APPROACH REF TILES'` signal.
     - Verify tile badge drawing in `_vp_place_grid` on `tab_mv` for standalone and shared labels (`APPROACH`, `AF + APPROACH`, `GRAD + APPROACH`).
     - Verify `ap_draw()` empty state early guard rendering placeholder without division by zero.
     - Verify `ap_draw()` in multi-tile grid mode and single-tile zoom mode.
     - Verify wheel scrubbing forwards and backwards through steps.
     - Verify `raw_toggle` mode switches between raw grayscale and Cyan/Magenta overlay.
     - Verify double-click hit test toggles `ap_zoom_tile`.
     - Verify archived run discovery and replay from `meta/approach/<timestamp>/manifest.json` using `raw/` and `overlays/` paths.
     - Verify `resizeEvent` reallocates `ap_canvas` and redraws when `tab_ap` is active.

## Targets, Tests, Done When [MUTABLE]
- **Targets:** `gui/viewport.ui`, `src/viewport.py`, `src/main_controls.py`, `src/main_controls_dlg_windows.py`
- **Tests:** `tests/test_auto_approach.py`
- **Done when:** `~/miniforge3/envs/sbem-py37/bin/python agent_test.py tests/test_auto_approach.py` passes with zero errors; Viewport provides 4th `Approach` tab displaying multi-tile Cyan/Magenta overlays; mouse wheel scrubs steps; double click zooms into single tile; right-click context menu toggles approach reference tiles with live `ApproachDlg` sync; and archived runs load cleanly from `manifest.json`.

## Steps [MUTABLE]
- [x] T-010.1 **[implementation-engineer]** Update `gui/viewport.ui` to add 4th tab `tab_ap` (`Approach`), containing `QLabel_ApproachCanvas` and controls box `groupBox_apControls` with `horizontalSlider_stepAP`, `label_stepInfoAP`, `pushButton_rawToggleAP`, `comboBox_runSelectorAP`, and `pushButton_loadRunAP`.
- [x] T-010.2 **[implementation-engineer]** Upgrade `Viewport.__init__` and `Viewport.resizeEvent` in `src/viewport.py`:
  - Initialize `self.ap_canvas = QPixmap(self.cs.vp_width, self.cs.vp_height)`.
  - Initialize `self.ap_qp = QPainter()`.
  - Initialize state variables (`ap_current_step`, `ap_max_steps`, `ap_steps`, `ap_raw_mode`, `ap_zoom_tile`, `ap_tile_rects`, `ap_run_dir`).
  - Update `resizeEvent(self, event)` to reallocate `self.ap_canvas` and call `ap_draw()` when `tabWidget.currentIndex() == 3` (AR2-T010-006).
  - Wire UI signals: `horizontalSlider_stepAP.valueChanged`, `pushButton_rawToggleAP.clicked`, `pushButton_loadRunAP.clicked`, `comboBox_runSelectorAP.currentIndexChanged`.
  - Handle tab activation in `tab_changed()` for tab index 3.
- [x] T-010.3 **[implementation-engineer]** Implement Viewport `tab_mv` context menu and tile badge drawing in `src/viewport.py` (AC-SBEM-AUTO_APPROACH-003):
  - In `vp_show_context_menu(self, p)`: add `"Select/Deselect tile g.t as approach ref."` action connected to `self._vp_toggle_approach_ref_tile` (AR2-T010-005).
  - Implement `_vp_toggle_approach_ref_tile`: toggle `approach_active`, transmit `'UPDATE APPROACH REF TILES'` to `main_controls_trigger`, and call `self.vp_draw()` (AR2-T010-003, AR2-T010-005).
  - In `_vp_place_grid`: draw `'APPROACH'` label on tiles, combining cleanly with `'AF'` and `'GRAD'` (AR2-T010-005).
- [x] T-010.4 **[implementation-engineer]** Implement cross-component trigger routing in `src/main_controls.py` and `src/main_controls_dlg_windows.py` (AR2-T010-003):
  - In `MainControls.process_signal`: handle `'UPDATE APPROACH REF TILES'` by calling `self.approach_dlg.sync_ref_tiles_from_grid_manager()` when open; handle `('UPDATE APPROACH PROGRESS', progress, step_record)` by calling `self.viewport.ap_update_live_step(progress, step_record)`.
  - In `ApproachDlg.update_auto_approach_progress`: transmit `('UPDATE APPROACH PROGRESS', progress, step_record)` to `self.main_controls_trigger`.
- [x] T-010.5 **[implementation-engineer]** Implement Approach Tab drawing engine and navigation in `src/viewport.py`:
  - `ap_draw(self)`: early guard on $N=0$ rendering placeholder text (AR2-T010-004); render adaptive $R \times C$ grid (or single zoomed tile if `ap_zoom_tile` is active) loading pre-rendered overlay image from `overlay_image_path` (with `auto_approach.compose_cyan_magenta_overlay(prev_img, curr_img, shift_yx=...)` fallback, AR2-T010-001) or raw image if `ap_raw_mode`; draw header badges and contact highlight borders.
  - `ap_step_fwd(self)`, `ap_step_bwd(self)`, `ap_set_step(self, step_idx)`.
  - `ap_toggle_raw_mode(self)`.
  - `ap_update_live_step(self, progress, step_record)`: handle live progress updates from running engine.
- [x] T-010.6 **[implementation-engineer]** Implement mouse interaction event handlers in `src/viewport.py`:
  - In `wheelEvent`: when tab index is 3, scrub steps via `ap_step_fwd()` / `ap_step_bwd()`.
  - In `mouseDoubleClickEvent`: when tab index is 3, hit-test `self.ap_tile_rects` to toggle zoom on clicked tile.
- [x] T-010.7 **[implementation-engineer]** Implement archived run discovery and loading in `src/viewport.py`:
  - `ap_populate_run_selector(self)`: scan `<base_dir>/meta/approach/*/manifest.json`.
  - `ap_load_selected_run(self, run_dir=None)`: parse `manifest.json` following canonical schema reading `raw_image_path` and `overlay_image_path` (AR2-T010-002), load step records, update slider, and redraw.
- [x] T-010.8 **[implementation-engineer]** Add unit tests in `tests/test_auto_approach.py` in method `test_viewport_approach_tab_and_wheel_scrubbing()` (AR2-T010-007):
  - Tab 4 UI existence, canvas dimensions, and controls.
  - Right-click approach ref toggle, `GridManager` live sync, and `ApproachDlg` sync.
  - Badge text rendering combinations on `tab_mv`.
  - Empty state early guard without ZeroDivisionError (AR2-T010-004).
  - Multi-tile adaptive grid rendering and single-tile zoom rendering.
  - Mouse-wheel step scrubbing and step slider synchronization.
  - Raw mode toggle.
  - Double-click hit testing.
  - Archived run loading from `meta/approach/<timestamp>/manifest.json`.
  - Canvas reallocation on `resizeEvent` (AR2-T010-006).
- [x] T-010.9 **[implementation-engineer]** Run bytecode pre-flight check (`~/miniforge3/envs/sbem-py37/bin/python -m py_compile src/viewport.py src/main_controls.py src/main_controls_dlg_windows.py tests/test_auto_approach.py`) and verify green test suite via `~/miniforge3/envs/sbem-py37/bin/python agent_test.py tests/test_auto_approach.py`.
- [x] T-010.10 **[implementation-engineer]** Update `docs/feature-architecture/auto-approach/5-tasks.md` and set `Status: Completed` in `6-plan-T010.md:11`.

## File Permissions
- MODIFY: `gui/viewport.ui`
- MODIFY: `src/viewport.py`
- MODIFY: `src/main_controls.py`
- MODIFY: `src/main_controls_dlg_windows.py`
- MODIFY: `tests/test_auto_approach.py`
- MODIFY: `docs/feature-architecture/auto-approach/5-tasks.md`
- MODIFY: `docs/feature-architecture/auto-approach/6-plan-T010.md`

## Types / methods / interfaces
- `src/viewport.py`:
  - `Viewport.ap_canvas: QPixmap`
  - `Viewport.ap_qp: QPainter`
  - `Viewport.ap_current_step: int`
  - `Viewport.ap_max_steps: int`
  - `Viewport.ap_steps: List[Any]`
  - `Viewport.ap_raw_mode: bool`
  - `Viewport.ap_zoom_tile: Optional[str]`
  - `Viewport.ap_tile_rects: Dict[str, QRect]`
  - `Viewport.ap_run_dir: Optional[str]`
  - `Viewport._vp_toggle_approach_ref_tile(self) -> None`
  - `Viewport.ap_on_tab_activated(self) -> None`
  - `Viewport.ap_draw(self) -> None`
  - `Viewport.ap_step_fwd(self) -> None`
  - `Viewport.ap_step_bwd(self) -> None`
  - `Viewport.ap_set_step(self, step_idx: int) -> None`
  - `Viewport.ap_toggle_raw_mode(self) -> None`
  - `Viewport.ap_populate_run_selector(self) -> None`
  - `Viewport.ap_load_selected_run(self, run_dir: Optional[str] = None) -> None`
  - `Viewport.ap_update_live_step(self, progress: Any, step_record: Any) -> None`
- `src/main_controls.py`:
  - `MainControls.process_signal(self) -> None` (handles `'UPDATE APPROACH REF TILES'` and `('UPDATE APPROACH PROGRESS', progress, step_record)`)
- `src/main_controls_dlg_windows.py`:
  - `ApproachDlg.update_auto_approach_progress(self) -> None` (emits progress tuple to main_controls_trigger)

## Data / contracts
- Grid Layout: For $N$ probe tiles, calculate columns $C = \max(1, \lceil\sqrt{N}\rceil)$, rows $R = \max(1, \lceil N / C \rceil)$. When $N == 0$, display centered text without division.
- Cyan/Magenta Overlay Contract:
  - $R = \tilde{I}_k,\quad G = \tilde{I}_{k-1},\quad B = \max(\tilde{I}_{k-1}, \tilde{I}_k)$
  - Loaded directly from `step_record.tile_evaluations[tile_key].overlay_image_path` under `overlays/step_%03d_g%04d_t%04d_cm.png`, or dynamically generated via `src.auto_approach.compose_cyan_magenta_overlay(img_ref, img_curr, shift_yx=...)`.
- Live Reference Tile Format: comma-separated `'g.t'` in `GridManager.approach_ref_tiles`.
- Wheel Event Contract: Scrolling up increments step index ($k \to k + 1$ clamped to $K$); scrolling down decrements step index ($k \to k - 1$ clamped to 0).
- Double Click Contract: If clicked within bounding rect of tile $t$ in `self.ap_tile_rects`, toggle zoom: `self.ap_zoom_tile = t` if not zoomed, else `self.ap_zoom_tile = None`.
- Archived Run Contract: Directory `<base_dir>/meta/approach/<timestamp>/` containing `manifest.json`, with raw images in `raw/step_%03d_g%04d_t%04d.tif` and overlays in `overlays/step_%03d_g%04d_t%04d_cm.png`.

## Side-effects / risks
- High memory usage caching full-res tile images: Resolved by loading images on-demand for the current step $k$ rather than retaining all history in memory.
- Viewport canvas resizing desynchronization: Resolved by matching canvas size `self.cs.vp_width, self.cs.vp_height` in `ap_canvas` inside `resizeEvent` and redrawing on tab activation or window resize.
- Non-GUI thread drawing hazard: `ap_update_live_step` must only be called on the main thread via Qt signal/slot trigger from `MainControls.process_signal`.
