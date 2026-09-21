# Verification Protocol: Aperture Centering

## Automated Testing
1. Run test suite:
   `~/miniforge3/envs/sbem-py37/bin/python agent_test.py tests/test_aperture_centering.py`
   Verifies:
   - Polar coordinate radial symmetry metrics (`cv2.warpPolar` Tenengrad gradients).
   - Real-time manual coil nudge calculations.
   - 2D grid sweep, artifact creation (`alignment_log.txt`, `sharpness_data.json`, `aperture_centering_heatmap.png`), and optimal coordinate localization.
   - `ApertureCenteringDlg` UI dialog initialization and signals.

2. Syntax and bytecode compilation:
   `~/miniforge3/envs/sbem-py37/bin/python -m py_compile src/utils.py src/sem_control.py src/sem_control_zeiss.py src/sem_control_mock.py src/aperture_centering.py src/main_controls_dlg_windows.py src/main_controls.py`
