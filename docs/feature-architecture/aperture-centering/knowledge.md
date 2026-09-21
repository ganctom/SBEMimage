# Domain Knowledge: SEM Aperture Centering Dynamics

This document records physical insights, electromagnetic optics constraints, and hardware quirks governing aperture alignment in SBEMimage.

## 1. Physical Optics of the Objective Aperture
- **Function**: In a scanning electron microscope, the objective aperture defines the beam convergence angle ($\alpha$), cutting off high-angle off-axis electrons to reduce spherical and chromatic aberration.
- **Misalignment Symptoms**:
  - When the physical or electromagnetic aperture alignment is off-center relative to the column optical axis, the beam passes through non-ideal lens regions.
  - This introduces strong off-axis aberrations: primary coma, astigmatism, and tilted focal plane curvature across large field-of-view tiles.
  - While on-axis autofocus at the image center might appear sharp, tile perimeters will exhibit asymmetric, directional blurring.
- **Optimal Centering Objective**: Center the electron beam through the exact center of the electromagnetic deflector coil field such that focal plane curvature is radially symmetric and on-axis crispness is maximized.

## 2. Electromagnetic Deflectors & Hysteresis
- **Deflector Settling Time**:
  - Modern ZEISS SEMs use electromagnetic deflector coils (controlled via SmartSEM API `SetApertureAlignX` / `SetApertureAlignY`) to steer the beam through the physical aperture hole.
  - Deflector coils require finite settling time after current changes to stabilize magnetic fields. Sudden jumps cause transient image drift during the first lines of raster scanning.
  - A minimum settling delay of 1.0 s must be observed after deflector adjustments when not cutting.
- **Snake-Like Traversal**:
  - Rastering in a standard progressive grid (jumping from the end of row $k$ back to the start of row $k+1$) introduces large discontinuous current steps.
  - Using a snake-like (boustrophedon) path minimizes step distances and prevents magnetic hysteresis from distorting calibration measurements.

## 3. SmartSEM Coordinate Polarity Quirks
- **Inverted Y-Axis**:
  - On ZEISS SmartSEM instruments, the aperture alignment Y-axis is physically inverted relative to standard Cartesian coordinates.
  - Lower (more negative) Y percentages steer the beam UPward, whereas higher positive Y percentages steer it DOWNward.
  - To prevent operator confusion:
    - Directional UI buttons map **▲** to negative Y offsets and **▼** to positive Y offsets.
    - Diagnostic heatmaps call `axes.invert_yaxis()` so that smaller Y values are placed at the top of the plot, directly matching microscope physical movement.

## 4. Specimen Charging & Diamond Knife Sectioning
- **Beam Damage & Negative Surface Charge**:
  - Serial Block-Face imaging operates on non-conductive heavy-metal stained biological tissue embedded in plastic epoxy resin (e.g. Durcupan, Epon).
  - Sweeping 9 to 49 high-dose frames across the exact same specimen location deposits intense negative charge, resulting in electron deflection, image distortion, and severe hydrocarbon contamination.
- **Physical Cut Interleave**:
  - To acquire pristine calibration frames under realistic imaging conditions, a thin microtome section (e.g. 30–35 nm) is cut between frame acquisitions.
  - **Mechanical / Optical Overlap**: The aperture deflector for frame $i+1$ is updated *before* the microtome knife stroke begins. The deflector coils settle during the 15+ second mechanical cut cycle, completely eliminating optical settle latency while exposing a freshly cut, uncharged block surface for each frame.

## 5. Sharpness Metric Sensitivity & Regimes
- **Center Sharpness (Gradient Magnitude ROI)**:
  - Measures Tenengrad Sobel gradient magnitude inside a 98% circular ROI.
  - Highly effective when the dominant misalignment effect is uniform blur or symmetric defocus.
  - Continuous 2D paraboloid surface fitting overcomes discrete sampling discretization.
- **Radial Symmetry (Polar Unwrapping)**:
  - Measures angular variance across concentric rings via `cv2.warpPolar`.
  - Sensitive to pure off-axis optical aberrations (coma, astigmatic elongation) even when the overall image exhibits high brightness or sharp features in one direction.
