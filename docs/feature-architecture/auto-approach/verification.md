# Verification Protocol: Automated Sample Approach (`auto-approach`)

## 1. Automated Pre-Flight & Pytest Suite (Python 3.7.6)

1. **Fast Bytecode / Syntax Pre-Flight Check (`GEMINI.md` Section 5.4):**
   ```bash
   ~/miniforge3/envs/sbem-py37/bin/python -m py_compile \
     src/auto_approach.py \
     src/config_template.py \
     src/grid_manager.py \
     src/microtome_control.py \
     src/microtome_control_gatan.py \
     src/microtome_control_mock.py \
     src/main_controls.py \
     src/main_controls_dlg_windows.py \
     src/viewport.py
   ```

2. **Token-Optimized Dedicated Test Runner:**
   ```bash
   ~/miniforge3/envs/sbem-py37/bin/python agent_test.py tests/test_auto_approach.py
   ```
   Covers:
   - `check_number_of_entries()` for both `default.ini` (`CFG_NUMBER_SECTIONS = 13`, `CFG_NUMBER_KEYS = 254`) and `system.cfg`.
   - Odd/even scan-line pyramidal SNR calibration across noisy (`0.1 µs`) vs. clean scans.
   - Pre-flight rejection (zero cuts, zero Z-moves) on blank, saturated, and pure featureless white-noise images.
   - Both `Normalized SSIM` and `Gradient SSIM` modes on:
     - Localized partial corner cuts and full-tile surface cuts.
     - Subtle low-contrast surface texture changes (textured-to-smooth resin shave).
     - Dose-induced global brightness/contrast shifts without cutting (zero false positive).
     - Stage XY jitter ($\pm 30\,\text{px}$) with bounded subpixel registration and 100%-shaved correlation-collapse safety.
   - Contrast-matched Cyan/Magenta overlay compositing (`R=Curr, G=Prev, B=max(Prev, Curr)`): neutral gray invariance under brightness drift and pure cyan/magenta polarity.
   - Full `AutoApproachEngine` state machine over mocked Gatan 3View / SmartSEM hardware:
     - Initial start from `'Before slice'` (`Clear` inactive): verifies sample Z is nominal first (halting with zero knife moves if Z is `None`, `< 0`, or `Error.mismatch_z`), then verifies `clear_knife()` (`.ack`) before baseline XY moves and single baseline grab.
     - Beam blanking transitions (`set_beam_blanking(1)` while cutting, `0` only while grabbing).
     - Nominal `Near -> K_capped cuts (.ac2 verified) -> verified Clear (.ack) -> XY move` sequence and `max_depth_um` safety stop.
     - **Error Freeze Invariant:** Explicit assertion that `clear_knife()` is **NEVER** called when any Z-read/move, Near, Cut (`.err`), Clear, XY-move, or SEM grab error occurs (knife stays in its current position).
     - **User Abort Clear-After-Stroke-Down Invariant:** Explicit assertion that user `Abort` halts scheduling further slices, waits for any in-flight `do_full_approach_cut()` `.ac2` confirmation (`'Stroke Up'` deactivated), then commands and verifies `clear_knife()` (`.ack`) and reports removed depth (unless `.err` occurred, in which case `clear_knife()` is NOT called).
     - **Scan-Rotation Preservation Invariant:** Explicit assertion that `set_scan_rotation(0)` is never forced on completion, error, or abort, preserving pre-approach or parent Grid scan rotation.

3. **Offscreen PyQt5 UI Layout & Non-Overlap Check:**
   ```bash
   QT_QPA_PLATFORM=offscreen ~/miniforge3/envs/sbem-py37/bin/python -m pytest tests/test_auto_approach.py -k ui
   ```

---

## 1.4 Unit Test Plan & Doubles Specification (T-006)

This specification defines the unit and hardware-mocked integration test suite in `tests/test_auto_approach.py`. Tests are implemented in `tests/test_auto_approach.py` by each owning implementation task (T-005, T-007..T-011) and must be green before that task's AR-3 code review gate.

