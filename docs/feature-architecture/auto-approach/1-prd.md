# Feature PRD: Automated Sample Approach [IMMUTABLE]

Feature ID: PROD-SBEM-AUTO_APPROACH
Owner: Spec Owner & Software Architect
Status: Draft (Under User Review)
Date: 2026-10-29
Implementation Order: Step 1
Feature Context: Brownfield
Platform Context: Existing stack
Tech Decision Posture: Fixed (Python 3.7.6, PyQt5, ZEISS SmartSEM, Gatan 3View DM)

## 1. Problem Statement and Value [IMMUTABLE]
- **Context:** In Serial Block-Face Electron Microscopy (SBEM), operators need to approach the diamond knife to the sample surface not only after mounting a new or re-trimmed sample block (following coarse approach in air), but also whenever an automated **re-approach** is required after an acquisition pause, chamber vent, thermal drift, or cutting issues experienced during dataset acquisition. Manually approaching forces operators to cut blind slice batches, clear the knife, manually acquire images, visually judge whether the knife has begun cutting the sample surface, and repeat.
- **Impact of Not Doing It:** Manual approach and re-approach waste significant operator and microscope time, risk over-cutting into valuable specimen volume on the highest region of the block face, and rely on subjective visual inspection under electron-dose-induced image intensity changes.
- **Value Proposition:** A threshold-free, self-calibrating Automated Sample Approach MVP/PoC for Gatan 3View systems that interleaves batched approach cuts with high-resolution probe-tile SEM imaging, automatically detects the first physical cut on **any** operator-selected probe tile without user threshold tuning, halts immediately, and lets the operator inspect the approach series via live contrast-matched Cyan/Magenta overlays in a dedicated Viewport tab.

## 2. In Scope [IMMUTABLE]
- **Probe Tile Selection (`g.t`, 1:1 Autofocus Ref Pattern):** Operators select suitable high-resolution probe tiles (any active or inactive tile within an active Grid) via Viewport right-click (`"Select/Deselect tile g.t as approach ref."` with `APPROACH` Viewport tile label, matching Autofocus reference tiles) or via the live-synced `Reference tiles:` (`"g.t"`) field in `ApproachDlg` (no preset or clear buttons).
- **Grid-Inherited Scan Settings + Optional Dwell Override:** Frame size, pixel size, scan rotation, XY stage coordinates, and Working Distance / stigmation (when non-zero on tile) are inherited from each probe tile's parent Grid; dwell time defaults to `"Inherit from grid"` with an optional custom dwell-time override dropdown in `ApproachDlg` to minimize electron dose and resin Z-shrinkage.
- **Strictly Single-Scan Self-Calibrating Pyramidal SSIM Engine:**
  - Acquires **strictly 1 baseline frame** per probe tile at Start (minimum electron dose).
  - Automatically selects each tile's optimal $2\times$ pyramid denoising scale $l^*$ and internal noise floor using single-frame odd vs. even raster scan-line structural similarity (`I[0::2, :]` vs. `I[1::2, :]`).
  - Pre-flight aborts **before cutting any slices** if any selected probe tile fails image validity or cannot reach reliable SNR across the pyramid (blank, saturated, or insufficient trackable surface texture).
  - Supports two user-selectable PoC SSIM modes without exposing manual numeric thresholds:
    1. **Normalized SSIM:** Denoised, bounded-shift subpixel registered, z-score normalized whole-tile SSIM (invariant to dose-induced brightness/contrast drift).
    2. **Gradient SSIM:** Denoised, bounded-shift subpixel registered spatial-gradient magnitude whole-tile SSIM (pure edge/topography comparison).
  - Stops approach immediately as soon as a cut is detected on **any** probe tile.
- **Gatan 3View Verified Batch Cutting, Safe Abort & Interleave (Unmodified DM Scripts):**
  - Supports starting even from `'Before slice'` (`Clear` not active) as well as `Clear`: first verifies that the **sample Z-axis is in a nominal state** (valid $Z \ge 0$, no `Error.mismatch_z`, within Z range ceiling; halting without moving the knife if Z is non-nominal), then commands and verifies `Clear` (`.ack`) before baseline XY moves and imaging.
  - Blanks electron beam during cutting and unblanks only during frame acquisition.
  - Cuts batches of $K$ slices (capped on the final batch so accumulated depth never exceeds `max_depth_um`) at thickness $T\,\text{nm}$ in `Near` position with verified `.ac2`/`.err` DM handshake on Gatan 3View; after all cuts in the batch complete nominally without error, commands and verifies `Clear` (`.ack`) before moving XY stage to acquire and evaluate probe tiles.
  - Safe `Abort` sequence (without modifying `dm/*.s`): immediately halts further cuts; if an active `MicrotomeStage_FullApproachCut` cycle is in flight, waits for it to finish and verify `.ac2` (confirming `'Stroke Up'` has been deactivated and sample lowered below cutting level), then moves the knife to `Clear` (`.ack` verified) and reports removed depth.
