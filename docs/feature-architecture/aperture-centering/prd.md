# PRD: feat/aperture-centering

## 1. System Objective
Provide automated and interactive objective aperture centering calibration for ZEISS Scanning Electron Microscopes (SEMs) in SBEMimage. The system sweeps an $N \times N$ aperture alignment grid, captures high-resolution frames, evaluates off-axis optical field curvature and on-axis crispness, fits a continuous 2D paraboloid surface to detect sub-step optima, optionally interleaves physical microtome diamond-knife sectioning to eliminate beam charging, and auto-applies or interactively presents the optimal centering coordinates to the operator.

## 2. Hard Constraints
- **Python Version**: STRICTLY Python 3.7.6 (x86_64 Rosetta).
  - NO walrus operator (`:=`).
  - NO PEP 585 generics (`list[str]`); use `typing.List[str]`.
  - NO PEP 604 unions (`int | None`); use `typing.Optional[int]`.
  - NO f-strings with `=` (`f"{var=}"`).
- **Deflector Range**: Aperture alignment values are constrained to standard microscope deflector range (typically $[-100.0\%, +100.0\%]$).
- **Physical Safety**: When physical microtome cutting is enabled, diamond knife stroke count and total stage Z advance must be calculated and confirmed via explicit modal warning before moving motors.
- **SmartSEM Polarity**: SmartSEM aperture alignment Y-axis is inverted relative to standard Cartesian coordinates: smaller/negative Y values move the beam alignment UP, and larger positive Y values move it DOWN.
- **Fail-Safe Restoration**: If a calibration sweep is aborted, fails, or is cancelled by the user, the initial microscope aperture alignment coordinates must be guaranteed to be restored.

## 3. In-Scope Boundaries
- `src/aperture_centering.py` (`ApertureCenteringManager`, `evaluate_radial_symmetry`, `evaluate_center_sharpness`, `fit_2d_surface`)
- `src/main_controls_dlg_windows.py` (`ApertureCenteringDlg`)
- `gui/aperture_centering_dlg.ui` (Qt UI layout for manual steering and automated sweep controls)
- `src/main_controls.py` (Menu integration under Tools/Calibration)
- `tests/test_aperture_centering.py` (Comprehensive unit and integration test suite)

## 4. Anti-Targets
- Do not attempt closed-loop autofocus or astigmatism correction within this routine (AFSS handles dynamic focal tracking during stack acquisition).
- Do not block the PyQt GUI thread during lengthy multi-frame sweeps or physical diamond cuts.
- Do not mutate global microscope configuration files until the user explicitly approves applying the optimal alignment.

## 5. Architectural Discussion & Design

### 5.1 Dual Evaluation Strategies
- **Center Sharpness (Default)**:
  - Evaluates Sobel gradient magnitude over a circular centered region of interest spanning 98% of the frame radius.
  - Highly robust in practical serial section imaging where dominant optical defect is symmetric blurring or overall image defocus.
  - Paired with 2D quadratic paraboloid surface regression ($z = ax^2 + by^2 + cxy + dx + ey + f$) to solve for the continuous global peak $(\hat{x}, \hat{y})$ with sub-grid step precision.
- **Radial Symmetry**:
  - Unwraps the gradient magnitude image into polar coordinates $(r, \theta)$ centered at the optical center using OpenCV `cv2.warpPolar`.
  - Computes the angular coefficient of variation across concentric radial rings, applying linear weighting to emphasize outer rings where off-axis aberrations (coma, astigmatism) manifest strongly.
  - Maximizes rotational symmetry across the field of view.

### 5.2 Acquisition & Deflector Dynamics
- **Snake-Like Sampling Grid**: Sweeps alternate direction on successive rows (row 0: left $\to$ right; row 1: right $\to$ left) starting from the top-left to minimize hysteresis and settling artifacts in electromagnetic deflector coils.
- **Settling Time**: When physical cutting is disabled, a 1.0 s dwell time is observed after setting aperture coordinates before image acquisition.
- **Pre-Setting Before Knife Cut**: When physical cutting is enabled, the aperture coordinates for step $i+1$ are set *before* the microtome cut for step $i$ begins. This overlaps electromagnetic deflector settling with the mechanical knife movement (15+ s), eliminating idle time.

### 5.3 Physical Cutting & Charge Mitigation
- Repeated electron beam exposure on non-conductive resin blocks creates severe localized charging and hydrocarbon contamination.
- The manager interleaves physical microtome diamond knife cutting between calibration frames, tracking stage Z advances and updating `last_known_z` across `Microtome`, `Stage`, `Acquisition`, and Main Controls via Qt signals.

### 5.4 Phase Correlation Image Registration
- Large aperture deflector changes can produce optical translation on the sensor.
- When `register_images` is selected, consecutive frames are registered via phase cross-correlation (`utils.compute_shifts_cv2`), aligned via `utils.shift_collection`, and cropped to their shared overlapping field of view before metric evaluation.

### 5.5 High-Throughput Threading & Memory Management
- Frame evaluation is offloaded to a background `ThreadPoolExecutor`, allowing image analysis of frame $i$ to proceed concurrently while the SEM raster-scans frame $i+1$.
- Plotting runs headless via `matplotlib.use('Agg')` with explicit figure disposal (`plt.close(fig)`), avoiding memory leaks during long multi-hour runs.
