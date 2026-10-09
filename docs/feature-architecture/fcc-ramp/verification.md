# Verification Protocol: fcc-ramp

## Automated Testing
Commands (Python 3.7.6 environment):
1. Pre-flight syntax check on each modified file:
   `~/miniforge3/envs/sbem-py37/bin/python -m py_compile src/<modified_file>.py`
2. Feature tests (token-optimized runner):
   `~/miniforge3/envs/sbem-py37/bin/python agent_test.py tests/test_fcc_ramp.py`

Test strategy: instantiate `SEM_SmartSEM` in simulation mode (the `pythoncom` import is guarded, so it works on macOS), replace `get_fcc_level`, `set_fcc_level`, `is_fcc_on`, `turn_fcc_on`, `turn_fcc_off` with a small fake, and drive time through `fcc_ramp_tick(now)`.

| Test | PRD scenario |
|---|---|
| Ramp Up from OFF: order set 0 -> ON -> wait -> ramp; reaches exactly target | 1 |
| Ramp Down with Auto-OFF: reaches 0, waits, turns OFF | 2 |
| Ramp Down without Auto-OFF: stays ON at 0 | 3 |
| Stop mid-ramp (up and down) leaves level unchanged, state IDLE | 4 |
| External level change > 1.0% aborts (`ABORTED_EXTERNAL`); change <= 1.0% does not | 5 |
| `stop_fcc_ramp()` from exit path cancels pending Auto-OFF, issues no hardware command | 6 |
| Non-numeric readback or readback off by > 1.0% after a set aborts (`ABORTED_ERROR`); exceptions from primitives abort | 7 |
| Ramp Up refused when level >= target; message returned; nothing started | 8 |
| Ramp Up from ON starts from current level without 0 reset or valve wait | 9 |
| Ramp Down refused at 0%; message returned | 10 |
| Ramp Down from ON starts from current level | 11 |
| Stop during VALVE_OPENING and VALVE_CLOSING leaves FCC ON at 0 | 12a, 12b |
| FCC reported OFF during RAMPING / VALVE_CLOSING aborts | 13 |
| FCC not ON after valve delay aborts | 14 |
| Auto-OFF failure reports `AUTO_OFF_FAILED`, FCC stays ON at 0 | 15 |
| Interpolation: 29% -> 30% over 5 min gives 0.1% steps, monotonic, last value exactly 30.0; late ticks do not drift | 1, 9 |
| Duration 1..120 min accepted; settings round-trip through `save_to_cfg` / load | 17 |
| `check_number_of_entries()` True for `default.ini` (246 keys) and `system.cfg` | 17 |
| Offscreen render of `charge_compensator_settings_dlg.ui`: no overlapping widget rectangles; dialog contains all widgets | GUI |

## Physical Instrument Manual Verification Routine
1. **Open question 1:** with FCC OFF, set `AP_CC_PRESSURE` to 0, turn the FCC ON, and watch the chamber pressure/FCC readout. No spike at the previously stored level is expected.
2. **Ramp Up from OFF** with defaults (30%, 5 min, 15 s): verify the valve wait, the steady increase, exact end value, and the yellow fill progressing left-to-right on the main-window FCC button.
3. **Open question 2:** during a ramp, compare commanded levels with `get_fcc_level()` readbacks; confirm the 1.0% tolerance gives no false aborts. Adjust `FCC_RAMP_TOLERANCE` if needed.
4. **Ramp Down** with Auto-OFF on and off; confirm the valve closes after the delay and the UI is restored.
5. **Stop Ramp** mid-flight, and during both valve waits.
6. **External interference:** change the FCC level, then toggle FCC OFF, directly in SmartSEM during a ramp; each must abort with a message and leave the FCC untouched.
7. **Dialog behaviour:** close the FCC dialog during a ramp, work in SBEMimage, reopen it: controls greyed out, "Stop Ramp" shown on the right button, live level displayed.
8. **Exit during ramp:** the combined prompt appears; confirming leaves the FCC ON at the current level.
9. **Open question 4:** run a ramp during a live acquisition; check the log for COM errors and check for missed grabs.
10. **Open question 3:** note the real valve open/close time and confirm the 15 s default.
11. **Settings:** change values in the gear-wheel panel, save config, restart, confirm persistence; confirm out-of-range values cannot be entered.
12. **Layout:** inspect the enlarged FCC dialog on the microscope PC: no overlapping or clipped widgets.
