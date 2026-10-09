# PRD: feat/aperture-centering

## 1. System Objective
Provide automated and interactive objective aperture centering calibration for ZEISS Scanning Electron Microscopes (SEMs) in SBEMimage. The system sweeps an $N \times N$ aperture alignment grid, captures high-resolution frames, evaluates on-axis and field crispness using Center Sharpness, fits a continuous 2D paraboloid surface to detect sub-step optima, automatically registers and crops frames via subpixel phase cross-correlation, optionally interleaves physical microtome diamond-knife sectioning to eliminate beam charging, guards against electron beam drops and unresponsive hardware APIs, and auto-applies or interactively presents the optimal centering coordinates to the operator.

## 2. Hard Constraints
- **Python Version**: STRICTLY Python 3.7.6 (x86_64 Rosetta).
  - NO walrus operator (`:=`).
  - NO PEP 585 generics (`list[str]`); use `typing.List[str]`.
  - NO PEP 604 unions (`int | None`); use `typing.Optional[int]`.
  - NO f-strings with `=` (`f"{var=}"`).
- **Deflector Limits & Clamping**: Aperture alignment values are constrained by hardware limits queried dynamically from SmartSEM via `GetLimits('AP_APERTURE_ALIGN_X', ...)` / `GetLimits('AP_APERTURE_ALIGN_Y', ...)`, falling back to `aperture_align_limits` configured in `system.cfg` (default $[-100.0\%, +100.0\%]$). All nudge and sweep coordinates are clamped within these limits.
- **Physical Safety**: When physical microtome cutting is enabled, diamond knife stroke count and total stage Z advance must be calculated and confirmed via explicit modal warning before moving motors.
- **SmartSEM Polarity**: SmartSEM aperture alignment Y-axis is inverted relative to standard Cartesian coordinates: smaller/negative Y values move the beam alignment UP, and larger positive Y values move it DOWN.
- **Fail-Safe Restoration & Error Recovery**: If a calibration sweep is aborted, fails, times out, is cancelled by the user, or if the electron beam goes off during the sweep, the initial microscope aperture alignment coordinates must be guaranteed to be restored on the SEM, and an informative warning dialog displayed.

## 3. In-Scope Boundaries
- `src/aperture_centering.py` (`ApertureCenteringManager`, `evaluate_center_sharpness`, `fit_2d_surface`)
- `src/main_controls_dlg_windows.py` (`ApertureCenteringDlg`)
- `gui/aperture_centering_dlg.ui` (Qt UI layout for manual steering and automated sweep controls)
- `src/sem_control.py` and `src/sem_control_zeiss.py` (`get_aperture_align_limits`)
- `src/default_cfg/system.cfg` and `src/config_template.py` (`aperture_align_limits`, `SYSCFG_NUMBER_KEYS = 56`)
- `src/main_controls.py` (Menu integration under Tools/Calibration)
- `docs/aperture_centering_help.md` (User guide and help documentation)
- `tests/test_aperture_centering.py` (Comprehensive unit and integration test suite)

## 4. Anti-Targets
- Do not attempt closed-loop autofocus or astigmatism correction within this routine (AFSS handles dynamic focal tracking during stack acquisition).
- Do not block the PyQt GUI thread during lengthy multi-frame sweeps or physical diamond cuts.
- Do not mutate global microscope configuration files until the user explicitly approves applying the optimal alignment.
- Do not retain unproved experimental metrics (Radial Symmetry was removed in favor of robust Center Sharpness).
- Do not emit uncontrolled stdout `print()` debug statements; use dedicated logging to `alignment_log.txt`.

## 5. Architectural Discussion & Design

### 5.1 Center Sharpness Evaluation
- Evaluates Sobel gradient magnitude over a circular centered region of interest spanning 98% of the frame radius.
- Highly robust in practical serial section imaging where dominant optical defect is symmetric blurring or overall image defocus.
- Paired with 2D quadratic paraboloid surface regression ($z = ax^2 + by^2 + cxy + dx + ey + f$) to solve for the continuous global peak $(\hat{x}, \hat{y})$ with sub-grid step precision.
- Discarded unproved polar radial symmetry calculations to ensure production stability and predictable convergence.

### 5.2 Acquisition & Deflector Dynamics
- **Snake-Like Sampling Grid**: Sweeps alternate direction on successive rows (row 0: left $\to$ right; row 1: right $\to$ left) starting from the top-left to minimize hysteresis and settling artifacts in electromagnetic deflector coils.
- **Hardware Limits Clamping**: Sweep grid points and manual nudge operations are clamped to `[min_x, max_x, min_y, max_y]`.
- **Settling Time**: When physical cutting is disabled, a 1.0 s dwell time is observed after setting aperture coordinates before image acquisition.
- **Pre-Setting Before Knife Cut**: When physical cutting is enabled, the aperture coordinates for step $i+1$ are set *before* the microtome cut for step $i$ begins. This overlaps electromagnetic deflector settling with the mechanical knife movement (15+ s), eliminating idle time.

### 5.3 Physical Cutting & Charge Mitigation
- Repeated electron beam exposure on non-conductive resin blocks creates severe localized charging and hydrocarbon contamination.
- The manager interleaves physical microtome diamond knife cutting between calibration frames, tracking stage Z advances and updating `last_known_z` across `Microtome`, `Stage`, `Acquisition`, and Main Controls via Qt signals.

### 5.4 Subpixel Image Registration & Shared FOV Crop
- Large aperture deflector changes produce small lateral beam translations.
- Subpixel phase cross-correlation (`utils.compute_shifts_cv2`) and bounding-box cropping (`utils.crop_image_collection`) are active by default to evaluate sharpness strictly on the overlapping field of view without needing a manual user toggle.

### 5.5 Fail-Safe Beam & API Monitoring
- Checks electron beam state (`is_eht_off()` / `is_eht_on()`) before starting and at each step of the sweep. If the beam is turned off or drops mid-sweep, alignment immediately halts, initial coordinates are restored on the SEM, and a modal warning alerts the operator.
- API timeouts and communication exceptions during `set_aperture_align_xy` and `acquire_frame` are caught, safely reinstating initial coordinates to prevent microscope misalignment.
