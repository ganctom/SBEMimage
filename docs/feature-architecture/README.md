# SBEMimage Feature Architecture Registry & Tracker

This directory serves as the persistent architectural repository and tracker for major features implemented in SBEMimage. 

Whenever a complex feature development cycle is finalized, its technical design, mathematical formulations, hardware constraints, and verification protocols are archived here so that future maintainers and developers have deep context on architectural decisions.

---

## Feature Registry

| Feature Name | Status | Primary Modules | Architecture Reference | Summary |
| :--- | :---: | :--- | :--- | :--- |
| **Focal Charge Compensator Ramp (fcc-ramp)** | Completed | `src/sem_control_zeiss.py`<br>`src/main_controls.py`<br>`src/acquisition.py`<br>`gui/fcc_ramp_settings_dlg.ui` | [Architecture](fcc-ramp/fcc-ramp_architecture.md)<br>([PRD](fcc-ramp/prd.md) \| [Tasks](fcc-ramp/tasks.md) \| [Knowledge](fcc-ramp/knowledge.md) \| [Verification](fcc-ramp/verification.md)) | Automated linear time-based pressure interpolation for the Focal Charge Compensator to prevent abrupt pressure shocks. Includes interactive ramp settings dialog, live progress styling on main window, and automatic stack-end ramp down. |
| **Stub Overview Stage Position (stub-ov-stage-pos)** | Completed | `src/viewport_dlg_windows.py`<br>`gui/stub_ov_dlg.ui` | [Architecture](stub-ov-stage-pos/stub-ov-stage-pos_architecture.md)<br>([PRD](stub-ov-stage-pos/prd.md) \| [Tasks](stub-ov-stage-pos/tasks.md) \| [Knowledge](stub-ov-stage-pos/knowledge.md) \| [Verification](stub-ov-stage-pos/verification.md)) | Added compact 'Read XY' button to Stub Overview dialog to automatically populate center coordinates from current microscope stage position without enlarging dialog width. |
| **Focus and Stigmation Transfer to Overviews (focus-stig-to-ov)** | Completed | `src/grid_manager.py`<br>`src/overview_manager.py`<br>`src/main_controls_dlg_windows.py`<br>`src/acquisition.py`<br>`gui/overview_settings_dlg.ui`<br>`gui/acq_settings_dlg.ui` | [Architecture](focus-stig-to-ov/focus-stig-to-ov_architecture.md)<br>([PRD](focus-stig-to-ov/prd.md) \| [Tasks](focus-stig-to-ov/tasks.md) \| [Knowledge](focus-stig-to-ov/knowledge.md) \| [Verification](focus-stig-to-ov/verification.md)) | Propagation of working distance and stigmation from active tile grids to matching overviews to maintain sharp focus across serial cuts, with automated pre-acquisition sync and on-demand GUI transfer. |
| **Overview Image Rotation (ov-rotation)** | Completed | `src/overview_manager.py`<br>`src/acquisition.py`<br>`src/viewport.py`<br>`src/main_controls_dlg_windows.py`<br>`gui/overview_settings_dlg.ui` | [Architecture](ov-rotation/ov-rotation_architecture.md)<br>([PRD](ov-rotation/prd.md) \| [Tasks](ov-rotation/tasks.md) \| [Knowledge](ov-rotation/knowledge.md) \| [Verification](ov-rotation/verification.md)) | Arbitrary scan-rotation support for overview images with SEM polarity inversion $(360-\theta)\bmod 360$, fail-safe post-acquisition 0° scan-rotation reset guard, rotated AABB bounding box for debris detection, viewport pivot rotation rendering and mouse coordinate inversion, and GUI rotation controls with grid rotation inheritance. |
| **Grid Shifting & Focal Plane Tracking** | Completed | `src/acquisition.py`<br>`src/autofocus.py`<br>`gui/slice_view.py` | [Architecture](grid-shifting/grid_shifting_architecture.md) | Deterministic grid shifting to eliminate quadruple electron dose at tile intersections with dynamic Working Distance gradient tracking and viewport slice-by-slice visual compensation. |
| **Multi-Point Global Affine Stage Calibration** | Completed | `src/main_controls_dlg_windows.py`<br>`gui/stage_calibration_dlg.ui`<br>`src/test_stage_calibration_fit.py` | [Architecture](stage-calibration/stage_calibration_architecture.md)<br>([PRD](stage-calibration/prd.md) \| [Tasks](stage-calibration/tasks.md) \| [Knowledge](stage-calibration/knowledge.md) \| [Verification](stage-calibration/verification.md)) | Robust $N \times N$ grid calibration using Ordinary Least Squares affine fit, central 60% lens distortion cropping, AVX2 subpixel phase correlation, multi-core parallelization, 0.6s settle time, and statistical multi-run wander aggregation. |
| **Asynchronous Mirror Drive Copying** | Completed | `src/acquisition.py` | [Architecture](async-mirroring/async_mirroring_architecture.md) | Non-blocking background worker thread with bounded queue to overlap network mirror drive file copies with stage motor movements, eliminating network-induced acquisition cycle delays. |
| **Automated & Interactive Aperture Centering** | Completed | `src/aperture_centering.py`<br>`src/main_controls_dlg_windows.py`<br>`gui/aperture_centering_dlg.ui` | [Architecture](aperture-centering/aperture_centering_architecture.md)<br>([PRD](aperture-centering/prd.md) \| [Tasks](aperture-centering/tasks.md) \| [Knowledge](aperture-centering/knowledge.md) \| [Verification](aperture-centering/verification.md)) | Interactive manual steering and automated $N \times N$ sweep calibration with snake-like traversal, Center Sharpness evaluation, continuous 2D paraboloid surface fitting, automated subpixel phase correlation registration, microtome diamond-knife de-charging interleave, hardware/system limits clamp, beam off guard, and SmartSEM Y-axis inverted diagnostic heatmaps. |

---

## Directory Conventions for New Features

When adding a new feature:
1. Create a subfolder: `docs/feature-architecture/<feature-name>/`.
2. Add a comprehensive `<feature-name>_architecture.md` detailing:
   - Problem statement and legacy limitations
   - Mathematical coordinate models and equations
   - Hardware integration dynamics (timings, axes, motors, detectors)
   - Performance optimizations (downsampling, multithreading, algorithmic complexity)
   - Edge cases, safety clamps, and testing protocols
3. Optionally include reference planning files (`prd.md`, `tasks.md`, `knowledge.md`, `verification.md`).
4. Update this `README.md` table to register the feature.
