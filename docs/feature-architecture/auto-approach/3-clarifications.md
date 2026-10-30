# Auto-Approach - Clarifications [IMMUTABLE]

## Metadata [IMMUTABLE]
- **PRD:** `1-prd.md`
- **ADL:** `2-adl.md`
- **Slice:** `docs/feature-architecture/auto-approach/`

## Mandatory Questions Coverage Map [IMMUTABLE]
1. **Feature context:** `answered` — Brownfield (extending existing SBEMimage approach workflow in `ApproachDlg`).
2. **Platform context:** `answered` — Existing stack (Python 3.7.6, PyQt5, numpy, scipy, skimage/cv2, Zeiss SmartSEM, Gatan 3View DM microtome; Katana out of scope).
3. **Tech decision posture:** `answered` — Fixed (Strict Python 3.7.6 rules, existing SBEMimage architecture, config entry count invariants).
4. **Existing consumers and compatibility expectation:** `answered` — Must keep (existing manual blind slice removal in `ApproachDlg` must remain intact and functional).
5. **Migration/rollout needs:** `answered` — Phased in-place GUI extension (Manual vs. Automated tabs in `ApproachDlg`, with non-destructive error/abort knife handling).
6. **Stack constraints (Platform Context: Existing):** `answered` — STRICT Python 3.7.6 (no walrus `:=`, no PEP 585/604 syntax, no `f"{var=}"`, `CFG_NUMBER_KEYS` update when adding config keys).
7. **Versioning/contract stability:** `answered` — Internal SBEMimage controller/dialog contracts; no public API break.
8. **Data migration required:** `answered` — None; persisted settings in `default.ini` under `[approach]`.

## Domain-Specific Clarification Log [LOG]

### CL-AUTO_APPROACH-001: Contact Criterion
- **Q:** What physical/algorithmic criterion defines automated sample approach and triggers completion?
- **A:** Image-difference detection across consecutive SEM images until first knife-sample contact ("stop on touch").
- **Outcome:** Incorporated into `1-prd.md` under `AC-SBEM-AUTO_APPROACH-001`.

### CL-AUTO_APPROACH-002: SEM Imaging Target & Resolution
- **Q:** Which SEM imaging target should be acquired to inspect the sample surface after each cutting step?
- **A:** User-defined set of high-resolution tiles. An Overview (OV) image lacks sufficient resolution (150–500 nm/px) to detect early localized grazing touches or subtle resin planing, whereas high-resolution tiles (10–50 nm/px) provide the necessary sensitivity.
- **Outcome:** Incorporated into `1-prd.md` under `AC-SBEM-AUTO_APPROACH-002` and `2-adl.md`.

### CL-AUTO_APPROACH-003: Cutting & Interleaving Cadence
- **Q:** How should microtome cutting and knife Near/Clear cycles be interleaved with SEM imaging?
- **A:** Batch $K$ approach cuts with knife maintained in "Near" position $\to$ Move knife to "Clear" position $\to$ Acquire user-defined high-resolution tiles $\to$ Compute registered image difference $\to$ Repeat until contact detected or Max Total Depth safety limit reached.
- **Outcome:** Incorporated into `1-prd.md` under `AC-SBEM-AUTO_APPROACH-003`.

### CL-AUTO_APPROACH-004: UI Integration
- **Q:** How should Automated Approach be integrated into the SBEMimage GUI?
- **A:** Extend the existing Approach dialog (`ApproachDlg`) to support both classic blind Approach ("Manual") and Automated Approach ("Automated"), maintaining a unified modal control dialog.
- **Outcome:** Incorporated into `1-prd.md` under `AC-SBEM-AUTO_APPROACH-004`.

