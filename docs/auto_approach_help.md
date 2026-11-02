# Automated Sample Approach (auto-approach)

The **Automated Sample Approach** system enables autonomous, vision-guided approach and re-approach of the microtome diamond knife to the specimen block face in SBEMimage. By combining single-scan odd/even scanline pyramidal self-calibration with structural similarity (SSIM) metrics, the system automatically detects the initial diamond knife cut with nanometer precision, eliminating manual knife advance guesswork, subjective thresholding, and risk of catastrophic specimen gouging.

---

## 1. Overview & Vision-Guided Approach Principles

### The Approach Challenge
During serial block-face electron microscopy (SBEM), approaching the ultra-microtome diamond knife to an unsectioned or newly loaded specimen block has traditionally required operators to manually advance the specimen stage in small increments and visually inspect microscope images or optical feeds. Manual approach carries significant risks:
- **Catastrophic gouging**: Over-advancing the stage can cause the diamond knife to deeply gouge the specimen resin, permanently destroying valuable biological material or chipping the diamond edge.
- **Operator fatigue & time loss**: Conservative manual stepping is tedious and can take hours.
- **Subjective heuristics**: Arbitrary absolute gray-level thresholds fail due to electron beam drift, specimen charging, carbon deposition, and subtle changes in sample topography.

### Vision-Guided Threshold-Free Cut Detection
SBEMimage's automated approach engine solves this through **single-scan structural contrast self-calibration and preprocessing**:
1. **Denoising & Contrast Equalization Preprocessing**:
   Every acquired tile frame passes through Gaussian filtering ($\sigma = 1.0$) to suppress Poisson shot noise followed by CLAHE (Contrast Limited Adaptive Histogram Equalization, `clipLimit = 2.0`, `tileGridSize = (8, 8)`). This strips macroscopic charging and illumination gradients while amplifying fine membrane boundaries and organelle ultrastructure, enabling reliable detection of ultra-thin physical cuts down to **25 nm**.
2. **10% Center-Crop Subpixel Registration**:
   Consecutive preprocessed frames are registered using subpixel phase cross-correlation restricted to the central $80\% \times 80\%$ window ($[0.10H:0.90H, 0.10W:0.90W]$). This eliminates beam flyback transients, scanning line distortion, and diamond knife shadow borders from corrupting stage wander estimation (safely clamped to $\le 15\,\mu\text{m}$).
3. **Tile-Specific Structural Contrast Thresholding**:
   During initial reference step 0, each baseline frame $I_0$ is split into interleaved odd/even raster scanlines ($E[r]$ and $O[r]$ on lattice $y = 2r + 1.5$) to decompose image variance into detector noise variance $\sigma_{\text{noise}}^2 = \frac{1}{2}\text{Var}(\tilde{E} - \tilde{O})$ and structural contrast ratio $\gamma_{\text{struct}} = \sigma_{\text{struct}} / (\sigma_{\text{total}} + \epsilon) \in [0.0, 1.0]$. The engine derives a dynamic, tile-specific cut dissimilarity threshold:
   $$d_{\text{trigger}}(\text{tile}) = \text{clamp}\Big(0.35 + 7.5 \cdot (0.75 - \gamma_{\text{struct}}),\; 0.300,\; 0.660\Big)$$
   - Dense biological tissue tiles ($\gamma_{\text{struct}} \ge 0.75$) calibrate to a tight threshold ($d_{\text{trigger}} = 0.300 - 0.350$), guaranteeing immediate Step 1 sensitivity on 25 nm ultra-thin cuts ($d = 0.752$).
   - Peripheral or resin tiles ($\gamma_{\text{struct}} \le 0.71$) calibrate to wider thresholds ($d_{\text{trigger}} = 0.550 - 0.660$), eliminating false positives from mechanical wander or non-uniform resin charging (0% false positives across all air approach runs).

### Dual SSIM Modes
- **Mode 0: Normalized SSIM**: Evaluates structural similarity across downsampled Gaussian pyramids with min-max normalization. This mode provides optimal robustness against high-frequency SEM shot noise and is recommended for standard biological specimens with rich structural contrast (e.g. brain tissue, cell cultures).
- **Mode 1: Gradient SSIM**: Evaluates structural similarity on Sobel gradient magnitudes. This mode suppresses low-frequency global charging gradients and resin intensity shifts while amplifying high-frequency diamond knife striations, chatter marks, and resin shearing, providing superior sensitivity on uniform epoxy resin, heavily charging blocks, or low-contrast specimens.