### 1.4.1 Test Fixtures & Deterministic Doubles
1. **`MockMicrotomeGatan3View` (`Microtome_Mock` subclass):**
   - Records full chronological call log: `log = List[Tuple[str, Any]]` (`near_knife`, `clear_knife`, `do_full_approach_cut`, `set_stage_z`, `get_stage_z`).
   - Supports configurable failure injection: `fail_on_near: bool`, `fail_on_clear: bool`, `fail_on_cut_index: Optional[int]`, `fail_on_z_read: bool`, `z_mismatch_state: bool`.
   - Simulates DM handshake files: verifies `.ack` is cleared and rewritten on `near_knife`/`clear_knife`; verifies `.ac2` is emitted on nominal cut completion and `.err` emitted on injected faults.
2. **`MockSEM` (`SEM_Mock` subclass):**
   - Records beam-blanking transitions: `beam_blanked_log: List[int]`.
   - Records scan-rotation calls: `scan_rotation_log: List[float]` (asserts `set_scan_rotation(0)` is never called).
   - Generates deterministic synthetic frames on `acquire_frame(width, height, dwell_time)` per tile key.
3. **`MockStage` (`Stage` subclass):**
   - Tracks XY stage moves: asserts XY move is only requested when `microtome.is_knife_clear == True`.
4. **`SyntheticTileGenerator`:**
   - Procedural textured test pattern (Perlin/Gaussian smoothed noise + edge features mimicking biological tissue).
   - Simulates physical perturbations:
     - Independent Poisson-Gaussian shot noise for odd vs. even scan lines.
     - Global brightness/contrast dose drift: $I_{\text{drift}} = a \cdot I + b$ ($a \in [0.8, 1.2], b \in [-30, +30]$).
     - Subpixel stage jitter: `scipy.ndimage.shift(I, (dy, dx))` with $\Delta x, \Delta y \in [-15.0, +15.0]\,\text{px}$.
     - Partial knife shave: cuts off a corner or stripe of pixels, replacing with flat resin intensity ($\mu \approx 40, \sigma \approx 2$).
     - 100% full-surface shave: replaces entire tile with smooth resin + shot noise (zero structural correlation).
     - Blank tile ($I = 0$), saturated tile ($I = 255$), and pure flat noise ($\sigma < 0.5$).

---

### 1.4.2 T-005 Algorithmic Tests (`src/auto_approach.py`)
- **`test_single_scan_odd_even_centroid_coincidence()`**
  - **Task:** T-005 | **AC:** `AC-SBEM-AUTO_APPROACH-001`
  - **Assertion:** Given an impulse image (single non-zero row $y_0$), split into $E_0, O_0$ and compute $\tilde{E}_0, \tilde{O}_0$ per architecture §2.1. Assert the center-of-mass centroids of $\tilde{E}_0$ and $\tilde{O}_0$ coincide to $< 10^{-9}\,\text{px}$ on row $2r + 1.5$.
  - **Assertion:** Assert noise variance amplification factor $(\frac{1}{4})^2 + (\frac{3}{4})^2 = \frac{5}{8} = 0.625$ identically on both halves.
- **`test_single_scan_calibration_pyramid_selection()`**
  - **Task:** T-005 | **AC:** `AC-SBEM-AUTO_APPROACH-001`
  - **Assertion:** High-noise synthetic tile (`0.1 µs` dwell, low SNR) selects $l^* \ge 1$; clean high-SNR tile selects $l^* = 0$.
  - **Assertion:** Output `TileCalibrationProfile` contains `valid=True`, $d_{\text{noise}} \in [0, 0.15]$, and $d_{\text{trigger}} = \min(\max(4 \cdot d_{\text{noise}}, 0.12), 0.45)$.
- **`test_preflight_rejection_blank_saturated_noise()`**
  - **Task:** T-005 | **AC:** `AC-SBEM-AUTO_APPROACH-002`
  - **Assertion:** Blank frame ($\mu \le 1.0$), saturated frame ($\mu \ge 254.0$), and low-contrast flat image ($\sigma < 0.5$) return `TileCalibrationProfile(valid=False, failure_reason=...)`.
  - **Assertion:** Featureless white-noise image (internal SSIM $< 0.85$ across all pyramid levels) returns `valid=False`.