### CL-AUTO_APPROACH-005: Sample Surface Physics & MVP Probe Tile Scope
- **Q:** What does a newly mounted sample block face look like right before approach (coated vs. uncoated), and how should probe tiles be selected for MVP?
- **A:** Both sputter-coated/rough-trimmed blocks (high-contrast coat stripping) and uncoated/semi-planed blocks (subtle low-contrast resin texture change) occur routinely. For MVP, keep selection simple without rotating random tile subsets: the operator selects a fixed set of probe tiles (via Viewport right-click `"Select/deselect as approach ref."`, custom `"g.t"` list, or `"First & Last active"` preset), and approach stops immediately as soon as a cut is detected on **any** probe tile.
- **Outcome:** Updated `1-prd.md` (`AC-SBEM-AUTO_APPROACH-001`, `AC-SBEM-AUTO_APPROACH-003`) and `2-adl.md` (`AD-AUTO_APPROACH-005`).

### CL-AUTO_APPROACH-006: Grid-Inherited Scan Parameters & Dwell Override
- **Q:** How should SEM scan parameters (frame size, pixel size, dwell time) be determined for probe tiles?
- **A:** Strictly inherit frame size, pixel size, rotation, XY position, and WD/stig from each probe tile's parent Grid, while inheriting dwell time by default with an option in `ApproachDlg` to override dwell time (e.g. to reduce electron dose and resin Z-shrinkage).
- **Outcome:** Updated `1-prd.md` (`AC-SBEM-AUTO_APPROACH-003`) and `2-adl.md` (`AD-AUTO_APPROACH-005`).

### CL-AUTO_APPROACH-007: Dual SSIM Detection Modes (Dose-Drift Invariant)
- **Q:** Since raw image intensity drifts with cumulative electron dose, what structural comparison metric should be used?
- **A:** Raw intensity difference is unreliable under electron dose. Implement two user-selectable SSIM modes for the PoC after denoising and bounded-shift subpixel registration: (1) z-score normalized whole-tile SSIM (`Normalized SSIM`), and (2) spatial-gradient magnitude whole-tile SSIM (`Gradient SSIM`).
- **Outcome:** Updated `1-prd.md` (`AC-SBEM-AUTO_APPROACH-001`) and `2-adl.md` (`AD-AUTO_APPROACH-003`).

### CL-AUTO_APPROACH-008: Zero User Thresholds & Single-Scan Odd/Even Scan-Line Self-Calibration
- **Q:** Should operators tune an SSIM threshold or run a 2-scan baseline calibration at Start?
- **A:** Operators must not be bothered with thresholds or manual calibration, and Start must acquire **strictly 1 baseline scan** per probe tile to minimize electron dose. Each tile self-calibrates its $2\times$ pyramid denoising level and internal noise floor from odd vs. even raster scan lines (`I[0::2, :]` vs. `I[1::2, :]`) of that single image.
- **Outcome:** Updated `1-prd.md` (`AC-SBEM-AUTO_APPROACH-001`, `AC-SBEM-AUTO_APPROACH-002`) and `2-adl.md` (`AD-AUTO_APPROACH-002`).

### CL-AUTO_APPROACH-009: Pre-Flight Failure on Un-Trackable / Low-SNR Probe Tile
- **Q:** How should Auto-Approach react if any selected probe tile's single baseline scan at Start is blank, saturated, or featureless even after pyramidal pooling?
- **A:** Hard-abort **before cutting any slices** and identify which probe tile(s) failed SNR/validity so the operator can refocus or choose better probe tiles.
- **Outcome:** Updated `1-prd.md` (`AC-SBEM-AUTO_APPROACH-002`) and `2-adl.md` (`AD-AUTO_APPROACH-002`).

### CL-AUTO_APPROACH-010: 4th Viewport `Approach` Tab with Cyan/Magenta Overlays & Mouse-Wheel Scrubbing
- **Q:** How should the operator visualize the approach image series without information overload?
- **A:** Add a dedicated 4th `Approach` tab in `SBEMimage Viewport` displaying an auto-sized multi-tile grid of contrast-matched **Cyan/Magenta overlays** per probe tile (no SSIM graphs), with **mouse-wheel scrolling** through the approach series, bottom step slider + `Cyan-Magenta / Raw` toggle, double-click zoom, non-modal `ApproachDlg` (using `RESTRICT GUI` while running), and run archiving in `meta/approach/<timestamp>/`.
- **Outcome:** Updated `1-prd.md` (`AC-SBEM-AUTO_APPROACH-006`, `AC-SBEM-AUTO_APPROACH-007`) and `2-adl.md` (`AD-AUTO_APPROACH-006`).