- **Hard Max Total Depth Safety Stop:** Configurable `max_depth_um` limit stopping approach cleanly once the permitted Z travel is reached.
- **Non-Modal Tabbed `ApproachDlg`:** Extends `gui/approach_dlg.ui` with `Manual` (legacy blind slice removal) and `Automated` tabs; runs non-modally using SBEMimage's `RESTRICT GUI` lock while active so the Viewport window remains interactive.
- **4th Viewport Tab (`Approach`) with Cyan/Magenta Live Series Viewer:**
  - Displays an auto-sized multi-tile grid of contrast-matched **Cyan/Magenta overlays** (`Neutral Gray` = unchanged structure, `Cyan` = pre-cut features removed, `Magenta` = newly exposed cut structure; no SSIM graphs).
  - Supports **mouse-wheel scrolling** through the approach step series, bottom step slider + `Cyan-Magenta / Raw` toggle, double-click to zoom an individual probe tile, and loading/viewing archived runs from `meta/approach/<timestamp>/`.
- **Configuration Persistence:** Persists `[approach]` settings in `src/default_cfg/default.ini` strictly coupled with `CFG_NUMBER_SECTIONS` (`12 -> 13`) and `CFG_NUMBER_KEYS` (`247 -> 254`) in `src/config_template.py`.

## 3. Out of Scope [IMMUTABLE]
- Support for ConnectomX Katana, GCIB, or other non-Gatan 3View microtome systems.
- Modifying Gatan DigitalMicrograph scripts (`dm/SBEMimage_DMcom_GMS2.s`, `dm/SBEMimage_DMcom_GMS3.s`).
- Exposing manual SSIM/difference threshold spinboxes or requiring manual calibration runs from the operator.
- Random rotating probe-tile subsets per batch (deferred beyond MVP).
- SSIM trend plots/charts in the GUI (intentionally excluded to avoid visual/information overload).
- Automated sample tilt leveling or post-contact full-block planing modes.
- Modifying shared SmartSEM low-level wrappers (`sem_get`, `sem_set`, `sem_execute`) or touching `magc/`.

## 4. Data Inputs & Non-Functional Needs [MUTABLE]
- **Primary Sources:** High-resolution SEM tile frames saved per step in `<base_dir>/meta/approach/<timestamp>/`.
- **Target Runtime:** STRICT Python 3.7.6 (`~/miniforge3/envs/sbem-py37`). No walrus (`:=`), no PEP 585 (`list[str]`), no PEP 604 (`int | None`), no `f"{var=}"`.
- **Dose & Shrinkage Minimization:** Strictly 1 baseline scan per probe tile before Batch 1; beam blanked (`set_beam_blanking(1)`) throughout all cutting/Z-move intervals.
- **Stage Jitter & Full-Shave Safety:** Subpixel `phase_cross_correlation` shift is bounded to physical stage repeatability ($\pm 5\,\mu\text{m}$ clamped to $\le 15\%$ of image dimensions) so a 100%-shaved tile with zero remaining correlation never produces wild crops or crashes.
- **Fail-Safe Integrity:**
  - **Initial Z Nominal Check Before Any Knife Move:** Approach may start from `'Before slice'` (`Clear` not active) or `Clear`; before commanding initial `Clear` for baseline imaging, the procedure MUST verify sample Z-axis is nominal (valid $Z \ge 0$, no `Error.mismatch_z`, within stage Z limits).
  - **On Any Error:** The knife **MUST stay in its current location** — automatic `Clear` is strictly forbidden on error, because clearing the knife while in a faulted `'Before slice'` / raised-sample state can shear off tissue from the sample.
  - **On User Abort / Stop:** Immediately halt scheduling further slices; once any in-flight `MicrotomeStage_FullApproachCut` finishes nominally (`.ac2` verified, guaranteeing `'Stroke Up'` has been deactivated and the sample is lowered below cutting level), command and verify `Clear` (`.ack`) and report total depth removed. (If an error occurred during the active cycle, error rules take precedence and `Clear` is NOT called.)
  - **Scan Rotation Preservation:** Scan rotation **MUST NOT be reset to `0`**; it remains in whatever state it was prior to approach or as defined by the respective probe tile's parent Grid.
  - **Beam Blanking:** SEM beam is blanked (`set_beam_blanking(1)`) whenever frame acquisition is not actively running.