- **`test_bounded_registration_stage_jitter_and_100pct_shave()`**
  - **Task:** T-005 | **AC:** `AC-SBEM-AUTO_APPROACH-001`
  - **Assertion:** Under stage jitter $(\Delta y, \Delta x) = (3.2, -4.1)\,\text{px}$, recovered shift matches within $\pm 0.1\,\text{px}$.
  - **Assertion:** Under 100% full-surface resin shave (correlation collapse), clamp bounds shift to $(0.0, 0.0)$, does not raise IndexError, and yields dissimilarity $d_k > 0.8 \ge d_{\text{trigger}}$ (clean cut detection).
- **`test_dual_ssim_modes_cut_detection_and_dose_drift_invariance()`**
  - **Task:** T-005 | **AC:** `AC-SBEM-AUTO_APPROACH-001`
  - **Assertion:** Under pure brightness/contrast shift ($a=1.2, b=-20$, zero cutting), both `Normalized SSIM` and `Gradient SSIM` evaluate to $d_k < d_{\text{trigger}}$ (zero false contact trigger).
  - **Assertion:** Under a 20% partial surface shave, both modes evaluate to $d_k \ge d_{\text{trigger}}$ (`contact_detected=True`).
- **`test_cyan_magenta_overlay_invariants()`**
  - **Task:** T-005 | **AC:** `AC-SBEM-AUTO_APPROACH-007`
  - **Assertion:** When $I_k == I_{k-1}$ (or identical up to linear brightness scale), composite image satisfies $R = G = B$ (pure grayscale, neutral gray everywhere).
  - **Assertion:** Pixels where structure was removed ($I_{k-1} > I_k$) have $G = 255, B = 255, R < 255$ (pure `#00FFFF` cyan tint).
  - **Assertion:** Pixels where new structure appeared ($I_k > I_{k-1}$) have $R = 255, B = 255, G < 255$ (pure `#FF00FF` magenta tint).

---

### 1.4.3 T-007 Gatan 3View Handshake & Safe-Stop Tests (`src/microtome_control_gatan.py`, `src/microtome_control.py`)
- **`test_microtome_near_clear_handshake_verification()`**
  - **Task:** T-007 | **AC:** `AC-SBEM-AUTO_APPROACH-004`
  - **Assertion:** `near_knife()` and `clear_knife()` verify `.ack` file existence and return `True` on success.
  - **Assertion:** If `.err` is present or `.ack` times out, both methods log error, set `error_state`, and return `False`.
- **`test_microtome_do_full_approach_cut_ac2_verification()`**
  - **Task:** T-007 | **AC:** `AC-SBEM-AUTO_APPROACH-004`, `AC-SBEM-AUTO_APPROACH-005`
  - **Assertion:** Calling `do_full_approach_cut()` verifies `check_cut_cycle_status()` (`.ac2` confirmation).
  - **Assertion:** If `.err` file appears during cut cycle, `do_full_approach_cut()` returns `False` and leaves knife in place.

---

### 1.4.4 T-008 Config & GridManager Tests (`src/default_cfg/default.ini`, `src/config_template.py`, `src/grid_manager.py`)
- **`test_config_counts_and_process_cfg()`**
  - **Task:** T-008 | **AC:** `AC-SBEM-AUTO_APPROACH-008`
  - **Assertion:** `check_number_of_entries()` succeeds asserting `CFG_NUMBER_SECTIONS = 13` and `CFG_NUMBER_KEYS = 254` for `default.ini`, and unchanged 8 sections / 56 keys for `system.cfg`.
  - **Assertion:** `process_cfg()` cleanly parses legacy config lacking `[approach]`, inserting default values without raising KeyError.
  - **Assertion:** Round-trip `AutoApproachConfig` to/from dict preserves all 7 fields (`mode`, `slice_thickness_nm`, `batch_slices`, `max_depth_um`, `probe_tiles`, `dwell_time_override_us`, `ssim_mode`).
