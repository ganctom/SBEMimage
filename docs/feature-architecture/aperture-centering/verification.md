# Verification Protocol: Aperture Centering

## Automated Testing

### 1. Pytest Unit & Integration Suite
Run the dedicated test suite using the SBEM Python 3.7.6 environment:
```bash
~/miniforge3/envs/sbem-py37/bin/python agent_test.py tests/test_aperture_centering.py
```
*(All 26 automated tests pass in ~120s).*

### 2. Configuration & Invariant Check
```bash
~/miniforge3/envs/sbem-py37/bin/python agent_test.py tests/test_focus_stig_to_ov.py
```
*(Verifies `check_number_of_entries` with `SYSCFG_NUMBER_KEYS = 56`).*

### 3. Test Coverage Breakdown (26 Tests)
- `test_evaluate_center_sharpness_synthetic`: Validates Sobel gradient magnitude over synthetic noise dome.
- `test_evaluate_center_sharpness_centered_vs_decentered`: Validates that centered focus domes score higher than off-axis decentered domes.
- `test_evaluate_center_sharpness_blur_gradient`: Differentiates sharp from blurred images.
- `test_evaluate_center_sharpness_flat_image`: Validates zeroed array handling without divide-by-zero errors.
- `test_fit_2d_surface_perfect_paraboloid`: Validates continuous least-squares paraboloid surface fitting solves true critical point $(\hat{x}, \hat{y})$.
- `test_fit_2d_surface_flat_or_concave`: Validates rejection of non-inverted/concave surfaces.
- `test_aperture_centering_sweep_and_artifacts`: Validates full 3x3 sweep, directory structure, text logging, JSON serialization, and heatmap plot generation.
- `test_aperture_centering_auto_apply`: Validates that `auto_apply=True` updates SEM coordinates to optimal, while `auto_apply=False` reinstates initial coordinates.
- `test_aperture_centering_dlg_apply_and_revert`: Validates user confirmation dialog logic (Apply vs. Cancel).
- `test_aperture_centering_dlg_initialization`: Validates UI controls, combo box population, and widget states.
- `test_aperture_centering_physical_cut_with_thickness`: Validates that an $N \times N$ grid executes exactly $(N^2 - 1)$ physical cuts and advances microtome Z by $(N^2 - 1) \times \Delta z$.
- `test_aperture_centering_dlg_cut_warning_cancel`: Verifies safety modal warning displays cut counts and Z-advance, allowing user cancellation.
- `test_aperture_preset_before_cut_and_stage_z_callback`: Verifies that next aperture setting precedes diamond knife cut, and microtome stage Z callbacks execute synchronously.
- `test_aperture_centering_dlg_log_and_z_sync`: Verifies stage Z sync with acquisition manager and Main Controls trigger (`UPDATE Z`).
- `test_evaluate_center_sharpness_high_symmetry_poor_sharpness`: Validates that uniformly blurred images receive poor sharpness scores.
- `test_fit_2d_surface_out_of_bounds_returns_none`: Validates out-of-bounds fitted extrema reject continuous fit and fall back to discrete grid peak.
- `test_cross_correlation_registration_pipeline`: Validates subpixel phase correlation, shift accumulation, and shared FOV cropping.
- `test_aperture_centering_dlg_register_images_removed`: Confirms removal of `checkBox_registerImages` from UI.
- `test_aperture_centering_dlg_default_settings`: Verifies all Release Candidate defaults (5x5 grid, Step Size 5.0%, 15 nm pixel size, 35 nm cut, 6144x4608 frame, 0.2 us dwell).
- `test_calibration_image_filenames_alphabetical_order`: Validates that files sorted alphabetically match acquisition chronology.
- `test_generate_plots_labels_with_initial_and_best_fit`: Validates plot title labels, marker labels, inverted Y-axes, and secondary Mean Sharpness panel.
- `test_beam_off_aborts_sweep_and_restores_initial`: Verifies electron beam dropping before or mid-sweep aborts the process, restores initial coordinates on the SEM, and raises `RuntimeError`.
- `test_sem_api_failure_aborts_sweep_and_restores_initial`: Verifies SEM API communication failures abort the sweep and safely reinstate initial coordinates.
- `test_hardware_limits_clamping_in_nudge_and_sweep`: Verifies hardware limits clamp manual nudge and sweep coordinates within bounds.
- `test_dlg_error_handling_shows_warning_and_restores_alignment`: Verifies that `ApertureCenteringDlg` displays a warning modal on sweep failure and restores initial values.
- `test_system_cfg_aperture_align_limits_and_entry_count`: Verifies `system.cfg` contains `aperture_align_limits`, matches `SYSCFG_NUMBER_KEYS`, and parses correctly in `SEM.get_aperture_align_limits()`.

---

## Physical Instrument Manual Verification Routine

When deploying to a physical ZEISS SEM with ultramicrotome:

1. **Launch SBEMimage**:
   - Open **Tools** → **Aperture Centering...**.
   - Check title: "Automated Aperture Centering Sweep".
   - Confirm label: "Step Size (%):".
   - Confirm absence of "Register and crop images" checkbox and evaluation strategy selector.
2. **Manual Nudge Verification**:
   - Click **Read Current** and confirm coordinates match SmartSEM.
   - Click **▲**: verify SmartSEM Y alignment decreases (moves UP physically).
   - Click **▼**: verify SmartSEM Y alignment increases (moves DOWN physically).
   - Click **◄** and **►**: verify X alignment updates accordingly.
   - Verify coordinate clamping when approaching hardware limits.
3. **Dry-Run Sweep (No Cutting)**:
   - Select `3 x 3` grid, step `3.0%`, resolution `1024 x 768`.
   - Ensure "Perform physical cut" is unchecked.
   - Click **Start Sweep**.
   - Verify deflector settles for 1.0 s before each frame.
   - Observe live progress bar and status updates.
   - When finished, verify prompt displays initial and optimal coordinates and "Center Sharpness" score.
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
5. **Safety & Error Interlock Test**:
   - Turn off beam during sweep: verify sweep halts immediately, initial alignment is restored on SEM, and error dialog is shown.
6. **Artifact Inspection**:
   - Open `meta/calibrations/aperture_centering/<timestamp>/`.
   - Verify `frame_001...` through `frame_009...` sort in exact chronological order.
   - Open `aperture_centering_heatmap.png`:
     - Verify left heatmap has inverted Y-axis.
     - Verify Initial (`x`) and Optimal (`★`) markers match log coordinates.
     - Verify right panel displays Mean Sharpness heatmap.
