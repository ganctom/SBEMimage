# Auto-Approach - Architecture Decisions [IMMUTABLE]

## Metadata [IMMUTABLE]
- **PRD:** `1-prd.md`
- **Clarifications:** `3-clarifications.md`
- **Data Model:** `4-data-model.md`
- **Slice:** `docs/feature-architecture/auto-approach/`

## Constraints [IMMUTABLE]
- **Language / Runtime:** STRICTLY Python 3.7.6 (`~/miniforge3/envs/sbem-py37`).
  - NO walrus operator (`:=`).
  - NO PEP 585 generics (`list[str]`); MUST use `typing.List[str]`.
  - NO PEP 604 unions (`int | None`); MUST use `typing.Optional[int]` or `typing.Union`.
  - NO f-strings with `=` (`f"{var=}"`).
- **Microtome Scope:** Strictly **Gatan 3View** (via unmodified DigitalMicrograph `dm/SBEMimage_DMcom_GMS*.s` scripts) and `Microtome_Mock` for simulation/testing. ConnectomX Katana and other microtomes are out of scope.
- **Deep Interfaces (Ousterhout):** Zero magic thresholds or calibration chores exposed to the operator; self-calibration, bounded registration, and SSIM evaluation are encapsulated inside `src/auto_approach.py`.
- **Dose Minimization:** Strictly 1 baseline frame acquired per probe tile at Iteration 0; SEM beam blanked during all cutting and Z-move intervals.
- **Non-Destructive Knife, Nominal-Z & Scan-Rotation Safety Invariants:**
  1. **Unmodified DM Scripts:** Modifying `dm/SBEMimage_DMcom_GMS2.s` or `dm/SBEMimage_DMcom_GMS3.s` is strictly forbidden.
  2. **Initial Start from `'Before slice'` or `Clear`:** Automated Approach may start with `Clear` inactive (`'Before slice'`), provided sample Z-axis is verified nominal first (valid $Z \ge 0$, no `Error.mismatch_z`, within Z ceiling) before commanding and verifying `Clear` (`.ack`) for baseline imaging.
  3. **On Any Error:** Leave the knife in its current location — NEVER issue an automatic `Clear` on error.
  4. **On User Abort / Stop:** Halt further cuts immediately; wait for any active `MicrotomeStage_FullApproachCut` to finish `.ac2` (confirming `'Stroke Up'` has been deactivated and sample lowered below cutting level without error), then command and verify `Clear` (`.ack`). (If `.err` occurred, rule 3 applies and `Clear` is NOT called.)
  5. **XY Stage Moves:** Only allowed when the knife is verified in `Clear` under nominal operation (`Error.none`).
  6. **Scan Rotation:** Never force-reset scan rotation to `0`; preserve pre-approach scan rotation or the scan rotation defined on the respective probe tile's parent Grid.
- **Configuration Coupling Invariant:** Adding `[approach]` (+1 section, +7 keys) to `src/default_cfg/default.ini` requires updating `CFG_NUMBER_SECTIONS = 13` and `CFG_NUMBER_KEYS = 254` in `src/config_template.py`.
- **Anti-Targets:** Do not modify `dm/*.s` (`SBEMimage_DMcom_GMS2.s`, `SBEMimage_DMcom_GMS3.s`); do not touch `src/microtome_control_katana.py`; do not modify shared SmartSEM wrappers (`sem_get`, `sem_set`, `sem_execute`); do not touch `magc/`.

## Decision Log [LOG]

### AD-AUTO_APPROACH-001: Qt-Free Core Approach & Self-Calibration Engine
- **Date:** 2026-10-29
- **Status:** Accepted
- **Context:** Keeping signal processing, state sequencing, and artifact writing independent of PyQt5 enables deterministic headless unit testing and clean separation of concerns.
- **Decision:** Implement `AutoApproachEngine`, self-calibration functions, SSIM evaluators, and Cyan/Magenta compositing in `src/auto_approach.py` using NumPy, SciPy, OpenCV (`cv2`), and `scikit-image` (`skimage.registration.phase_cross_correlation`, `skimage.metrics.structural_similarity`).
- **Consequences:** 100% of algorithmic and hardware-mocked state machine paths are testable via `agent_test.py tests/test_auto_approach.py` without launching `QApplication`.
- **Links:** `AC-SBEM-AUTO_APPROACH-001`..`005`, `T-005`, `T-006`.