---

## 2. Quick Start & Parameter Tuning

### Opening the Approach Dialog
Open the **Approach Dialog** from the **Main Controls** window:
Click on **Approach...** (or select **Microtome** → **Approach**).

The dialog provides two tabs:
- **Manual Tab**: Traditional manual stage advance controls and single cut triggers.
- **Automated Tab**: Vision-guided automated approach setup, parameter tuning, and execution monitoring.

### Configuring Parameters in the Automated Tab

1. **Reference Tiles (`Reference tiles:` / `lineEdit_refTiles`)**:
   - Specifies which tile fields of view will be imaged to detect diamond knife contact.
   - Format: comma-separated `Grid.Tile` pairs (e.g. `0.0, 0.2`).
   - **Interactive Selection**: You can designate tiles directly from the Viewport. Right-click any active acquisition tile and select **Set as approach reference** (or **Toggle approach reference**). The tile boundary is marked with a distinctive `REF` badge, and the input field in the Approach Dialog updates automatically.

2. **Slice Thickness (`Slice thickness:` / `spinBox_autoThickness`)**:
   - The stage advance per microtome cutting cycle in nanometers (default: `100 nm`, range: `5` to `200 nm`, step: `5 nm`).
   - Conservative values ($20 - 50\text{ nm}$) protect delicate samples and knives; larger values ($50 - 100\text{ nm}$) accelerate approach through thick blank resin caps.

3. **Batch Cuts (`Batch cuts:` / `spinBox_batchSlices`)**:
   - Number of consecutive microtome cuts executed before imaging reference tiles (default: `5 slices`, range: `1` to `50 slices`).
   - Setting a batch size of `5` to `10` cuts reduces electron beam exposure and total approach duration during coarse initial approach.

4. **Max Depth (`Max depth:` / `doubleSpinBox_maxDepth`)**:
   - Hardware safety limit in micrometers (default: `20.0 µm`, range: `0.1` to `500.0 µm`, precision: `0.1 µm`).
   - If the stage advances by this cumulative distance without detecting a cut, the approach halts automatically in a safe state (`SAFETY_LIMIT_REACHED`), preventing runaway stage advance.

