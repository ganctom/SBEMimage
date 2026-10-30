# Domain Knowledge: Automated Sample Approach (`auto-approach`)

This document records the physical dynamics, electron-beam interactions, Gatan 3View microtome mechanics, and SmartSEM conventions governing Automated Sample Approach and Re-Approach in SBEMimage.

---

## 1. Sample Block Physics & Electron-Beam Dynamics

1. **Initial Approach & Mid-Dataset Re-Approach Context:**
   - **Initial Vacuum Approach:** Performed after coarse approach in air and chamber evacuation (at which point any top sputter coating has typically already been trimmed off in air).
   - **Automated Re-Approach:** Frequently needed mid-dataset after an acquisition pause, chamber vent, thermal drift in $Z$, or recovery from cutting issues where the sample has been retracted below the cutting plane and must be brought back into contact with minimal tissue loss.
   - **Operator Probe Selection:** It is the operator's responsibility to place probe tiles (`g.t`) on suitable regions of the block face with trackable surface structure.
2. **Electron-Beam Resin Radiolysis & Z-Shrinkage ("Cratering"):**
   - Epoxy resins (Durcupan, Epon, Spurr's) undergo mass loss under electron irradiation, causing the scanned tile footprint to physically sink in $Z$ by tens of nanometers per high-dose scan.
   - Excessive repeated scanning on a probe tile depresses its surface below surrounding unirradiated tissue, risking a **false negative** where the knife shaves unimaged regions before touching the sunken probe pit.
   - **Design Mitigation:** Acquire **strictly 1 baseline scan** per probe tile at Start, allow overriding dwell time to fast low-dose values in `ApproachDlg`, batch $K$ cuts per check, and keep the SEM beam blanked throughout all cutting cycles.
3. **Dose-Induced Brightness & Contrast Drift:**
   - Even without physical cutting, cumulative electron dose and local surface charging shift raw grayscale mean and contrast from scan to scan.
   - Raw pixel subtraction and un-normalized SSIM (whose luminance factor $l(x, y) = \frac{2\mu_x\mu_y + C_1}{\mu_x^2 + \mu_y^2 + C_1}$ penalizes global mean shifts) are vulnerable to false triggers from charging drift. Normalizing via z-score or taking spatial gradient magnitudes removes uniform luminance/contrast drift prior to SSIM evaluation.
4. **Block-Face Tilt & Partial Grazing Contact:**
   - Pre-trimmed or thermally drifted block faces are not perfectly coplanar with the diamond knife cutting plane. First contact occurs at whichever region sits highest in $Z$; therefore, approach must halt immediately as soon as **any** probe tile detects a cut.

---

## 2. Raster SEM Noise Independence & Self-Calibration

1. **Odd vs. Even Raster Scan-Line Noise Independence:**
   - Along the horizontal fast-scan axis ($X$), detector preamplifier bandwidth can weakly correlate adjacent pixels $(x, x+1)$.
   - Across the vertical slow-scan axis ($Y$), adjacent scan lines $y$ (even) and $y+1$ (odd) are separated in time by a full line scan ($\sim 0.5\text{–}2\,\text{ms}$), making their shot and electronic noise **100% temporally independent** while sampling the same physical structures (shifted vertically by $0.5\,\text{px}$).
   - Comparing bilinearly aligned even lines `I[0::2, :]` against odd lines `I[1::2, :]` across a $2\times$ spatial pyramid measures each tile's exact empirical SNR and noise ceiling from **a single frame** with zero extra electron dose.
2. **Iteration $k=0$ vs. Iteration $k \ge 1$ Asymmetry:**
   - At **Iteration $k=0$ (Baseline)**, inability to achieve internal structural correlation across the pyramid means the chosen tile is blank, saturated, out of focus, or pure featureless shot noise — Automated Approach **must abort before cutting**.
   - At **Iteration $k \ge 1$ (Post-Cut)**, if the diamond knife shaves a previously textured, calibrated tile ($k-1$) into smooth resin ($k$), the frame grab is valid (normal mean intensity, non-saturated), while structural similarity against $I_{k-1}^{(l^*)}$ drops sharply — this is a **positive cut detection**, never a pre-flight SNR error.

---

## 3. Gatan 3View Mechanics, Knife Hazards & SmartSEM Realities

1. **Microtome Scope & Unmodified DM Scripts:**
   - Automated Approach supports **Gatan 3View** controlled via DigitalMicrograph (`src/microtome_control_gatan.py`) and `Microtome_Mock` for simulation/testing. ConnectomX Katana and other microtomes are out of scope.
   - Modifying `dm/SBEMimage_DMcom_GMS2.s` or `dm/SBEMimage_DMcom_GMS3.s` is **strictly forbidden**; all safety guarantees operate through existing DM commands (`MicrotomeStage_GetPositionZ`, `MicrotomeStage_SetPositionZ_Confirm`, `MicrotomeStage_Near`, `MicrotomeStage_Clear`, `MicrotomeStage_FullApproachCut`, `MicrotomeStage_SetPositionXY_Confirm`).
2. **Starting from `'Before slice'` & Sample Z-Axis Nominal Verification:**
   - Automated Approach may start with the knife in `'Before slice'` (`Clear` not active) or in `Clear`.
   - Before commanding `MicrotomeStage_Clear` for baseline imaging, the procedure first verifies that the **sample Z-axis is in a nominal state**: `get_stage_z()` returns a valid $Z \ge 0$, `error_state != Error.mismatch_z` (`206`), `error_state == Error.none`, and $Z$ is within stage limits. If sample Z is non-nominal, the procedure halts immediately without moving or clearing the knife. Once Z is verified nominal, `clear_knife()` safely clears the knife (`.ack` verified) before any XY stage motion or baseline SEM scan.
3. **Knife `Near` vs. `Clear` & `'Stroke Up'` Tissue-Shear Sequencing:**
   - Keeping the knife in `Near` during batched `do_full_approach_cut()` saves $\sim 3\text{–}4\,\text{s}$ per slice, while the knife holder occludes the SEM field of view and BSE detector; all XY stage moves and SEM tile grabs require the knife verified in `Clear` (`DMcom.ack`).
   - Inside `SBEMimage_DMcom_GMS3.s`, `MicrotomeStage_FullApproachCut` sets `stroke_down = 0, oscillator_off = 0` (`'Stroke Up'`, raising the sample to cutting level), runs `MicrotomeStage_Cut(1)`, sets `stroke_down = 1, oscillator_off = 1` (`'Stroke Down'`, deactivating `'Stroke Up'` and lowering the sample below cutting level), runs `MicrotomeStage_Retract(1)` (returning to `'Before slice'`), and writes `DMcom.ac2` on success or `DMcom.err` on failure.
   - **Mandatory Safety Rules:**
     1. **On Any Error (`DMcom.err`, timeout, Z mismatch, stage/SEM error):** Never call `clear_knife()` — leave the knife in its exact current position because `'Stroke Up'` or knife state cannot be trusted in a faulted state and clearing could shear off specimen tissue.
     2. **On User Abort / Stop:** Immediately halt scheduling further cuts. If a `MicrotomeStage_FullApproachCut` cycle is currently in flight, wait for `check_cut_cycle_status()` to confirm `DMcom.ac2` (`Error.none`), which guarantees `'Stroke Up'` has been deactivated (`stroke_down = 1`) and the sample is lowered below cutting level. **Then** move the knife to **`Clear`** (`clear_knife()` with `.ack` verification) and report removed depth. (If `.err` occurred during that active cycle, rule 1 applies and `clear_knife()` is NOT called.)
4. **Legacy Gatan Handshake Gaps (Discovered in Codebase):**
   - Legacy `Microtome_3View.near_knife()` and `clear_knife()` slept $4\,\text{s}$ without verifying `ACK_FILE` (`.ack`) or `ERROR_FILE` (`.err`), and legacy `ApproachDlg` never called `check_cut_cycle_status()` (`.ac2`/`.err`) after `do_full_approach_cut()`. Automated Approach verifies `.ack`/`.ac2`/`.err` on every nominal step.
5. **ZEISS SmartSEM Beam Blanking & Scan Rotation Preservation:**
   - `sem.set_beam_blanking(0)` unblanks the beam prior to `sem.acquire_frame()`; `sem.set_beam_blanking(1)` blanks the beam immediately afterward so a parked beam never irradiates the block during cutting batches.
   - Grid scan rotation uses SmartSEM polarity `theta_sem = (360 - theta_grid) % 360`. **Scan rotation MUST NOT be reset to `0`** at any point (completion, error, or abort); it stays in whatever state it had before approach or as defined by the respective probe tile's parent Grid, preserving alignment during mid-dataset re-approach.