### AD-AUTO_APPROACH-002: Single-Scan Odd/Even Raster Scan-Line Pyramidal Self-Calibration
- **Date:** 2026-10-29
- **Status:** Accepted
- **Context:** Operators must not be burdened with tuning thresholds across varying dwell times (`0.1–3.2 µs`), while cumulative e-beam resin shrinkage prohibits taking multiple baseline scans per tile.
- **Decision:** Split each single baseline frame $I_0$ into even (`I_0[0::2, :]`) and odd (`I_0[1::2, :]`) raster scan lines, aligned onto the common original-row lattice $y = 2r + 1.5$ by mirror-symmetric $\tfrac{1}{4}/\tfrac{3}{4}$ 2-tap vertical interpolation ($\tilde{E}_0[r] = \tfrac{1}{4}E_0[r] + \tfrac{3}{4}E_0[r+1]$, $\tilde{O}_0[r] = \tfrac{3}{4}O_0[r] + \tfrac{1}{4}O_0[r+1]$; exact centroid coincidence, equal noise variance — see `auto-approach_architecture.md` §2.1). Construct a $2\times$ box/Gaussian pyramid $l = 0, 1, \dots, L_{\max}$ (down to minimum side $\ge 64\,\text{px}$) and compute internal structural similarity $\text{SSIM}_{\text{internal}}(l)$ under the selected SSIM mode. Select the finest pyramid scale $l^*$ achieving target internal repeatability ($\text{SSIM}_{\text{internal}}(l^*) \ge 0.94$, or best scale if $\ge 0.85$), recording noise floor $d_{\text{noise}} = 1 - \text{SSIM}_{\text{internal}}(l^*)$. If no pyramid level achieves minimum trackable structure (or frame is blank/saturated), abort **before cutting any slices**. On step $k \ge 1$, declare contact when cross-step dissimilarity $d_k = 1 - \text{SSIM}(I_{k-1}^{(l^*)}, I_k^{(l^*)}) > \max(\kappa \cdot d_{\text{noise}}, d_{\min})$ (treating valid post-cut loss of texture into smooth resin as contact rather than a pre-flight error).
- **Consequences:** Zero user thresholds, strictly 1 baseline scan, automatic adaptation to noisy fast scans, and $4^l\times$ faster registration/SSIM at scale $l^*$.
- **Links:** `AC-SBEM-AUTO_APPROACH-001`, `AC-SBEM-AUTO_APPROACH-002`, `CL-AUTO_APPROACH-007`..`009`.

### AD-AUTO_APPROACH-003: Dual User-Selectable PoC SSIM Modes & Bounded-Shift Registration
- **Date:** 2026-10-29
- **Status:** Accepted
- **Context:** Electron dose shifts raw image brightness/contrast across consecutive scans; stage XY motor repeatability ($\sim 0.5–2.0\,\mu\text{m}$) shifts high-res tiles by tens of pixels; and a 100%-shaved tile loses all correlation with its predecessor.
- **Decision:**
  1. Register $I_k^{(l^*)}$ to $I_{k-1}^{(l^*)}$ via subpixel `phase_cross_correlation(..., upsample_factor=10)`, clamping `(dy, dx)` to $\min(\lceil 5.0\,\mu\text{m} / (\text{px\_nm} \cdot 2^{l^*}) \rceil,\; \lfloor 0.15 \cdot \min(H, W) \rfloor)$ so correlation collapse on a fully shaved tile never causes empty/extreme crops.
  2. Provide two PoC modes selectable in `ApproachDlg`:
     - **Mode 0 (`Normalized SSIM`):** Z-score normalize both registered crops ($\tilde{I} = (I - \mu) / \max(\sigma, \epsilon)$, clipped to $[-4, 4]$) and compute `structural_similarity(..., data_range=8.0)`.
     - **Mode 1 (`Gradient SSIM`):** Compute Sobel gradient magnitude (`cv2.Sobel` + `cv2.magnitude`), normalize by robust scale, and compute `structural_similarity`.
- **Consequences:** Complete immunity to global brightness/gain drift; clean side-by-side PoC evaluation of intensity-normalized structure vs. pure edge structure on real blocks.
- **Links:** `AC-SBEM-AUTO_APPROACH-001`, `CL-AUTO_APPROACH-006`.

