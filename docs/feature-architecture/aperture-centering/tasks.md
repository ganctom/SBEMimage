# Execution Ledger: feat/aperture-centering

## Phase 1: Core Calibration Engine & Mathematical Foundations
- [x] Implement `evaluate_radial_symmetry` using `cv2.Sobel`, `cv2.warpPolar`, and concentric ring angular coefficient of variation.
- [x] Implement `evaluate_center_sharpness` with configurable circular ROI radius fraction (default: 0.98).
- [x] Implement `fit_2d_surface` solving least-squares 6-parameter quadratic paraboloid to discover continuous sub-step optimal coordinates.
- [x] Build `ApertureCenteringManager` class in `src/aperture_centering.py` managing hardware calls, image storage, and results.
- [x] Implement `nudge(delta_x, delta_y)` for manual real-time deflector steering.

## Phase 2: Sweep Execution, Microtome Cutting, and Concurrency
- [x] Implement `run_sweep` with configurable grid sizes ($2 \times 2$ through $7 \times 7$), step size, resolution, and dwell time.
- [x] Implement snake-like grid sweep traversal (alternating rows starting from top-left) to minimize electromagnetic deflector hysteresis.
- [x] Implement chronological file naming (`frame_{idx+1:03d}_X{gx:+.2f}_Y{gy:+.2f}.tif`) for seamless alphabetical sorting in filesystem.
- [x] Interleave physical microtome sectioning between frame acquisitions when `perform_cut` is enabled.
- [x] Pre-set next aperture deflector alignment prior to physical cut cycle to overlap deflector coil settling with knife movement.
- [x] Sync stage Z updates across `microtome`, `stage`, `acq`, and `MainControlsTrigger` (`UPDATE Z`).
- [x] Dispatch asynchronous image evaluation in a 2-worker `ThreadPoolExecutor` concurrent with subsequent SEM raster scanning.
- [x] Implement subpixel phase cross-correlation registration and shared field-of-view cropping when `register_images` is enabled.
- [x] Ensure automatic reinstatement of initial aperture coordinates on sweep abort, exception, or user cancellation.

## Phase 3: GUI Development & User Interface Integration
- [x] Create `gui/aperture_centering_dlg.ui` with manual nudge pad, current alignment readouts, and sweep configuration group boxes.
- [x] Implement `ApertureCenteringDlg` in `src/main_controls_dlg_windows.py`.
- [x] Connect `Tools` → `Aperture Centering...` action in `src/main_controls.py`.
- [x] Connect PyQt triggers (`progress_trigger`, `finish_trigger`) for thread-safe UI updates without GUI freeze.
- [x] Add confirmation warning modal detailing cut count, per-cut thickness, total Z-advance (µm and nm), and duration prior to physical sectioning.
- [x] Implement post-sweep confirmation modal displaying initial vs. optimal coordinates and scores, offering immediate application or revert.
- [x] Add explicit "Apply Optimal Alignment" push button.

## Phase 4: Diagnostic Visualization & Plotting Polishing
- [x] Implement `generate_plots` generating two-panel diagnostic plot saved to `aperture_centering_heatmap.png`.
- [x] Invert Y-axis on 2D heatmaps to mirror SmartSEM physical deflector polarity (smaller/negative Y = top).
- [x] Annotate Initial position (`x`) and Optimal position (`★`) with explicit coordinate and best-fit labels.
- [x] In `Center Sharpness` mode, render secondary 2D heatmap showing global `Mean Sharpness` across X/Y space.
- [x] In `Radial Symmetry` mode, render radial sharpness falloff curves comparing initial vs. optimal alignments.
- [x] Ensure non-interactive headless plotting (`matplotlib.use('Agg')`) and call `plt.close(fig)` to eliminate memory leaks.

## Phase 5: Release Candidate Defaults & Code Polishing
- [x] Set default evaluation strategy to `Center Sharpness` (index 0).
- [x] Set default sweep parameters: Grid `5 x 5`, Step `5.0%`, Resolution `6144 x 4608`, Dwell `0.2 µs`, Pixel Size `15.0 nm`, Cut Thickness `35 nm`.
- [x] Set default ROI radius fraction to `0.98` for full-field central evaluation.
- [x] Validate Python 3.7.6 strictness across all modified files.
- [x] Expand unit test suite in `tests/test_aperture_centering.py` to 21 automated passing tests.
- [x] Perform formal code review and publish architectural registry documentation.
