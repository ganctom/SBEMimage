# Execution Ledger: feat-aperture-centering

## Phase 1: Aperture Centering Implementation & Verification
- [x] 1.1 Extract SmartSEM Remote API parameters for aperture alignment (`AP_APERTURE_ALIGN_X`, `AP_APERTURE_ALIGN_Y`).
- [x] 1.2 Implement aperture align getters/setters in `SEM` base class (`src/sem_control.py`), `SEM_SmartSEM` (`src/sem_control_zeiss.py`), and `SEM_Mock` (`src/sem_control_mock.py`).
- [x] 1.3 Implement `evaluate_radial_symmetry` using polar mapping (`cv2.warpPolar`) and `ApertureCenteringManager` with asynchronous execution, logging, and 2D heatmap generation (`src/aperture_centering.py`).
- [x] 1.4 Create `gui/aperture_centering_dlg.ui` dialog with manual live steering arrow buttons, sweep settings, progress bar, and optimal alignment display.
- [x] 1.5 Add `actionApertureCentering` to Calibration menu in `gui/main_window.ui` and wire in `src/main_controls.py`.
- [x] 1.6 Implement `ApertureCenteringDlg` in `src/main_controls_dlg_windows.py`.
- [x] 1.7 Add unit and integration test suite in `tests/test_aperture_centering.py` and verify passing with `agent_test.py`.

## Phase 2: Feature Refinements
- [x] 2.1 Add 1-second delay after each aperture shift for settling time (`src/aperture_centering.py`).
- [x] 2.2 Add pixel size selector and physical cut checkbox to `gui/aperture_centering_dlg.ui` and `src/main_controls_dlg_windows.py`.
- [x] 2.3 Implement physical cut execution during the sweep loop (`src/aperture_centering.py`).
- [x] 2.4 Summarize final optimal setting in `main_controls` log window and main log file.