### AD-AUTO_APPROACH-004: Gatan 3View Non-Destructive Knife Control, Error Freeze & Safe Abort
- **Date:** 2026-10-29
- **Status:** Superseded by `AD-AUTO_APPROACH-008`
- **Context:** On Gatan 3View, automatically commanding `Clear` when an error has left the knife in `'Before slice'` or when `'Stroke Up'` holds the sample at cutting height can inadvertently cut or shear off specimen tissue. Additionally, legacy `Microtome_Gatan.near_knife()` and `clear_knife()` did not check `.ack`/`.err` files, and `ApproachDlg` did not call `check_cut_cycle_status()` after `do_full_approach_cut()`.
- **Decision:**
  - Scope microtome support strictly to **Gatan 3View** (`src/microtome_control_gatan.py`, `dm/SBEMimage_DMcom_GMS3.s`) and `Microtome_Mock` (`src/microtome_control_mock.py`).
  - Verify `.ack`/`.err` in `near_knife()` and `clear_knife()`, and verify `check_cut_cycle_status()` (`.ac2`/`.err`) after every `do_full_approach_cut()`.
  - **Nominal End-of-Batch Only for `Clear`:** Issue `clear_knife()` ONLY when all cuts in the batch (and their stroke-down + retract phases) succeeded nominally without error or abort. Cap final batch slice count so `max_depth_um` terminates nominally right after tile evaluation (when knife is already `Clear`).
  - **On Any Error:** Do NOT call `clear_knife()` or `near_knife()` — leave the knife in its exact current position, blank the beam, and alert the operator.
  - **On User Abort / Stop:** Stop the knife in its current position, deactivate `'Stroke Up'` (`stroke_down = 1`, `oscillator_off = 1`) to lower the sample below cutting level, do NOT automatically call `clear_knife()`, and report the knife state and removed depth.
  - Keep `sem.set_beam_blanking(1)` throughout all Z moves and cuts; unblank (`0`) only during `acquire_frame`.
- **Consequences:** Eliminates any risk of inadvertent tissue slicing on error or user stop while maintaining fast `Near` batch cutting in nominal runs.
- **Links:** `AC-SBEM-AUTO_APPROACH-004`, `AC-SBEM-AUTO_APPROACH-005`, `CL-AUTO_APPROACH-012`..`016`, `T-007`.

### AD-AUTO_APPROACH-005: Probe Tile Reference Model, Grid-Inherited Settings & Scan-Rotation Preservation
- **Date:** 2026-10-29
- **Status:** Superseded by `AD-AUTO_APPROACH-009`
- **Context:** Automated Approach is used both for initial approach and for mid-dataset re-approach after acquisition pauses, where grids already carry specific scan rotations and optical settings.
- **Decision:** Add `approach_active: bool = False` on `Tile` and `approach_ref_tiles` on `GridManager`, toggleable via Viewport right-click (`"Select/deselect as approach ref."`), `"First & Last active"` preset, or `"g.t"` text box in `ApproachDlg`. Inherit `frame_size_selector`, `pixel_size`, `rotation` (`(360 - theta) % 360` when grid defines rotation, **never resetting scan rotation to `0`** — leaving scan rotation as defined by the grid or pre-approach state), `sx_sy`, and non-zero `wd`/`stig_xy` from `gm[g][t]`, with optional dwell-time override in `ApproachDlg`.
- **Consequences:** Seamless re-approach during paused dataset acquisitions without disturbing active scan rotation.
- **Links:** `AC-SBEM-AUTO_APPROACH-003`, `CL-AUTO_APPROACH-012`, `CL-AUTO_APPROACH-015`.

### AD-AUTO_APPROACH-006: Non-Modal Tabbed `ApproachDlg` + 4th Viewport `Approach` Tab (Cyan/Magenta)
- **Date:** 2026-10-29
- **Status:** Accepted
- **Context:** Modal `ApproachDlg` blocks interaction with `SBEMimage Viewport`; distant probe tiles on a $1\,\text{mm}$ Overview are too small to inspect simultaneously on `tab_mv`; and SSIM charts add unnecessary visual clutter.
- **Decision:**
  1. Convert `ApproachDlg` to `Qt.NonModal` (held as a single instance on `MainControls`, transmitting `RESTRICT GUI` / `UNRESTRICT GUI` while running) with two tabs: `Manual` and `Automated`.
  2. Add a 4th tab `tab_ap` (`Approach`, methods prefixed `ap_`) in `gui/viewport.ui` / `src/viewport.py` rendering an adaptive multi-tile grid of contrast-matched **Cyan/Magenta overlays**:
     $$R = \tilde{I}_k,\quad G = \tilde{I}_{k-1},\quad B = \max(\tilde{I}_{k-1}, \tilde{I}_k)$$
     where $\tilde{I}_{k-1}, \tilde{I}_k \in [0, 255]$ are robust median/IQR-matched registered images (unchanged pixels satisfy $R = G = B$, rendering neutral grayscale without highlight clipping; removed features glow `#00FFFF` Cyan; newly exposed cut structure glows `#FF00FF` Magenta).
  3. Support **mouse-wheel scrolling** across approach steps $0 \dots K$, a bottom step slider + `Cyan-Magenta / Raw` toggle, double-click single-tile zoom, and loading archived runs from `<base_dir>/meta/approach/<timestamp>/`.
