# Verification Protocol: stub-ov-stage-pos

## Automated Testing
1. Dedicated test runner:
   `~/miniforge3/envs/sbem-py37/bin/python -m pytest tests/test_stub_ov_stage_pos.py`
   Or using token-optimized test runner:
   `~/miniforge3/envs/sbem-py37/bin/python agent_test.py tests/test_stub_ov_stage_pos.py`

2. Python 3.7 syntax and bytecode compilation:
   `~/miniforge3/envs/sbem-py37/bin/python -m py_compile src/viewport_dlg_windows.py`

## Manual Verification Routine on SEM / Simulator
1. Launch SBEMimage in simulation or live SEM mode.
2. Navigate the microscope stage to known test coordinates (e.g. $X = 1500$, $Y = -2500$).
3. Open Viewport $\to$ Stub Overview dialog (`Acquire Stub Overview`).
4. Verify the dialog layout: dialog width is unchanged (252px), and the "Read XY" button sits directly next to the X and Y spinboxes.
5. Click **Read XY**.
6. Verify that `spinBox_X` updates to `1500` and `spinBox_Y` updates to `-2500`.
7. Start stub overview acquisition and verify the "Read XY" button is disabled while busy.
