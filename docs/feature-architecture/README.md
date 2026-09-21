# SBEMimage Feature Architecture Registry & Tracker

This directory serves as the persistent architectural repository and tracker for major features implemented in SBEMimage. 

Whenever a complex feature development cycle is finalized, its technical design, mathematical formulations, hardware constraints, and verification protocols are archived here so that future maintainers and developers have deep context on architectural decisions.

---

## Feature Registry

| Feature Name | Status | Primary Modules | Architecture Reference | Summary |
| :--- | :---: | :--- | :--- | :--- |
| **Grid Shifting & Focal Plane Tracking** | Completed | `src/acquisition.py`<br>`src/autofocus.py`<br>`gui/slice_view.py` | [Architecture](grid-shifting/grid_shifting_architecture.md) | Deterministic grid shifting to eliminate quadruple electron dose at tile intersections with dynamic Working Distance gradient tracking and viewport slice-by-slice visual compensation. |
| **Multi-Point Global Affine Stage Calibration** | Completed | `src/main_controls_dlg_windows.py`<br>`gui/stage_calibration_dlg.ui`<br>`src/test_stage_calibration_fit.py` | [Architecture](stage-calibration/stage_calibration_architecture.md)<br>([PRD](stage-calibration/prd.md) \| [Tasks](stage-calibration/tasks.md) \| [Knowledge](stage-calibration/knowledge.md) \| [Verification](stage-calibration/verification.md)) | Robust $N \times N$ grid calibration using Ordinary Least Squares affine fit, central 60% lens distortion cropping, AVX2 subpixel phase correlation, multi-core parallelization, 0.6s settle time, and statistical multi-run wander aggregation. |
| **Asynchronous Mirror Drive Copying** | Completed | `src/acquisition.py` | [Architecture](async-mirroring/async_mirroring_architecture.md) | Non-blocking background worker thread with bounded queue to overlap network mirror drive file copies with stage motor movements, eliminating network-induced acquisition cycle delays. |
| **Automated & Interactive Aperture Centering** | Completed | `src/aperture_centering.py`<br>`src/main_controls_dlg_windows.py`<br>`gui/aperture_centering_dlg.ui` | [Architecture](aperture-centering/aperture_centering_architecture.md)<br>([PRD](aperture-centering/prd.md) \| [Tasks](aperture-centering/tasks.md) \| [Knowledge](aperture-centering/knowledge.md) \| [Verification](aperture-centering/verification.md)) | Interactive manual steering and automated $N \times N$ sweep calibration with snake-like traversal, dual sharpness metrics (Center Sharpness and Polar Radial Symmetry), continuous 2D paraboloid surface fitting, subpixel phase correlation registration, microtome diamond-knife de-charging interleave, and SmartSEM Y-axis inverted diagnostic heatmaps. |

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
