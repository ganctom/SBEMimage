# PRD: fix/stage-calibration-precision

## 1. System Objective
Redesign the stage calibration procedure to use a robust, multi-point (NxN grid) least-squares affine transformation fit, including central-cropping of images to eliminate geometric lens distortions, high-speed multi-threaded pairwise registration, and adaptive downsampling.

## 2. Hard Constraints
- Target Runtime: Python 3.7.6 (x86_64 Rosetta).
- NO PEP 585 generics (e.g. list[str]); use typing.List.
- NO PEP 604 unions (e.g. int | None); use typing.Optional/Union.
- NO walrus operator (:=).
- Calibration moves (`shift`) must be less than 50% of the image field of view to guarantee sufficient overlap within the central 60% cropped area (20% margins on all edges).
- Scale factors X and Y must be constrained to the range `[0.1, 10.0]`.
- A 0.6s settling delay must be observed after each stage movement before capturing an image frame.

## 3. In-Scope Boundaries
- `src/main_controls_dlg_windows.py` (`StageCalibrationDlg`)
- `gui/stage_calibration_dlg.ui` (Addition of Grid size, Frame size, Number of runs, and Wander radius controls)

## 4. Anti-Targets
- Do not refactor legacy PyQt GUI code outside feature scope.
- Do not fundamentally alter the downstream usage of the 4-parameter model (`scale_x`, `scale_y`, `rot_x`, `rot_y`) in `src/coordinate_system.py`.

## 5. Architectural Discussion & Design
- **Original Flow**: The legacy GUI calibrates based on a small 3-point (L-shape) local movement. The affine parameters calculated from these isolated vectors suffer from large discrepancies when extrapolated across a massive tile-grid.
- **Redesigned Flow**: The stage is driven through a user-configurable N x N grid. Cross-correlation is computed on a central 60% crop of all adjacent image pairs to filter out edge distortions. An overdetermined linear system of shifts is constructed and solved via Ordinary Least Squares (`np.linalg.lstsq`) to extract a highly robust, global transformation matrix.
- **Automatic Parameter Negotiation**: The system automatically computes and suggests a reasonable calibration shift (e.g., 30% of FOV) whenever the user changes pixel size or frame size, while allowing manual overrides. Legacy features like the parameter acceptance popup are fully preserved.
- **Multi-Run Aggregation & Outlier Rejection**: Performs $M$ grid calibrations at randomly wandered macro-locations (respecting stage limits). Each run produces an affine matrix. Outlier runs (caused by lack of resin features, etc.) are aggressively discarded using a Median Absolute RMSE filter, and the remaining matrices are combined via Median to form an ultra-stable global calibration.
- **Micro-Jitter Anti-Aliasing**: Random $\pm 10\%$ micro-jitter is applied to individual grid targets to prevent stage lead-screw runout and other periodic imperfections from systematically biasing the calibration (the true delta coordinates are tracked and mapped precisely to the least-squares engine).
- **Ephemeral Storage**: All calibration grid images are handled exclusively via Python's `tempfile` and aggressively destroyed upon memory loading, eliminating workspace bloat.
- **Flipped Axes & Angular Normalization**: On systems where stage motor axes are inverted relative to SEM pixel coordinates, the affine fit yields `cos(rot_diff) < 0` (negative scale factors). The engine reconciles this by offsetting both `rot_x` and `rot_y` by $\pm \pi$ and flipping the scale signs, maintaining mathematical matrix equivalence while enforcing positive scales and expected angular quadrants.
- **High-Speed Computation Pipeline**:
  - **Adaptive Downsampling**: For large frames (>1024 px), images are adaptively downscaled using area averaging (`cv2.INTER_AREA`), phase correlation is evaluated with subpixel precision, and shifts are re-scaled, reducing FFT computational complexity by $>10\times$.
  - **Hardware-Accelerated OpenCV Correlation**: Uses native AVX2 C++ `cv2.phaseCorrelate` with Hann windowing for near-instant (<5ms) subpixel shift resolution, falling back to ORB RANSAC only if the correlation peak is low.
  - **Multi-Threaded Parallel Execution**: Pairwise shift tasks ($2 N (N - 1)$ per run) are processed concurrently across all available CPU cores via `concurrent.futures.ThreadPoolExecutor`.
- **UI Architecture**: To maintain user familiarity, the legacy "Calculate calibration parameters" group box maintains its original layout and coordinate structure, housing the legacy pixel-shift inputs, parameter calculation method selection, and explicit calculation buttons. The advanced Multi-point grid parameters (Grid Size, Frame Size, Number of Runs, Wander Radius) are housed strictly within a newly injected layout column on the far right, logically dividing the old and new control planes.