## 5. Dependency & Downstream Analysis [MUTABLE]
- **Upstream:** `Microtome_3View` / `Microtome_Mock` (`src/microtome_control_gatan.py`, `src/microtome_control_mock.py`; communicating with unmodified `dm/SBEMimage_DMcom_GMS*.s`), `Stage` (`src/stage.py`), `SEM` (`src/sem_control*.py`), `GridManager` (`src/grid_manager.py`), `ImageInspector` (`src/image_inspector.py`).
- **Downstream:** `MainControls` (`src/main_controls.py`), `ApproachDlg` (`src/main_controls_dlg_windows.py`), `Viewport` (`src/viewport.py`, `gui/viewport.ui`).

## 6. Compatibility & Rollout [MUTABLE]
- **Existing Consumers:** `MainControls.open_approach_dlg()`, `Viewport`.
- **Compatibility Expectation:** Must keep backward compatibility for Manual blind slice removal (`ApproachDlg` Manual tab), existing 3 Viewport tabs, and unmodified `dm/SBEMimage_DMcom_GMS*.s` scripts.
- **Versioning / Contract Stability:** Internal SBEMimage Python modules only (`dm/*.s` untouched); backward-compatible config upgrade via `process_cfg()`.
- **Migration / Rollout:** Direct integration behind the `Automated` tab of `ApproachDlg` and 4th `Approach` tab of `Viewport`.
- **Data Migration:** Automatic default injection for existing session `.ini` files via `config_template.process_cfg()`.
- **Fallback / Rollback:** Clicking `Abort` immediately stops scheduling further slices, waits for any active cut cycle to finish deactivating `'Stroke Up'` (`.ac2` verified, lowering the sample below cutting level), moves the knife to `Clear` (`.ack` verified), and reports total depth removed (unless a hardware/DM error occurred, in which case the knife stays in its current position).

## 7. Domain & Abstraction Insights [MUTABLE]
- **Dose-Drift Invariance:** Cumulative electron dose alters raw image intensity across repeated scans of the same probe location, making z-score-normalized SSIM and gradient-magnitude SSIM reliable where raw intensity subtraction would drift; it is the operator's responsibility to place probe tiles on suitable sample areas.
- **Odd/Even Raster Scan-Line Self-Calibration:** Adjacent SEM raster lines (`y` even vs. `y` odd) have temporally independent shot/amplifier noise while sampling the same physical surface structure (up to a $0.5\,\text{px}$ vertical offset), enabling single-image SNR & pyramid-scale calibration with zero extra electron dose.
- **Baseline ($k=0$) vs. Post-Cut ($k \ge 1$) Asymmetry:** Insufficient trackable texture at $k=0$ indicates an unsuitable probe area or focus/beam issue (must abort before cutting), whereas disappearance of calibrated $k-1$ surface structure at $k \ge 1$ (on a valid non-blank grab) is a genuine physical cut.
- **Gatan 3View Knife & Stroke-Up Sequencing:** Clearing the knife is safe once sample Z is nominal and `'Stroke Up'` is deactivated (`stroke_down = 1`, which `MicrotomeStage_FullApproachCut` guarantees upon `.ac2` completion), allowing both starting from `'Before slice'` after verifying nominal Z and clearing the knife on user `Abort` after the active cut completes `.ac2`. Conversely, on any hardware/DM error (`.err` or Z mismatch), `'Stroke Up'` or knife position cannot be trusted, so the knife MUST stay in place without clearing.

## 8. Execution Ownership [MUTABLE]
- **Spec Owner / Software Architect:** PRD, ADL, Clarifications, Contracts, Domain Knowledge, Task DAG.
- **Unit Test Planner / Implementation Engineer:** `src/auto_approach.py`, `tests/test_auto_approach.py`, Gatan 3View handshake & safe-stop support, config coupling, `ApproachDlg`, and `Viewport` Approach tab.
- **Crosscutting / Commit Optimizer:** Fail-safe guards, structured run artifacts, user manual docs, code review, and squash merge.

