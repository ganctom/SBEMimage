# Domain Knowledge: SEM Aperture Centering Dynamics

This document records physical insights, electromagnetic optics constraints, and hardware quirks governing aperture alignment in SBEMimage.

## 1. Physical Optics of the Objective Aperture
- **Function**: In a scanning electron microscope, the objective aperture defines the beam convergence angle ($\alpha$), cutting off high-angle off-axis electrons to reduce spherical and chromatic aberration.
- **Misalignment Symptoms**:
  - When the physical or electromagnetic aperture alignment is off-center relative to the column optical axis, the beam passes through non-ideal lens regions.
  - This introduces strong off-axis aberrations: primary coma, astigmatism, and tilted focal plane curvature across large field-of-view tiles.
  - While on-axis autofocus at the image center might appear sharp, tile perimeters will exhibit asymmetric, directional blurring.
- **Optimal Centering Objective**: Center the electron beam through the column optical axis such that focal plane curvature is radially symmetric and on-axis crispness (Center Sharpness) is maximized.

## 2. Electromagnetic Deflectors & Hysteresis
- **Deflector Settling Time**:
  - Modern ZEISS SEMs use electromagnetic deflector coils (controlled via SmartSEM API `SetApertureAlignX` / `SetApertureAlignY`) to steer the beam through the physical aperture hole.
  - Deflector coils require finite settling time after current changes to stabilize magnetic fields. Sudden jumps cause transient image drift during the first lines of raster scanning.
  - A minimum settling delay of 1.0 s must be observed after deflector adjustments when not cutting.
- **Snake-Like Traversal**:
  - Rastering in a standard progressive grid (jumping from the end of row $k$ back to the start of row $k+1$) introduces large discontinuous current steps.
  - Using a snake-like (boustrophedon) path minimizes step distances and prevents magnetic hysteresis from distorting calibration measurements.

## 3. Hardware Deflector Limits & System Fallback
- **Microscope Coordinate Extents**:
  - Physical deflector coils operate within strict electrical/driver limits, typically $[-100.0\%, +100.0\%]$.
  - The software queries SmartSEM dynamically via `sem_api.GetLimits('AP_APERTURE_ALIGN_X', ...)` and `GetLimits('AP_APERTURE_ALIGN_Y', ...)`.
  - If the microscope is offline or in simulation mode, fallback limits are read from `system.cfg` under `[sem]` (`aperture_align_limits`).
  - Both manual nudge controls and automated sweep grids clamp coordinates to these limits to prevent hardware out-of-range faults.

## 4. SmartSEM Coordinate Polarity Quirks
- **Inverted Y-Axis**:
  - On ZEISS SmartSEM instruments, the aperture alignment Y-axis is physically inverted relative to standard Cartesian coordinates.
  - Lower (more negative) Y percentages steer the beam UPward, whereas higher positive Y percentages steer it DOWNward.
  - To prevent operator confusion:
    - Directional UI buttons map **▲** to negative Y offsets and **▼** to positive Y offsets.
    - Diagnostic heatmaps call `axes.invert_yaxis()` so that smaller Y values are placed at the top of the plot, directly matching microscope physical movement.

## 5. Electron Beam Monitoring & Fail-Safe Recovery
- **Beam-Off Events**:
  - The electron beam (EHT) may turn off unexpectedly during extended calibrations due to column vacuum interlocks, tip high-voltage arcs, or operator intervention.
  - Operating sweeps without an active electron beam wastes knife life (if cutting) and results in dark noise frames that corrupt surface fitting.
  - The software actively queries beam status (`is_eht_off()` / `is_eht_on()`) at the start and between each sweep step. If the beam drops, the sweep halts immediately, initial deflector coordinates are restored on the SEM, and a warning dialog alerts the operator.
- **API Unresponsiveness**:
  - Network or COM communication drops during `set_aperture_align_xy` or `acquire_frame` are caught safely, restoring initial microscope settings.

## 6. Specimen Charging & Diamond Knife Sectioning
- **Beam Damage & Negative Surface Charge**:
  - Serial Block-Face imaging operates on non-conductive heavy-metal stained biological tissue embedded in plastic epoxy resin (e.g. Durcupan, Epon).
  - Sweeping 9 to 49 high-dose frames across the exact same specimen location deposits intense negative charge, resulting in electron deflection, image distortion, and severe hydrocarbon contamination.
- **Physical Cut Interleave**:
  - To acquire pristine calibration frames under realistic imaging conditions, a thin microtome section (e.g. 30–35 nm) is cut between frame acquisitions.
  - **Mechanical / Optical Overlap**: The aperture deflector for frame $i+1$ is updated *before* the microtome knife stroke begins. The deflector coils settle during the 15+ second mechanical cut cycle, completely eliminating optical settle latency while exposing a freshly cut, uncharged block surface for each frame.

## 7. Sharpness Metric: Center Sharpness
- Measures Tenengrad Sobel gradient magnitude inside a 98% circular ROI.
- Proven, robust, and computationally fast across biological resin block-faces.
- Radial Symmetry (polar unwrapping) was evaluated and formally removed due to unproven mathematical stability on non-isotropic cellular textures; Center Sharpness paired with 2D quadratic paraboloid regression reliably finds the optical optimum.