- **Consequences:** High-signal, colorblind-safe live visual inspection across all probe tiles simultaneously with zero chart clutter.
- **Links:** `AC-SBEM-AUTO_APPROACH-006`, `AC-SBEM-AUTO_APPROACH-007`, `CL-AUTO_APPROACH-010`.

### AD-AUTO_APPROACH-007: `[approach]` Configuration Persistence Schema
- **Date:** 2026-10-29
- **Status:** Accepted
- **Context:** Session persistence must obey `GEMINI.md` Section 6 configuration invariants.
- **Decision:** Add section `[approach]` with 7 keys (`mode`, `slice_thickness`, `batch_slices`, `max_depth_um`, `probe_tiles`, `dwell_time_override`, `ssim_mode`) to `src/default_cfg/default.ini`, updating `CFG_NUMBER_SECTIONS = 13` (from `12`) and `CFG_NUMBER_KEYS = 254` (from `247`) in `src/config_template.py`.
- **Consequences:** Automatic upgrade of legacy `.ini` configs via `process_cfg()` and verified startup integrity.
- **Links:** `AC-SBEM-AUTO_APPROACH-008`, `T-008`.

### AD-AUTO_APPROACH-008: Unmodified DM Scripts, Nominal-Z Start from `'Before slice'`, and Clear-After-Stroke-Down on Abort
- **Date:** 2026-10-29
- **Status:** Accepted (Supersedes `AD-AUTO_APPROACH-004`)
- **Context:** Modifying `dm/SBEMimage_DMcom_GMS2.s` / `dm/SBEMimage_DMcom_GMS3.s` is strictly forbidden. Operators may start Automated Approach with the knife in `'Before slice'` (`Clear` inactive), and on user `Abort` want the knife moved to `Clear` *after* `'Stroke Up'` has been deactivated, while keeping the knife frozen in place on any error.
- **Decision:**
  1. **Zero DM Script Changes:** All Gatan 3View interactions use existing DM commands (`MicrotomeStage_Near`, `MicrotomeStage_Clear`, `MicrotomeStage_FullApproachCut`, `MicrotomeStage_GetPositionZ`, `MicrotomeStage_SetPositionZ_Confirm`, `MicrotomeStage_SetPositionXY_Confirm`), adding `.ack`/`.err` verification to `Microtome_3View.near_knife()` and `clear_knife()` and calling `check_cut_cycle_status()` (`.ac2`/`.err`) after every `do_full_approach_cut()`.
  2. **Initial Start Sequence:** Verify sample Z-axis is nominal first (`z_position is not None`, `z_position >= 0`, `error_state != Error.mismatch_z`, within Z ceiling; aborting with zero knife movement if Z is non-nominal). Once Z is verified nominal, command and verify `clear_knife()` (`.ack`) so starting from `'Before slice'` safely clears the knife prior to baseline XY moves and SEM grabs.
  3. **User Abort Sequence:** Set `aborted = True` to prevent scheduling any further cuts. If a `MicrotomeStage_FullApproachCut` is currently executing in DM, await `check_cut_cycle_status()`: `.ac2` confirmation (`Error.none`) guarantees DM has executed `stroke_down = 1, oscillator_off = 1` (deactivating `'Stroke Up'` and lowering the sample below cutting level) and completed retract. Only after `Error.none` confirmation, command and verify `clear_knife()` (`.ack`) and report removed depth.
  4. **Error Freeze:** On any `.err`, timeout, Z mismatch, or stage/SEM error (`error_state != Error.none`), **never** call `clear_knife()` — leave the knife in its current location.