- **`test_grid_manager_approach_ref_tiles_sync()`**
  - **Task:** T-008 | **AC:** `AC-SBEM-AUTO_APPROACH-003`
  - **Assertion:** Toggling `approach_active` on `Tile` updates `GridManager.approach_ref_tiles`.
  - **Assertion:** `GridManager.approach_ref_tiles` setter safely filters out-of-bounds (`'0.999'`, `'99.0'`) or malformed keys without crashing or corrupting state.
  - **Assertion:** `GridManager.save_to_cfg()` auto-vivifies `[approach]` if missing, serializes `probe_tiles`, includes `approach_active` tiles with non-zero WD in `wd_stig_params`, and excludes tiles with `wd=0`.
  - **Assertion:** Tile scan parameters (`frame_size_selector`, `pixel_size`, `rotation`, non-zero `wd`, `stig_xy`) are accurately resolved from parent grid.

---

### 1.4.5 T-009 / T-010 GUI Controller Tests (`src/main_controls_dlg_windows.py`, `src/viewport.py`)
- **`test_approach_dlg_controller_and_progress_trigger()`**
  - **Task:** T-009 | **AC:** `AC-SBEM-AUTO_APPROACH-003`, `AC-SBEM-AUTO_APPROACH-006`
  - **Assertion:** `ApproachDlg` instantiates as non-modal `QDialog`; emits `RESTRICT GUI` on Start and `UNRESTRICT GUI` on Stop/Finish.
  - **Assertion:** Engine `progress_callback` puts `(progress, step_record)` onto `utils.Trigger` queue and emits signal without touching Qt widgets from worker thread.
  - **Assertion:** Dialog updates step label, progress bar, and status text on main thread.
- **`test_viewport_approach_tab_and_wheel_scrubbing()`**
  - **Task:** T-010 | **AC:** `AC-SBEM-AUTO_APPROACH-007`
  - **Assertion:** Step index changes update multi-tile Cyan/Magenta canvas on `tab_ap`.
  - **Assertion:** Mouse wheel event increments/decrements step index within $[0, K_{\text{completed}}]$.
  - **Assertion:** Double-click toggles single-tile zoom vs. multi-tile grid view.

---

### 1.4.6 T-011 Cross-Cutting Safety Invariant Tests (`src/auto_approach.py`, `src/main_controls.py`)
- **`test_engine_initial_nominal_z_gate()`**
  - **Task:** T-011 | **AC:** `AC-SBEM-AUTO_APPROACH-002`
  - **Assertion:** When starting from `'Before slice'` (`Clear` inactive), if `stage.z_position is None` or `< 0` or `Error.mismatch_z`, engine halts immediately: **zero calls to `clear_knife()` or `near_knife()`**.
  - **Assertion:** When Z is nominal ($Z \ge 0$, no mismatch), engine commands and verifies `clear_knife()` before any XY moves or SEM grabs.
- **`test_engine_nominal_batch_run_and_max_depth_stop()`**
  - **Task:** T-011 | **AC:** `AC-SBEM-AUTO_APPROACH-004`, `AC-SBEM-AUTO_APPROACH-005`
  - **Assertion:** Nominal 5-slice batch executes: `near_knife()` -> 5x (`do_full_approach_cut()`) -> `clear_knife()` -> XY move -> acquire probe tiles -> evaluate.
  - **Assertion:** When `max_depth_um` ceiling is reached without contact, final batch slice count is capped so accumulated depth never exceeds `max_depth_um`, tiles are evaluated, and engine halts in `SAFETY_LIMIT_REACHED` with knife left in `Clear`.
- **`test_engine_error_knife_freeze_invariant()`**
  - **Task:** T-011 | **AC:** `AC-SBEM-AUTO_APPROACH-005`
  - **Assertion:** When an error is injected at:
    1. Z-stage move / read error,
    2. `near_knife()` timeout or `.err`,
    3. `do_full_approach_cut()` `.err`,
    4. XY stage move error,
    5. SEM grab failure,
    **`clear_knife()` is NEVER called.** Microtome knife call log contains zero `clear_knife()` invocations following the failure. State terminates in `ApproachState.ERROR`.
