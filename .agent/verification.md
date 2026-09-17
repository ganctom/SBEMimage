# Verification Protocol: Stage Calibration

## Automated Testing
1. **Mathematical Recovery & Outlier Rejection Test**:
   `python3 src/test_stage_calibration_fit.py`
   Verifies that linear regression extracts correct scale and rotation parameters under noise, properly handles inverted stage axes, and discards outlier runs.
2. **Coordinate System Regression**:
   `python -m py_compile src/main_controls_dlg_windows.py`
   Ensures Python 3.7.6 compatibility and syntax validity.

## Manual Verification Routine
1. Launch the SBEMimage GUI using a microscope simulator or physical SEM backend.
2. Open the **Stage Calibration** dialog.
3. Ensure the **Grid dimension** is selectable (e.g., 3x3), **Frame size** is populated from `STORE_RES`, and **Number of runs** is configured.
4. Verify the automatic default shift is proposed ($\sim 30\%$ FOV) and is strictly $< 50\%$ FOV.
5. Click **Start automatic calibration**.
6. Observe stage movement: verify a 0.6-second settling pause occurs after each move before frame capture.
7. Verify the log outputs the **Least-Squares Fit RMSE** in microns and the number of valid runs.
8. Check the resulting parameter prompt:
   - Scale factor X and Y must be positive and bounded within `[0.1, 10.0]`.
   - Rotation angles must match expected quadrants without inverted negative scales.
