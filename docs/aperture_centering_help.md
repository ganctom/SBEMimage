# Aperture Centering Calibration

The **Aperture Centering** tool provides both interactive manual steering and fully automated grid sweep calibration for electromagnetic aperture alignment on ZEISS Scanning Electron Microscopes (SEMs). 

A misaligned objective aperture induces off-axis aberrations (such as coma, astigmatism, and tilted focal plane curvature), causing asymmetrical blur across large field-of-view tiles. Proper aperture centering ensures uniform resolution across the entire acquired block-face.

---

## Accessing the Tool

Open the dialog from the **Main Controls** window:
**Tools** → **Aperture Centering...** (or via the Calibration menu).

---

## Interactive Manual Steering

The manual control panel allows nudging the current aperture alignment in real time without running a full sweep.

- **Current Alignment (X, Y %)**: Displays the active aperture alignment coordinates reported by SmartSEM.
- **Nudge Step (%)**: Sets the percentage increment for each directional nudge (default: `1.00%`).
- **Directional Buttons (▲, ▼, ◄, ►)**: Nudges the aperture coordinates.
  > [!NOTE]
  > **SmartSEM Y-Axis Polarity**: In SmartSEM, the Y-axis controller is physically inverted: smaller (or more negative) Y values move the beam alignment **UP**, while larger positive Y values move it **DOWN**. The **▲** and **▼** buttons and the diagnostic heatmaps are calibrated to reflect this physical microscope behavior.
- **Read Current**: Re-queries the microscope for active aperture alignment coordinates.

---

## Automated Calibration Sweep

The automated routine sweeps a 2D grid of aperture alignment settings around the current center point, captures a calibration frame at each position, and computes sharpness metrics to locate the optimal alignment.

### Sweep Settings

1. **Grid Size**: Selects the dimension of the square sampling grid (options: `2 x 2`, `3 x 3`, `4 x 4`, `5 x 5`, `6 x 6`, `7 x 7`; default: `5 x 5`).
   - The sweep follows an alternating **snake-like pattern** (row 0: left-to-right, row 1: right-to-left, etc.) starting from the top-left to minimize hysteresis in the deflector coils.
2. **Sweep Step (%)**: Defines the displacement between adjacent grid points in aperture alignment units (default: `5.0%`).
3. **Frame Resolution**: Sets the acquisition resolution for calibration frames (default: `6144 x 4608`).
4. **Dwell Time (µs)**: Beam scan dwell time per pixel (default: `0.2 µs`).
5. **Pixel Size (nm)**: Imaging pixel size for calibration frames (default: `15.0 nm`).
6. **Evaluation Strategy**:
   - **Center Sharpness** (Default & Recommended): Measures Sobel gradient magnitude across a 98% centered circular region of interest. Fits a continuous 2D quadratic paraboloid surface across the sampled grid to resolve the global continuous peak, even if the true optimum lies between discrete sampling steps. Highly robust when symmetric defocus or overall image blur dominates.
   - **Radial Symmetry**: Uses polar unwrap coordinates (`cv2.warpPolar`) around the optical center to calculate the angular coefficient of variation across radial rings. Maximizes rotational symmetry across the field, isolating off-axis focal plane curvature and coma.
7. **Register and Crop Images**:
   - When enabled, computes translation shifts between consecutive frames using subpixel phase cross-correlation, shifts frames into alignment, and crops to their shared field of view prior to metric computation.
   - Recommended if large aperture deflector shifts cause noticeable field-of-view translation on the specimen.
8. **Perform Physical Cut (Diamond Knife Interleave)**:
   - When imaging resin-embedded biological blocks, taking multiple high-resolution frames at the same location can deposit severe negative charge and cause hydrocarbon beam contamination.
   - Checking **Perform physical cut** commands the ultramicrotome to cut a fresh block surface before every calibration frame.
   - **Cut Thickness (nm)**: Sets microtome Z-advance per cut (default: `35 nm`).
   - **Cut Duration (s)**: Automatically retrieved from the microtome configuration (`full_cut_duration`).
   - **Safety Optimization**: To maximize throughput and allow deflector coil fields to settle, the aperture alignment for the next step is applied *prior* to starting the physical cut, letting deflector transients decay during the knife stroke.

---

## Sweep Execution & Results

1. Click **Start Sweep**. If physical cutting is enabled, a confirmation prompt displays the total number of cuts, total Z-advance (in µm and nm), and estimated duration before proceeding.
2. During the sweep, progress is displayed on the progress bar and status line. Calibration frames are saved sequentially in:
   `meta/calibrations/aperture_centering/<YYYY-MM-DD_HHMMSS>/`
   as `frame_001_X+0.00_Y+0.00.tif`, sorted chronologically.
3. Once completed:
   - An interactive confirmation dialog displays the initial vs. optimal coordinates and sharpness scores.
   - The user can choose to **Apply** the optimal center to SmartSEM immediately or **Cancel** to keep the initial microscope setting.
   - Results can be manually applied at any time via **Apply Optimal Alignment**.
   - If aborted by the user or on error, the initial aperture alignment coordinates are automatically reinstated on the SEM.

---

## Output Artifacts & Diagnostic Plots

Every run generates a persistent report folder containing:
- `alignment_log.txt`: Complete execution log with timestamps, parameters, step-by-step aperture coordinates, and stage Z movements.
- `sharpness_data.json`: Machine-readable results containing grid coordinates, sharpness scores, continuous 2D paraboloid fit coefficients, cumulative registration shifts, and optimal coordinates.
- `aperture_centering_heatmap.png`: Diagnostic two-panel plot:
  - **Left Panel**: 2D heatmap of sharpness/symmetry score across Aperture Align X and Y with inverted Y-axis matching SmartSEM physical controls. Shows markers for Initial position (`x`) and Optimal position (`★`).
  - **Right Panel**: Secondary diagnostic plot showing either the 2D Mean Sharpness heatmap (in *Center Sharpness* mode) or radial sharpness falloff comparison curves (in *Radial Symmetry* mode).
- `registered/`: (If image registration is enabled) Directory containing the translation-corrected, cropped calibration image series.