## 9. Acceptance Criteria [MUTABLE]

- **AC-SBEM-AUTO_APPROACH-001 - Self-Calibrating Pyramidal Cut Detection (Stop on First Touch)**
  - **Scenario:** Given 1 or more operator-selected probe tiles and either `Normalized SSIM` or `Gradient SSIM` mode selected, when a single baseline scan calibrates each tile's pyramid scale $l^*$ and noise floor from odd/even scan lines and a subsequent cut batch alters surface structure on **any** probe tile, then the engine detects the structural drop without user thresholds, halts further cutting (with knife already in `Clear` for tile imaging and scan rotation preserved), and reports which tile(s) detected contact.
  - **Deliverables:**
    - Implementation: `src/auto_approach.py` (`calibrate_tile_single_scan`, `evaluate_tile_pair`, `AutoApproachEngine`).
    - Unit tests: `tests/test_auto_approach.py` covering surface structural cuts, dose brightness/contrast drift immunity, bounded-shift registration under stage jitter, and 100%-tile shave stability.

- **AC-SBEM-AUTO_APPROACH-002 - Pre-Flight Nominal Z Check, Initial Clear & Un-Trackable Baseline Abort**
  - **Scenario:** Given the operator clicks Start in Automated Approach (with the knife starting in either `'Before slice'` or `Clear`), when EHT is off, probe tiles are empty/out of stage limits, or sample Z-axis is non-nominal (`None`, `< 0`, `Error.mismatch_z`, or exceeding Z range), then the system aborts **before moving or clearing the knife**; when sample Z is verified nominal, it commands and verifies `Clear` before XY stage motion, acquires 1 baseline scan per probe tile, and aborts **before cutting any slices** if any baseline scan is blank, saturated, or fails to reach target internal odd/even SNR across all pyramid levels.
  - **Deliverables:**
    - Implementation: Pre-flight nominal-Z gate, verified initial `Clear`, and Iteration-0 calibration gate in `src/auto_approach.py` and `ApproachDlg`.
    - Unit tests: `tests/test_auto_approach.py` asserting zero knife moves on non-nominal Z, verified `clear_knife()` before baseline XY move when Z is nominal, and zero cuts on pure-noise, blank, or saturated baseline images.

- **AC-SBEM-AUTO_APPROACH-003 - Probe Tile Selection (Autofocus Ref Pattern) & Grid-Inherited Scan Settings with Dwell Override**
  - **Scenario:** Given active Grids in `GridManager`, when the operator right-clicks any tile `g.t` (active or inactive for stack acquisition) in the Viewport context menu to toggle `"Select/Deselect tile g.t as approach ref."` or edits the `Reference tiles:` (`"g.t"`) field in `ApproachDlg`, then the probe set syncs live between Viewport `APPROACH` tile labels (combining cleanly with `AF`/`GRAD` labels when shared) and `ApproachDlg`, inheriting each tile's parent Grid frame size, pixel size, scan rotation (without resetting scan rotation to `0`), XY, and non-zero WD/stig while applying either the Grid's dwell time or the user's custom dwell-time override.
  - **Deliverables:**
    - Implementation: `src/grid_manager.py`, `src/viewport.py`, `src/main_controls_dlg_windows.py`, `gui/approach_dlg.ui`.
    - Unit tests: `tests/test_auto_approach.py` verifying active/inactive tile resolution in active grids, bidirectional `approach_ref_tiles` sync, scan-rotation preservation, and dwell-time inheritance vs. override.

- **AC-SBEM-AUTO_APPROACH-004 - Nominal Gatan 3View Batch Cutting, Verified Clear & Beam Blanking Interleave**
  - **Scenario:** Given batch size $K$ and slice thickness $T\,\text{nm}$ on Gatan 3View (or `Microtome_Mock`), when Automated Approach runs nominally, then the SEM beam is blanked during all cutting moves, the knife executes $K$ verified approach cuts in `Near` (`.ac2`/`.err` checked), verifies transition to `Clear` before any XY stage motion, unblanks the beam to acquire probe tiles, and re-blanks the beam.
  - **Deliverables:**
    - Implementation: `src/auto_approach.py`, `src/microtome_control_gatan.py`, `src/microtome_control_mock.py`.
    - Unit/Integration tests: `tests/test_auto_approach.py` verifying nominal call ordering and beam-blanking transitions.