- **`test_engine_user_abort_clear_after_stroke_down_invariant()`**
  - **Task:** T-011 | **AC:** `AC-SBEM-AUTO_APPROACH-005`
  - **Assertion:** When operator triggers `request_abort()` mid-batch while cut #2 is active:
    1. No further cuts (#3..#5) are scheduled.
    2. Engine awaits cut #2 `.ac2` completion (`Error.none`, confirming `'Stroke Up'` is deactivated and sample lowered below cutting plane).
    3. Only after `.ac2` verified, engine commands and verifies `clear_knife()` (`.ack`).
    4. Engine terminates in `ApproachState.ABORTED` and reports depth removed.
  - **Assertion:** If cut #2 returned `.err` during abort, error rule takes precedence: `clear_knife()` is **NOT** called.
- **`test_engine_scan_rotation_preservation_invariant()`**
  - **Task:** T-011 | **AC:** `AC-SBEM-AUTO_APPROACH-003`, `AC-SBEM-AUTO_APPROACH-005`
  - **Assertion:** For a grid with non-zero rotation (e.g. $45^\circ$), `sem.scan_rotation` is applied during probe tile grab.
  - **Assertion:** On terminal state (`CONTACT_DETECTED`, `SAFETY_LIMIT_REACHED`, `PREFLIGHT_FAILED`, `ABORTED`, `ERROR`), `sem.set_scan_rotation(0)` is **NEVER** called.
- **`test_engine_beam_blanking_transitions()`**
  - **Task:** T-011 | **AC:** `AC-SBEM-AUTO_APPROACH-004`
  - **Assertion:** `sem.set_beam_blanking(1)` is active during all Z moves, Near, batch cuts, Clear, and XY moves; `sem.set_beam_blanking(0)` is active strictly during `acquire_frame()`.
- **`test_engine_manifest_json_persistence()`**
  - **Task:** T-011 | **AC:** `AC-SBEM-AUTO_APPROACH-007`
  - **Assertion:** Run creates `<base_dir>/meta/approach/<timestamp>/manifest.json` containing valid JSON parsing to `AutoApproachConfig`, `TileCalibrationProfile` list, ordered `ApproachStepRecord` list, and final terminal state.
- **`test_main_controls_app_exit_guard_during_approach()`**
  - **Task:** T-011 | **AC:** `AC-SBEM-AUTO_APPROACH-005`
  - **Assertion:** When `self.approach_dlg.auto_approach_in_progress` is True, `MainControls.closeEvent` blocks exit with `QMessageBox.warning` and `event.ignore()`, preventing quitting mid-cut.

---

### 1.4.7 Traceability Matrix

| AC ID | Description | Planned Test Function(s) | Owning Task |
|---|---|---|---|
| `AC-SBEM-AUTO_APPROACH-001` | Pyramidal self-calibration, bounded registration & cut detection | `test_single_scan_odd_even_centroid_coincidence`, `test_single_scan_calibration_pyramid_selection`, `test_bounded_registration_stage_jitter_and_100pct_shave`, `test_dual_ssim_modes_cut_detection_and_dose_drift_invariance` | T-005 |
| `AC-SBEM-AUTO_APPROACH-002` | Pre-flight nominal-Z gate, initial Clear & un-trackable baseline abort | `test_preflight_rejection_blank_saturated_noise`, `test_engine_initial_nominal_z_gate` | T-005, T-011 |
| `AC-SBEM-AUTO_APPROACH-003` | Probe tile selection, grid settings & scan-rotation preservation | `test_grid_manager_approach_ref_tiles_sync`, `test_approach_dlg_controller_and_progress_trigger`, `test_engine_scan_rotation_preservation_invariant` | T-008, T-009, T-011 |
| `AC-SBEM-AUTO_APPROACH-004` | 3View batch cutting, verified Clear & beam blanking interleave | `test_microtome_near_clear_handshake_verification`, `test_microtome_do_full_approach_cut_ac2_verification`, `test_engine_nominal_batch_run_and_max_depth_stop`, `test_engine_beam_blanking_transitions` | T-007, T-011 |
| `AC-SBEM-AUTO_APPROACH-005` | Error knife-freeze, abort Clear-after-stroke-down & max depth stop | `test_engine_nominal_batch_run_and_max_depth_stop`, `test_engine_error_knife_freeze_invariant`, `test_engine_user_abort_clear_after_stroke_down_invariant`, `test_main_controls_app_exit_guard_during_approach` | T-011 |
| `AC-SBEM-AUTO_APPROACH-006` | Non-modal tabbed `ApproachDlg` & manual compatibility | `test_approach_dlg_controller_and_progress_trigger` | T-009 |
| `AC-SBEM-AUTO_APPROACH-007` | Viewport `Approach` tab, Cyan/Magenta overlays & wheel scrub | `test_cyan_magenta_overlay_invariants`, `test_viewport_approach_tab_and_wheel_scrubbing`, `test_engine_manifest_json_persistence` | T-005, T-010, T-011 |
| `AC-SBEM-AUTO_APPROACH-008` | `[approach]` configuration persistence & entry count invariant | `test_config_counts_and_process_cfg` | T-008 |


---

## 2. Simulation Mode Interactive Verification
1. Launch SBEMimage in Simulation Mode (`~/miniforge3/envs/sbem-py37/bin/python src/SBEMimage.py`).
2. In `Viewport`, right-click 2–4 tiles (both active and inactive stack tiles) in an active Grid (including a rotated Grid with non-zero rotation) and toggle `"Select/Deselect tile g.t as approach ref."`; verify `APPROACH` tile labels (and combined `AF + APP` / `GRAD + APP` labels) render cleanly and sync live with the `Reference tiles:` field in non-modal `ApproachDlg` (`Automated` tab).
3. Test editing `Reference tiles:` directly in `ApproachDlg` (verifying Viewport labels update) and test the custom dwell-time override dropdown.
4. Click **Start** on the `Automated` tab while switching to the 4th **`Approach`** tab in `SBEMimage Viewport` (confirming `ApproachDlg` is non-modal while conflicting main controls are restricted).
5. Scroll the **mouse wheel** over the `Approach` tab canvas to scrub back and forth across steps, double-click a tile to zoom/unzoom, and toggle `Cyan-Magenta / Raw`.
6. Click **Abort** during a simulated batch cut: verify no further slices are scheduled, the active cut completes `'Stroke Up'` deactivation, the knife moves to `Clear`, and scan rotation remains unchanged.
7. Verify `Manual` tab still executes classic blind approach without acquiring SEM frames.

---

## 3. Physical Microscope Verification Routine (Gatan 3View + ZEISS SmartSEM)
1. Prepare a sample block (initial post-air-coarse approach or mid-dataset re-approach, starting from either `'Before slice'` or `Clear` with sample Z in nominal state); ensure suitable sample regions are covered by active Grid tiles.
2. Select 2–4 probe tiles as approach reference tiles; set `batch_slices = 5`, `slice_thickness = 100 nm`, `max_depth_um = 20.0`, and fast dwell override (e.g. `0.2` or `0.4 µs`).
3. Confirm nominal Z is verified at Start, knife moves to `Clear` before baseline XY stage moves, SEM beam blanks automatically during each 5-slice `Near` cut batch, and Grid scan rotation is preserved throughout.
4. Test **Abort** safety with knife safely above sample: confirm further cuts stop immediately, active cut finishes deactivating `'Stroke Up'` (sample lowers below cutting plane), and knife moves cleanly to `Clear`.
5. Run to contact: observe live Cyan/Magenta tiles in the Viewport `Approach` tab, verify untouched steps remain neutral gray despite electron dose, and verify immediate stop on first cut on any probe tile.
6. Inspect `<base_dir>/meta/approach/<timestamp>/manifest.json` to compare `Normalized SSIM` vs. `Gradient SSIM` margins on real specimen runs.

---

## 4. Final Verification Summary & Formal Code Review Sign-Off (T-012)

- **Date:** 2026-10-30
- **Branch:** `feat/auto-approach` (tracking `dev-tomgan-rel`)
- **Environment:** STRICT Python 3.7.6 (`~/miniforge3/envs/sbem-py37`)
- **Sign-off Role:** `commit-optimizer` (Task T-012)

### 4.1 Verification Ledger

| Verification Item | Command / Assertion | Result |
|---|---|---|
| **Python 3.7.6 Syntax & Bytecode** | `~/miniforge3/envs/sbem-py37/bin/python -m py_compile src/auto_approach.py src/config_template.py src/grid_manager.py src/microtome_control.py src/microtome_control_gatan.py src/microtome_control_mock.py src/main_controls.py src/main_controls_dlg_windows.py src/viewport.py tests/test_auto_approach.py` | **PASS** (Zero syntax errors, zero Python 3.8+ features) |
| **Full Automated Test Suite** | `QT_QPA_PLATFORM=offscreen ~/miniforge3/envs/sbem-py37/bin/python agent_test.py tests/test_auto_approach.py` | **PASS** (29 passed, 0 failed in 9.79s) |
| **Configuration Invariant Check** | `CFG_NUMBER_SECTIONS = 13`, `CFG_NUMBER_KEYS = 254` checked against `src/default_cfg/default.ini` | **PASS** (13 sections, 254 keys matching constants) |
| **Brownfield DM Script Immutability** | `git diff --exit-code origin/dev-tomgan-rel -- dm/` | **PASS** (Zero modifications to `dm/SBEMimage_DMcom_GMS2.s` and `dm/SBEMimage_DMcom_GMS3.s`) |
| **Acceptance Criteria Coverage** | Traceability matrix (§1.4.7) across `AC-SBEM-AUTO_APPROACH-001` through `008` | **PASS** (100% coverage with 29 automated tests) |

### 4.2 Adversarial Review Gates Ledger

| Gate | Task | Round | Reviewer Model | Verdict | Open Findings |
|---|---|---|---|---|---|
| **AR-1** | Architecture / Spec | 1 | `gemini-4-argon-high` | **PASS** | 0 |
| **AR-2** | T-005 Engine & Pyramidal Calib | 1 | `gemini-4-argon-high` | **PASS** | 0 |
| **AR-2** | T-007 Microtome Handshakes | 1 | `gemini-4-argon-high` | **PASS** | 0 |
| **AR-2** | T-008 Config & Ref Tiles | 1 | `gemini-4-argon-high` | **PASS** | 0 |
| **AR-2** | T-009 ApproachDlg UI | 1 | `gemini-4-argon-high` | **PASS** | 0 |
| **AR-2** | T-010 Viewport Tab & Overlays | 1 | `gemini-4-argon-high` | **PASS** | 0 |
| **AR-2** | T-011 Invariants & Safety | 1 | `gemini-4-argon-high` | **PASS** | 0 |
| **AR-2** | T-012 Help Docs & Release | 2 | `gemini-3.8-flash-high` | **PASS** | 0 |
| **AR-3** | T-005 Implementation | 2 | `gemini-4-argon-high` | **PASS** | 0 |
| **AR-3** | T-007 Implementation | 2 | `gemini-4-argon-high` | **PASS** | 0 |
| **AR-3** | T-008 Implementation | 2 | `gemini-4-argon-high` | **PASS** | 0 |
| **AR-3** | T-009 Implementation | 2 | `gemini-4-argon-high` | **PASS** | 0 |
| **AR-3** | T-010 Implementation | 2 | `gemini-4-argon-high` | **PASS** | 0 |
| **AR-3** | T-011 Implementation | 2 | `gemini-3.8-flash-high` | **PASS** | 0 |

### 4.3 Release Sign-Off
All 12 tasks (T-001 through T-012) are completed, verified against physical domain invariants and acceptance criteria, and fully tested. The automated sample approach slice is approved for merge into `dev-tomgan-rel`.