### CL-AUTO_APPROACH-011: Microtome Knife-Clear Verification Hardening
- **Q:** Confirm hardening legacy Gatan 3View `.ack`/`.err` checks on `near_knife()` / `clear_knife()` / `do_full_approach_cut()` and Katana motor-stop wait before XY stage moves.
- **A:** Confirmed; include verified knife-clear guarantees in the architecture and verify artifacts prior to the Go Gate.
- **Outcome:** Updated `1-prd.md` (`AC-SBEM-AUTO_APPROACH-004`) and `2-adl.md` (`AD-AUTO_APPROACH-004`).

### CL-AUTO_APPROACH-012: Automated Re-Approach After Pauses & Cutting Issues (PRD Review)
- **Q:** Inline PRD review on Section 1 Context — when do operators need automated approach?
- **A:** Not only after mounting a sample, but also after acquisition pauses, chamber vents, or cutting issues experienced during dataset acquisition when an automated re-approach procedure is needed.
- **Outcome:** Updated `1-prd.md` Section 1 (`Context` & `Impact`) and `knowledge.md`.

### CL-AUTO_APPROACH-013: Remove Coated/Uncoated Distinction & Rely on User Area Selection (PRD Review)
- **Q:** Inline PRD review on Section 1 Value Proposition & Section 7 Domain Insights — should coated vs. uncoated samples be specified as a system requirement?
- **A:** Do not mention `'coated'` or `'uncoated'` at all: sputter coating is usually already removed during coarse approach in air before chamber evacuation, and selecting suitable sample areas for probe tiles is the operator's responsibility.
- **Outcome:** Removed all `'coated'`/`'uncoated'` references across `1-prd.md`, `2-adl.md`, `knowledge.md`, `auto-approach_architecture.md`, `verification.md`, and `5-tasks.md`.

### CL-AUTO_APPROACH-014: Gatan 3View Only — Exclude Katana Microtome (PRD Review)
- **Q:** Inline PRD review on Section 2 Microtome Support — should ConnectomX Katana systems be supported?
- **A:** No; Katana systems are not supported. Scope Automated Approach strictly to Gatan 3View (and `Microtome_Mock` for simulation/testing).
- **Outcome:** Moved Katana explicitly to Section 3 `Out of Scope` in `1-prd.md`, updated `2-adl.md`, `knowledge.md`, `verification.md`, and removed `src/microtome_control_katana.py` from `5-tasks.md` (`T-007`).

### CL-AUTO_APPROACH-015: Error Handling (Keep Knife in Place) & Scan-Rotation Preservation (PRD Review)
- **Q:** Inline PRD review on Section 4 Fail-Safe Integrity — how must knife position and scan rotation behave on error or completion?
- **A:** On any error, the knife **must stay in its current location** because clearing the knife while it is in `'Before slice'` position can shear tissue off the sample. Also, scan rotation **must NOT be reset to `0`** — it must remain in whatever state it was before approach or as defined in the respective Grid.
- **Outcome:** Updated `1-prd.md` (`Section 4`, `AC-SBEM-AUTO_APPROACH-003`, `AC-SBEM-AUTO_APPROACH-005`), `2-adl.md` (`AD-AUTO_APPROACH-004`, `AD-AUTO_APPROACH-005`), `knowledge.md`, `auto-approach_architecture.md`, `verification.md`, and `5-tasks.md`.

### CL-AUTO_APPROACH-016: User Abort / Cancel Sequence — Stop Knife, Deactivate `'Stroke Up'`, Never Auto-Clear (PRD Review)
- **Q:** Inline PRD review on Section 6 Fallback/Rollback — what exact sequence must happen when the user clicks Cancel/Abort?
- **A:** Cancel/Abort immediately halts cutting and **does NOT automatically clear the knife** (clearing in a non-nominal condition can inadvertently cut a physical slice). It must first stop the knife in its current position, then if `'Stroke Up'` is active deactivate `'Stroke Up'` to lower the sample below cutting level, and report the knife state and total depth removed. Only after stopping and lowering the sample below cutting level can the knife be cleared manually.
- **Outcome:** Updated `1-prd.md` (`Section 2`, `Section 4`, `Section 6`, `Section 7`, `AC-SBEM-AUTO_APPROACH-005`), `2-adl.md` (`AD-AUTO_APPROACH-004`), `knowledge.md`, `auto-approach_architecture.md`, `verification.md`, and `5-tasks.md`.