- **AC-SBEM-AUTO_APPROACH-005 - Error Knife-Freeze, Safe Abort Clear (After Stroke-Up Deactivation) & Max Depth Stop**
  - **Scenario:**
    1. When `max_depth_um` is reached nominally without contact, the final batch is capped to not exceed `max_depth_um`, tiles are evaluated, and approach stops cleanly with a max-depth alert.
    2. When **any error** occurs during Z readout/move, Near/Clear, cutting, XY move, or SEM grab, execution halts immediately, **the knife stays in its current location (no `Clear` command issued)**, scan rotation is NOT reset to `0`, and the error is reported.
    3. When the operator clicks **Abort**, further cuts are immediately halted; once any in-flight `MicrotomeStage_FullApproachCut` finishes nominally (`.ac2` verified so `'Stroke Up'` is deactivated and the sample is lowered below cutting level), the knife moves to **`Clear`** (`.ack` verified), scan rotation is preserved, and total depth removed is reported. (If an error occurred on that active cut, rule 2 applies and `Clear` is NOT called.)
    4. **Abort During Probe Tile Acquisition (Baseline or Step):**
       - **Gherkin Acceptance:**
         ```gherkin
         Scenario: Operator aborts automated approach during reference tile acquisition
           Given Automated Approach has been successfully initialized and is running
           When the operator presses the Abort button
           Then the automated procedure shall stop cleanly without acquiring any remaining approach reference tiles
           And if the Abort button is pressed during the SEM acquisition of an approach reference tile, that active tile acquisition shall complete and beam blank before cleanly aborting
         ```
       - When the operator clicks **Abort** during reference tile acquisition (either at baseline step 0 or during post-batch evaluation step $k$):
         - If an SEM tile frame acquisition is currently in-flight, it is allowed to complete nominally and the electron beam is immediately blanked in `finally`.
         - Further stage moves and image acquisitions for all remaining probe tiles in that step are stopped immediately.
         - Knife position is preserved in `Clear`, scan rotation is preserved, and no further cuts or stage moves are commanded.
  - **Deliverables:**
    - Implementation: `src/auto_approach.py`, `src/microtome_control_gatan.py` (`dm/*.s` untouched), `src/main_controls_dlg_windows.py`.
    - Unit tests: `tests/test_auto_approach.py` explicitly asserting `clear_knife()` is NEVER called on error, IS called on nominal user abort only after active cut `.ac2` completion (Stroke-Up deactivated), and `set_scan_rotation(0)` is never forced.

- **AC-SBEM-AUTO_APPROACH-006 - Non-Modal Tabbed `ApproachDlg` & Manual Mode Compatibility**
  - **Scenario:** Given `ApproachDlg` is opened, when the user operates the `Manual` tab, blind slice removal remains supported; when running `Automated` mode, `ApproachDlg` stays non-modal (using `RESTRICT GUI` to lock conflicting controls) so the user can interact with the `SBEMimage Viewport` live.
  - **Deliverables:**
    - GUI & controller: `gui/approach_dlg.ui`, `src/main_controls.py`, `src/main_controls_dlg_windows.py`.

- **AC-SBEM-AUTO_APPROACH-007 - Viewport `Approach` Tab with Cyan/Magenta Live Overlays & Wheel Scrubbing**
  - **Scenario:** Given an active or completed Automated Approach run saved under `meta/approach/<timestamp>/`, when the user views the 4th `Approach` tab in `SBEMimage Viewport`, then all probe tiles are rendered in an auto-sized multi-tile grid as contrast-matched **Cyan/Magenta overlays** (neutral gray where unchanged, cyan/magenta where cut, no SSIM graphs), supporting **mouse-wheel scrolling** through approach steps, slider/raw toggle, and double-click single-tile zoom.
  - **Deliverables:**
    - GUI & rendering: `gui/viewport.ui`, `src/viewport.py` (`ap_` methods), `src/auto_approach.py` (`compose_cyan_magenta_overlay`).
    - Unit tests: `tests/test_auto_approach.py` verifying neutral-gray identity under uniform brightness/contrast shifts and pure cyan/magenta channel mapping on structural differences.