- **Consequences:** 100% compatible with deployed `GMS2`/`GMS3` DM scripts on existing 3View microscopes while enforcing safe Z-lowered `Clear` on both initial `'Before slice'` start and user `Abort`, and strict knife-freeze on any error.
- **Links:** `AC-SBEM-AUTO_APPROACH-002`, `AC-SBEM-AUTO_APPROACH-004`, `AC-SBEM-AUTO_APPROACH-005`, `CL-AUTO_APPROACH-017`..`019`, `T-007`.

### AD-AUTO_APPROACH-009: 1:1 Autofocus-Style Probe Tile Selection UX (No Preset or Clear Buttons)
- **Date:** 2026-10-29
- **Status:** Accepted (Supersedes `AD-AUTO_APPROACH-005`)
- **Context:** Operators already select autofocus and focus-gradient reference tiles via the Viewport right-click menu (`_vp_toggle_tile_autofocus`) and a comma-separated `Reference tiles:` `QLineEdit` in `AutofocusSettingsDlg`. Extra `"First & Last active"` or `"Clear"` buttons add unfamiliar UI clutter.
- **Decision:**
  1. Add `approach_active: bool = False` on `Tile` and `approach_ref_tiles` property/setter on `GridManager` mirroring `autofocus_ref_tiles`, allowing any tile (active or inactive for stack acquisition) inside an active Grid to be selected.
  2. In `Viewport` (`tab_mv`), add right-click context action `"Select tile g.t as approach ref."` / `"Deselect tile g.t as approach ref."` alongside autofocus and focus-gradient ref actions, and render `APPROACH` on `vp_draw` (combining cleanly as `AF + APP` / `GRAD + APP` / `GRAD + AF + APP` when shared).
  3. In non-modal `ApproachDlg` (`Automated` tab), provide a `Reference tiles:` `QLineEdit` synced live bidirectionally with `gm.approach_ref_tiles` (with no `"First & Last"` or `"Clear"` buttons).
  4. Inherit `frame_size_selector`, `pixel_size`, `rotation` (`(360 - theta) % 360` when grid defines rotation, **never resetting scan rotation to `0`**), `sx_sy`, and non-zero `wd`/`stig_xy` from `gm[g][t]`, with optional dwell-time override in `ApproachDlg`.
- **Consequences:** Familiar, muscle-memory-compatible SBEMimage UX with live non-modal synchronization between `Viewport` and `ApproachDlg`.
- **Links:** `AC-SBEM-AUTO_APPROACH-003`, `CL-AUTO_APPROACH-020`, `T-008`, `T-009`, `T-010`.

## Module Routing Table [MUTABLE]

| Responsibility | Target path | Owner task |
|---|---|---|
| Self-calibrating pyramidal SSIM engine, bounded registration, Cyan/Magenta compositor, artifact writer & state machine | `src/auto_approach.py` | T-005 |
| Unit test plan (per-task test lists & doubles); tests are implemented by each owning implementation task in `tests/test_auto_approach.py` | `verification.md` (plan), `tests/test_auto_approach.py` (code) | T-006 (plan) / T-005, T-007..T-011 (code) |
| Gatan 3View `.ack`/`.ac2`/`.err` handshake verification in Python (`dm/*.s` untouched) + `Microtome` / `Microtome_Mock` support | `src/microtome_control.py`, `src/microtome_control_gatan.py`, `src/microtome_control_mock.py` | T-007 |
| `[approach]` config defaults, `CFG_NUMBER_SECTIONS`/`CFG_NUMBER_KEYS` update & `GridManager` `approach_ref_tiles` | `src/default_cfg/default.ini`, `src/config_template.py`, `src/grid_manager.py` | T-008 |
| Non-modal tabbed `ApproachDlg` UI & controller (`Manual` + `Automated` tabs) | `gui/approach_dlg.ui`, `src/main_controls_dlg_windows.py`, `src/main_controls.py` | T-009 |
| 4th Viewport `Approach` tab (`ap_`), Cyan/Magenta multi-tile grid, wheel series scrubbing & Viewport ref-tile badge/menu | `gui/viewport.ui`, `src/viewport.py` | T-010 |
| Cross-cutting non-destructive error freeze, safe abort Clear-after-Stroke-Down, scan-rotation preservation & `manifest.json` persistence | `src/auto_approach.py`, `src/main_controls.py`, `src/main_controls_dlg_windows.py` | T-011 |
| User manual, final architecture polish, code review & squash merge | `docs/auto_approach_help.md`, `docs/feature-architecture/auto-approach/` | T-012 |