### CL-AUTO_APPROACH-017: DM Scripts (`dm/SBEMimage_DMcom_GMS*.s`) Strictly Read-Only / Forbidden to Modify
- **Q:** Should `dm/SBEMimage_DMcom_GMS3.s` be modified to add mid-stroke knife stop commands, or remain untouched?
- **A:** Modifying the `GMS.s` scripts (`dm/SBEMimage_DMcom_GMS2.s`, `dm/SBEMimage_DMcom_GMS3.s`) is strictly forbidden. All Gatan 3View control must work strictly through the existing DM script commands.
- **Outcome:** Added `dm/*.s` to `Out of Scope` in `1-prd.md` and `Anti-Targets` in `2-adl.md`; removed `dm/SBEMimage_DMcom_GMS3.s` from `T-007` in `5-tasks.md`.

### CL-AUTO_APPROACH-018: Revised User Abort Behavior — Move Knife to `Clear` After `'Stroke Up'` Is Deactivated
- **Q:** Clarification superseding `CL-AUTO_APPROACH-016` on whether `Abort` should leave the knife un-cleared or move it to `Clear` once `'Stroke Up'` is deactivated.
- **A:** On user `Abort`, the knife **shall** go to the `Clear` position, **after** `'Stroke Up'` has been deactivated (which unmodified `MicrotomeStage_FullApproachCut` guarantees upon `.ac2` completion with `Error.none`). On any hardware/DM **error**, the knife still stays in its current position without clearing.
- **Outcome:** Updated `1-prd.md` (`Section 2`, `Section 4`, `Section 6`, `AC-SBEM-AUTO_APPROACH-005`), `2-adl.md` (`AD-AUTO_APPROACH-008`), `knowledge.md`, `auto-approach_architecture.md`, `verification.md`, and `5-tasks.md`.

### CL-AUTO_APPROACH-019: Initial Knife State — Allow Starting from `'Before slice'` After Verifying Nominal Sample Z
- **Q:** At `Start`, must the knife already be in `Clear`, or can Automated Approach start from `'Before slice'` (`Clear` not active)?
- **A:** Automated Approach can start even from `'Before slice'` position (`Clear` knife not active); the procedure only has to make sure first that the **sample Z-axis is in a nominal state** (valid non-negative Z readout, no `Error.mismatch_z`, within Z limits) before commanding and verifying `Clear` prior to baseline imaging.
- **Outcome:** Updated `1-prd.md` (`Section 2`, `Section 4`, `AC-SBEM-AUTO_APPROACH-002`), `2-adl.md` (`AD-AUTO_APPROACH-008`), `knowledge.md`, `auto-approach_architecture.md`, and `verification.md`.

### CL-AUTO_APPROACH-020: Probe Tile Selection UX (`AC-SBEM-AUTO_APPROACH-003`) — Match Autofocus Ref Tiles 1:1
- **Q:** How should probe tile selection work in `Viewport` and `ApproachDlg`, and are `"First & Last active"` or `"Clear"` buttons needed?
- **A:** Match SBEMimage's Autofocus reference tile selection 1:1: right-click any tile `g.t` (active or inactive for stack acquisition) in an active Grid in `Viewport` to toggle `"Select/Deselect tile g.t as approach ref."` (with `APPROACH` label drawn on the tile), synced live with a `Reference tiles:` `QLineEdit` in `ApproachDlg`. Neither `"First & Last active"` nor a `"Clear"` button is needed.
- **Outcome:** Updated `1-prd.md` (`Section 2`, `AC-SBEM-AUTO_APPROACH-003`), `2-adl.md` (`AD-AUTO_APPROACH-009`), `auto-approach_architecture.md`, `verification.md`, and `5-tasks.md` (`T-009`).
