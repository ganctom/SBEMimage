# Execution Ledger: fix/stage-calibration-precision

## Phase 1: Grid Calibration Implementation
- [x] Add Grid Size `QSpinBox` and Frame Size `QComboBox` to UI programmatically in `StageCalibrationDlg`.
- [x] Update overlap constraint to strictly enforce `shift < 0.5 * image_size`.
- [x] Implement automatic `shift` calculation (30% of FOV) triggering on pixel/frame size changes.
- [x] Update `calibration_images_acq_thread` to acquire an NxN grid of images.
- [x] Implement central 60% cropping (20% from all edges) before cross-correlation.
- [x] Compute cross-correlation for all adjacent horizontal and vertical pairs.
- [x] Use `np.linalg.lstsq` to solve overdetermined affine transformation equations.
- [x] Extract `scale_x`, `scale_y`, `rot_x`, `rot_y` and update the GUI/log with RMSE statistics.
- [x] Preserve legacy parameter acceptance popup logic post-calculation.

## Phase 2: Statistical Multi-Run Stage Calibration & Performance Optimization
- [x] Add "Number of Runs" and "Wander radius" controls to UI.
- [x] Integrate `tempfile` to read/write images in memory and prevent disk bloat.
- [x] Wrap acquisition in a loop that selects random macro-locations within the Wander Radius.
- [x] Ensure hardware safety via `stage.pos_within_limits()` before macro-steps.
- [x] Calculate true distance vectors (`sx2 - sx1`, `sy2 - sy1`) utilizing jittered coordinates for perfect least-squares modeling.
- [x] Implement robust statistical aggregation (Median) and discard anomaly runs based on RMSE > 3x median.
- [x] Introduce 0.6s settling idle time after each stage move to settle residual mechanical motion.
- [x] Reconcile flipped axes: shift rotation angles by $\pi$ and invert scales when `cos(rot_diff) < 0`.
- [x] Restrict/clamp scale X/Y factors to `[0.1, 10.0]`.
- [x] Accelerate pairwise registration via `cv2.phaseCorrelate` with Hann windowing.
- [x] Implement adaptive downsampling to $\le 1024$ px with subpixel interpolation.
- [x] Parallelize pairwise registration using `concurrent.futures.ThreadPoolExecutor` across all CPU cores.

## Phase 3: Global Position Discrepancy Mapping (Future)
- [ ] 3.1 Develop data structure to store grid-wide tile-pair shift vectors.
- [ ] 3.2 Map real position discrepancies from the computed shift vectors across a large tile-grid.
- [ ] 3.3 Implement non-linear correction models (e.g., polynomial surface, spline, or LUT).
- [ ] 3.4 Integrate the correction map into `CoordinateSystem.convert_d_to_s`.

## Phase 2.1: UI Layout Refinement
- [x] Separate legacy stage calibration 'Calculate calibration parameters' section to its original visual layout.
- [x] Create a new UI column (to the right of 'Pixel shift along X axis') specifically for the multi-point feature controls: Grid dimension, Frame size, Number of runs, Wander radius.
- [x] Ensure the method for registration (cv2, imreg_dft, skimage) remains within the legacy column.