5. **Dwell Time (`Dwell time:` / `comboBox_dwellTimeOverride`)**:
   - Optional imaging dwell time override dropdown.
   - Options include **Inherit from grid** (uses the dwell time configured in the tile's parent grid) as well as accelerated overrides (`0.1 µs`, `0.2 µs`, `0.4 µs`, `0.8 µs`, `1.6 µs`, `3.2 µs`, `6.4 µs`).
   - Allows using a fast, low-dose scan for approach imaging without altering the high-quality dwell time configured in your primary acquisition tile grids.

6. **SSIM Mode (`SSIM mode:` / `comboBox_ssimMode`)**:
   - Select between **Normalized SSIM** (default) and **Gradient SSIM** depending on your specimen type and resin contrast.

7. **Starting and Stopping the Approach**:
   - Click **Start** (`pushButton_startAutoApproach`) to begin the sequence.
   - The dialog automatically enters a **RESTRICT GUI** mode: configuration inputs and motor jog buttons are locked to prevent conflicting commands, while the **Abort** button (`pushButton_abortAutoApproach`) remains immediately responsive.
   - Click **Abort** at any time to safely halt the approach sequence.
   - The progress bar (`progressBar_autoApproach`) and status label (`label_statusAutoApproach`) provide live feedback on current cutting steps, removed depth, and engine state.

---

## 3. Viewport 4th "Approach" Tab

The SBEMimage Viewport features a dedicated 4th tab labeled **Approach** (`tab_ap`), located alongside the `Overview`, `Tile View`, and `Slice View` tabs.

### Multi-Tile Canvas Grid Layout & Live Refresh
When multiple reference tiles are configured, the Approach tab canvas (`QLabel_ApproachCanvas`) automatically pre-allocates and maintains a fixed multi-tile grid layout across the entire automated approach procedure:
- **Instant Grid Pre-Allocation**: As soon as automated approach starts, the Viewport immediately allocates and visualizes the complete canvas grid for all configured reference tiles, eliminating jarring transitions or resizing from single full-screen tiles to multiple tiles.
- **Stable Multi-Tile Layout**: During each cutting step, the grid dimensions remain constant regardless of whether one or multiple tiles have completed evaluation. Tiles pending evaluation in the active step display the latest available frame from the prior step (registered to Step 0) with a distinctive `"Waiting..."` badge (or a dark placeholder if waiting for initial Step 0 baseline acquisition) until their new scan completes.
- **Live Per-Tile Refresh**: As each individual reference tile completes SEM acquisition and evaluation within a cutting step, its cell on the Viewport canvas and corresponding GUI controls immediately refresh in real time, displaying the newly acquired frame, dissimilarity metric, and contact status badge without waiting for remaining tiles in the step batch to complete.

### Real-Time Cyan / Magenta Compositing
During approach, the Viewport renders a live false-color composite:
- **Cyan Channel**: The baseline reference image (step 0 or prior cut step).
- **Magenta Channel**: The newly acquired cut step.
- **Visual Interpretation**:
  - **Neutral Gray / Dark**: Surface regions where no physical cutting has occurred. Perfect alignment yields an evenly balanced, monochrome appearance.
  - **Vivid Cyan / Magenta Color Fringes**: Direct visual evidence of material removal. When the diamond knife shears the surface, structural shifts, knife tracks, and tissue exposure appear as bright, high-contrast cyan and magenta striations.

### Interactive Navigation & Globally Registered Tile Series Scrubbing
- **Subpixel-Registered Series Display**: When scrolling through cutting steps to inspect for physical cuts, images in both **Raw** and **Cyan/Magenta** modes are presented translationally registered and anchored to the baseline (Step 0) coordinate frame. Cumulative subpixel shifts compensate for mechanical stage wander, thermal drift, and beam deflection, locking the biological tissue features firmly in place so true physical cutting transitions are visually unmistakable.
- **Mouse-Wheel Scrubbing**: Position the mouse cursor over the Approach canvas and scroll the mouse wheel up or down to scrub backwards and forwards through the entire cutting sequence.
- **Step Slider (`horizontalSlider_stepAP`)**:
  - Drag the horizontal step slider to jump directly to any cutting step ($0$ through $N$).
- **Step Info Label (`label_stepInfoAP`)**:
  - Displays formatted progress details: `Step {step_idx} / {max_steps} | Cuts: {slices} | Depth: {depth:.2f} µm | {state}`.
- **Raw Image Toggle (`pushButton_rawToggleAP`)**:
  - Click the **Show Raw** button (checkable) to toggle between the Cyan/Magenta composite overlay and the unprocessed 16-bit SEM grayscale tile image. When in raw mode, the button label changes to **Cyan-Magenta**.
- **Double-Click Zoom**:
  - Double-click any reference tile panel on the canvas to toggle between the fitted multi-tile overview and $1:1$ full-resolution inspection of subtle diamond knife chatter marks. Double-clicking again restores the multi-tile layout.

### Loading Archived Runs
- **Run Selector (`comboBox_runSelectorAP`)**: Lists all previously executed approach runs found in `meta/approach/`.
- **(Re)load Button (`pushButton_loadRunAP`)**: Click **(Re)load** to load and replay historical approach datasets stored on disk with full slider and mouse-wheel scrubbing interactivity.

---

## 4. Physical Dynamics & Hardware Safety Invariants

The automated approach engine enforces strict hardware safety invariants to guarantee specimen integrity and diamond knife protection under all conditions:

1. **Nominal-Z Pre-Clear Verification**:
   - Before commanding the microtome knife to advance from its retracted park position (`clear_knife()`), the engine verifies that the physical stage $Z$ coordinate matches the nominal cutting plane.
   - If the stage has been manually jogged or displaced upward, the engine halts immediately without moving the knife, preventing mechanical collisions.

2. **Verified Clear Before Stage XY Moves**:
   - The microtome knife must be fully in the `Clear` (retracted) position with verified `.ack`/`.ac2` handshake confirmation before any stage motor $X$ or $Y$ translation is commanded.
   - Stage translation while the knife is near the specimen block is physically impossible in software.

3. **Error Knife-Freeze Invariant**:
   - If any hardware subsystem reports an error state (`microtome.error_state`, `stage.error_state`, or `sem.error_state`), the approach engine **freezes the knife in place**.
   - Zero knife clearance or stage movement is commanded during an active hardware fault, preventing uncoordinated motor moves against a stationary diamond edge.

4. **Safe Abort Clear-After-Stroke-Down**:
   - When the operator clicks **Abort**, the engine does not perform a violent emergency stop during an active cutting sweep.
   - If the microtome arm is mid-stroke, the cut cycle is permitted to finish its downward return stroke, after which the knife is safely retracted to `Clear`, leaving the block face intact.

5. **Scan-Rotation Preservation**:
   - SBEMimage preserves per-grid scan rotation angles. When imaging rotated grids during approach, the SEM scan rotation is accurately applied ($\theta_{\text{sem}} = (360 - \theta_{\text{sbem}}) \bmod 360$).
   - Upon transitioning to unrotated grids, the engine explicitly restores scan rotation to $0.0^\circ$.
   - The engine guarantees that scan rotation is never reset to $0^\circ$ upon abnormal run termination, error, or operator abort, preventing disruption of active acquisition setups.

6. **Automatic Beam Blanking & Safety Shutter**:
   - The electron beam is automatically blanked during stage XY motor transit between reference tiles to minimize specimen irradiation and charging.
   - Beam state is shielded within protected `try...finally` blocks, **guaranteeing the beam is safely blanked (`set_beam_blanking(1)`) upon approach completion, halt, or error to prevent specimen irradiation and beam damage**.

7. **Application Exit Protection**:
   - If the user attempts to close the SBEMimage application while an automated approach is running, `MainControls.closeEvent` intercepts the event, raises a warning modal dialog, and blocks shutdown until the approach sequence is safely stopped.

8. **Asynchronous Stage Transit & Mechanical Drift Settling**:
   - For multi-tile reference setups, stage repositioning between consecutive reference tiles ($i \to i+1$) is dispatched asynchronously in a background worker thread immediately upon completing tile $i$'s SEM acquisition.
   - Stage physical transit overlaps concurrently with tile $i$'s image processing pipeline (preprocessing, subpixel registration, structural contrast dissimilarity evaluation, and overlay generation), significantly accelerating the approach cycle.
   - Residual stage drift is eliminated before subsequent frame acquisition begins, as the stage arrives at its target coordinates and undergoes natural mechanical settling during the concurrent image processing calculation. Non-overlapped moves (e.g. initial positioning to Tile 0) strictly maintain the configured stage settling pause (`stage_move_wait_interval`).

---

## 5. Data Serialization & Offline Inspection

Every automated approach run is serialized to disk in a structured directory under your acquisition project:
```
<project_dir>/meta/approach/<YYYY-MM-DD_HHMMSS>/
├── manifest.json
├── raw/
│   ├── step_000_g0000_t0000.tif
│   ├── step_000_g0000_t0001.tif
│   ├── step_001_g0000_t0000.tif
│   └── ...
└── overlays/
    ├── step_001_g0000_t0000_cm.png
    ├── step_001_g0000_t0001_cm.png
    └── ...
```

*(Note: Step 0 captures the baseline reference images and does not produce an overlay image; overlay images are generated for step 1 and onward).*

### Manifest Schema (`manifest.json`)
The `manifest.json` file records complete execution metadata using portable POSIX relative paths:
- **`timestamp`**: Formatted local timestamp (`YYYY-MM-DD HH:MM:SS`) of run initiation.
- **`terminal_state`**: Final run status (`"COMPLETED"`, `"ABORTED"`, `"SAFETY_LIMIT_REACHED"`, or `"ERROR"`).
- **`total_slices_cut`**: Cumulative number of microtome slices cut during the run.
- **`total_depth_removed_um`**: Total stage advance in micrometers.
- **`config`**: Snapshot of operational settings (`slice_thickness`, `batch_slices`, `max_depth`, `ssim_mode`, `dwell_time_override`).
- **`calibrations`**: Calibrated per-tile reference dictionary (`tile_key` -> `{ valid, pyramid_level, internal_ssim, noise_dissimilarity, cut_dissimilarity_limit, max_shift_px, failure_reason }`).
- **`steps`**: Chronological array of cutting steps:
  - `step_index`: Sequential integer ($0, 1, 2, \dots$).
  - `slices_cut_cumulative`: Microtome cumulative cut count.
  - `depth_removed_um`: Total stage advance since run start in micrometers.
  - `z_stage_um`: Absolute physical stage $Z$ position in micrometers.
  - `triggered_tiles`: List of tile keys where cut detection was triggered at this step.
  - `tile_evaluations`: Per-tile dictionary (`tile_key` -> `{ step_index, raw_image_path, overlay_image_path, shift_yx_px, cross_ssim, dissimilarity, contact_detected }`).

This standardized serialization format enables post-run auditing, offline visualization, and automated re-approach verification across all microscopy workflows.