- **AC-SBEM-AUTO_APPROACH-008 - `[approach]` Configuration Persistence & Entry Count Invariant**
  - **Scenario:** Given `[approach]` keys added to `src/default_cfg/default.ini`, when `check_number_of_entries()` and `process_cfg()` run at startup, then validation passes with `CFG_NUMBER_SECTIONS = 13` and `CFG_NUMBER_KEYS = 254` in `src/config_template.py`.
  - **Deliverables:**
    - Config files & test: `src/default_cfg/default.ini`, `src/config_template.py`, `tests/test_auto_approach.py`.

- **AC-SBEM-AUTO_APPROACH-009 - Live Refresh of the Approach UI in Viewport**
  - **Scenario:**
    ```gherkin
    Scenario: Live refresh of Approach Tab during ongoing approach
      Given automated approach is ongoing
      When processing or acquisition of any approach reference tile is done
      Then all relevant GUI items in the Approach Tab in Viewport shall immediately refresh (image, approach controls)
    ```
  - **Deliverables:**
    - Implementation: `src/auto_approach.py` (intermediate tile callback), `src/viewport.py` (`ap_update_live_step` / `ap_draw`).
    - Unit tests: `tests/test_auto_approach.py` asserting intermediate progress callback invocation per tile.

- **AC-SBEM-AUTO_APPROACH-010 - Present Registered Tile Series in the Approach Tab**
  - **Scenario:**
    ```gherkin
    Scenario: Present registered tile series in the Approach Tab
      Given the user inspects approach images in the Approach Tab in Viewport
      When the user scrolls through the series by mouse or by slider in Approach Controls
      Then every image series shall be presented in an aligned form registered to the baseline
      And the registered view shall apply to both Raw and Cyan/Magenta modes
    ```
  - **Deliverables:**
    - Implementation: `src/viewport.py` (`ap_draw` subpixel alignment using `shift_yx_px`).
    - Unit tests: `tests/test_viewport_approach.py` verifying aligned image presentation during step scrubbing.

## 10. Execution Plan [MUTABLE]
- Phase 1: Specification, Architecture, Contracts & Test Scenarios (see `5-tasks.md` T-001..T-004).
- Phase 2: Self-Calibrating Engine, Cyan/Magenta Compositor, Gatan 3View Safe-Stop/Handshake & Config Coupling (see `5-tasks.md` T-005..T-008).
- Phase 3: Non-Modal Tabbed `ApproachDlg` & Viewport `Approach` Tab Integration (see `5-tasks.md` T-009..T-011).
- Phase 4: Verification, User Documentation & Squash Release (see `5-tasks.md` T-012).

## 11. Test Strategy [MUTABLE]
- **Unit (`tests/test_auto_approach.py`):** Odd/even scan-line pyramidal SNR calibration, featureless/blank pre-flight rejection, `Normalized SSIM` and `Gradient SSIM` under simulated dose drift + stage jitter + partial/full cuts, Cyan/Magenta compositing invariants, and `check_number_of_entries()` config test.
- **Integration (`tests/test_auto_approach.py`):** State-machine execution over mocked `SEM` / `Microtome` / `Stage` verifying nominal-Z check before initial `Clear`, single baseline grab, beam blanking, nominal `Near -> K cuts -> verified Clear -> XY move` ordering, **zero `clear_knife()` calls on any error**, verified `clear_knife()` on user abort after active cut `.ac2` (Stroke-Up deactivated), scan-rotation preservation, and `max_depth_um` stop.
- **Manual / Microscope (`verification.md`):** Offscreen PyQt UI layout verification, simulation-mode end-to-end wheel scrubbing in the Viewport `Approach` tab, and physical Gatan 3View + SmartSEM approach/re-approach validation.

## 12. Risks & Constraints [MUTABLE]
- **Inadvertent Slice / Tissue Loss from Unsafe Knife Clear:** Calling `Clear` when sample Z is faulted or while `'Stroke Up'` holds the sample at cutting height can cut off sample tissue. Mitigated by verifying sample Z is nominal before initial `Clear`, never calling `Clear` on any error, and on user `Abort` waiting for the active `MicrotomeStage_FullApproachCut` `.ac2` confirmation (`'Stroke Up'` deactivated) before moving to `Clear`.
- **Electron-Beam Resin Shrinkage:** Mitigated by strictly 1 baseline scan, optional fast dwell-time override, batched cuts, and beam blanking between scans.
- **Dose-Induced Intensity Drift:** Mitigated by z-score normalization / spatial gradient extraction before both SSIM evaluation and Cyan/Magenta rendering.
