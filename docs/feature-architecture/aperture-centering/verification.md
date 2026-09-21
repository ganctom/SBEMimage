# Verification Protocol: Aperture Centering

## Automated Testing

### 1. Pytest Unit & Integration Suite
Run the dedicated test suite using the SBEM Python 3.7.6 environment:
```bash
~/miniforge3/envs/sbem-py37/bin/python -m pytest tests/test_aperture_centering.py
```

### 2. Test Coverage Breakdown
- `test_evaluate_radial_symmetry_centered_vs_decentered`: Validates polar unwrap symmetry metric distinguishes centered focus domes from decentered domes.
- `test_aperture_centering_nudge`: Verifies real-time manual nudge updates SEM deflector state and returns true coordinates.
- `test_aperture_centering_sweep_and_artifacts`: Validates full 3x3 sweep, directory creation, log writing, JSON serialization, and diagnostic plot creation.
- `test_aperture_centering_auto_apply`: Validates that `auto_apply=True` updates SEM coordinates to optimal, while `auto_apply=False` reinstates initial coordinates.
- `test_aperture_centering_dlg_apply_and_revert`: Validates user confirmation dialog logic (Apply vs. Cancel).
- `test_aperture_centering_dlg_initialization`: Validates UI controls, combo box population, and widget states.
- `test_aperture_centering_physical_cut_with_thickness`: Validates that an $N \times N$ grid executes exactly $(N^2 - 1)$ physical cuts and advances microtome Z by $(N^2 - 1) \times \Delta z$.
- `test_aperture_centering_dlg_cut_warning_cancel`: Verifies safety modal warning displays cut counts and Z-advance, allowing user cancellation.
- `test_aperture_preset_before_cut_and_stage_z_callback`: Verifies that next aperture setting precedes diamond knife cut, and microtome stage Z callbacks execute synchronously.
- `test_aperture_centering_dlg_log_and_z_sync`: Verifies stage Z sync with acquisition manager and Main Controls trigger (`UPDATE Z`).
- `test_evaluate_center_sharpness_sharp_vs_blurry`: Validates Sobel gradient magnitude differentiates sharp images from blurred images.
- `test_evaluate_center_sharpness_empty_image`: Verifies empty array handling returns zeroed metrics without exception.
- `test_evaluate_center_sharpness_high_symmetry_poor_sharpness`: Validates that uniformly blurred images do not fool the `center_sharpness` metric.
- `test_center_sharpness_sweep_selects_optimal`: Validates full sweep under `center_sharpness` strategy.
- `test_fit_2d_surface_paraboloid`: Validates least-squares paraboloid surface fitting solves true critical point $(\hat{x}, \hat{y})$ under known inverted paraboloid.
- `test_even_grid_size_sweep`: Validates even grid sizes ($2 \times 2$, $4 \times 4$) execute and fit continuous surfaces correctly.
- `test_aperture_centering_sweep_with_registration_and_cropping`: Validates subpixel phase correlation, shift accumulation, and shared FOV cropping.
- `test_aperture_centering_dlg_register_images_checkbox`: Validates UI checkbox binding.
- `test_aperture_centering_dlg_default_settings`: Verifies all Release Candidate defaults:
  - Grid: `5 x 5`
  - Step: `5.0%`
  - Pixel Size: `15.0 nm`
  - Cut Thickness: `35 nm`
  - Strategy: `Center Sharpness` (index 0)
  - Frame: `6144 x 4608`
  - Dwell: `0.2 µs`
- `test_calibration_image_filenames_alphabetical_order`: Validates that files sorted alphabetically match acquisition chronology.
- `test_generate_plots_labels_with_initial_and_best_fit`: Validates plot title labels, marker labels, inverted Y-axes, and secondary panels.

---

## Physical Instrument Manual Verification Routine

When deploying to a physical ZEISS SEM with ultramicrotome:

1. **Launch SBEMimage**:
   - Open **Tools** → **Aperture Centering...**.
2. **Manual Nudge Verification**:
   - Click **Read Current** and confirm coordinates match SmartSEM.
   - Click **▲**: verify SmartSEM Y alignment decreases (moves UP physically).
   - Click **▼**: verify SmartSEM Y alignment increases (moves DOWN physically).
   - Click **◄** and **►**: verify X alignment updates accordingly.
3. **Dry-Run Sweep (No Cutting)**:
   - Select `3 x 3` grid, step `3.0%`, resolution `1024 x 768`.
   - Ensure "Perform physical cut" is unchecked.
   - Click **Start Sweep**.
   - Verify deflector settles for 1.0 s before each frame.
   - Observe live progress bar and status updates.
   - When finished, verify prompt displays initial and optimal coordinates.
   - Click **Cancel**: confirm initial alignment is reinstated in SmartSEM.
4. **Physical Cutting Sweep**:
   - Enable "Perform physical cut" with thickness `35 nm`.
   - Click **Start Sweep**.
   - Confirm safety warning prompt correctly calculates:
     - 8 cuts for a 3x3 grid
     - Total Z advance: $8 \times 35\text{ nm} = 280\text{ nm} = 0.280\text{ µm}$.
   - Click **OK** to proceed.
   - Observe microtome: verify next aperture alignment is set *before* each knife cut starts.
   - Verify Main Controls stage Z indicator updates after each slice.
5. **Artifact Inspection**:
   - Open `meta/calibrations/aperture_centering/<timestamp>/`.
   - Verify `frame_001...` through `frame_009...` sort in exact chronological order.
   - Open `aperture_centering_heatmap.png`:
     - Verify left heatmap has inverted Y-axis.
     - Verify Initial (`x`) and Optimal (`★`) markers match log coordinates.
     - Verify right panel displays Mean Sharpness heatmap.
