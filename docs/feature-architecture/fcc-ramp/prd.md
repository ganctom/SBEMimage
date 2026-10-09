# Product Requirements Document (PRD)

## System Objective
Implement an automated Focal Charge Compensation (FCC) ramp feature for ZEISS SmartSEM. The user can gradually raise ("Ramp Up") or lower ("Ramp Down") the **FCC level (%)** over a user-defined duration, instead of making abrupt changes that could destabilize the electron optics or the sample. The ramp runs in the background and does not block SBEMimage.

Terminology: this document uses **"FCC level (%)"** for the value of SmartSEM `AP_CC_PRESSURE` (0-100).

## Hard Constraints
- STRICTLY Python 3.7.6 (no walrus operator, no PEP 585 generics like `list[str]`, no PEP 604 unions like `int | None`, no f-strings with `=`).
- The ramp runs in the background. The FCC dialog (`ChargeCompensatorDlg`) can be closed while the ramp continues.
- The ramp logic lives in `SEM_SmartSEM` (`src/sem_control_zeiss.py`) and is Qt-free. The base class `SEM` gets no-op stubs; `SEM_Mock` gets a thin implementation.
- The shared SmartSEM wrappers `sem_get` / `sem_set` / `sem_execute` are NOT modified (they swallow exceptions; the ramp verifies every step by readback instead).
- Respect `.antigravitygitignore`. Do not modify `magc/`.
- Config invariant (`GEMINI.md` section 6): adding 4 keys to `default.ini` requires `CFG_NUMBER_KEYS` 242 -> 246 in `src/config_template.py`, plus a `check_number_of_entries()` test.

## Settings (gear-wheel panel, persisted in `default.ini` section `[sem]`)
| Key | Meaning | Default | Allowed range |
|---|---|---|---|
| `fcc_ramp_target` | Target FCC level for Ramp Up (%) | 30 | 0.1 - 100 (*) |
| `fcc_ramp_duration_min` | Ramp duration (minutes) | 5 | 1 - 120 |
| `fcc_ramp_valve_delay` | Wait for FCC valve to open/close (s) | 15 | 1 - 60 (*) |
| `fcc_ramp_auto_off` | Turn FCC OFF after Ramp Down reaches 0% | True | True / False |

(*) Target minimum and valve-delay range are proposed values, not yet confirmed by the user.

## In-Scope Boundaries
- `src/sem_control_zeiss.py`: ramp state machine in `SEM_SmartSEM` (start/stop/tick/status, settings load/save).
- `src/sem_control.py`: base-class no-op stubs for the ramp API.
- `src/sem_control_mock.py`: thin ramp implementation for simulation and tests.
- `src/default_cfg/default.ini` and `src/config_template.py`: 4 new `[sem]` keys, `CFG_NUMBER_KEYS = 246`.
- `gui/charge_compensator_settings_dlg.ui`: enlarge dialog and add a row (Ramp Up, Ramp Down, gear button) below the FCC level slider.
- `gui/fcc_ramp_settings_dlg.ui` (new): gear-wheel settings panel.
- `src/main_controls_dlg_windows.py`: `ChargeCompensatorDlg` changes and new `FccRampSettingsDlg`.
- `src/main_controls.py`: 1 s `QTimer` driving the ramp, FCC button progress styling, ramp warning/abort messages, combined exit prompt in `closeEvent`.
- `tests/test_fcc_ramp.py` (new) and a config-entry-count test.
- `docs/fcc_ramp_help.md` (user documentation, Phase 3).

## Anti-Targets
- Do not block acquisitions or autofocus while a ramp is running.
- Do not change `sem_get` / `sem_set` / `sem_execute` or any other SmartSEM feature.
- Do not add locking around SmartSEM calls (existing practice; verified on the microscope instead).
- Do not refactor legacy PyQt GUI code outside the FCC dialog.
- Do not implement the ramp for MultiSEM, Tescan or other devices (stubs only).
- Do not touch `magc/`.

## Acceptance Criteria

**Scenario 1: Ramp Up from OFF state**
```gherkin
Given the FCC is currently OFF
And the ramp-up target is 30%
When the user clicks "Ramp Up"
Then the system sets the FCC level to 0% and then commands the FCC to turn ON
And the system waits for the Valve Delay (default 15 seconds)
And the FCC level increases steadily to reach exactly 30% over the Ramp Duration
And the main window FCC button is filled with yellow proportionally to the ramp progress
And the manual FCC controls and the gear-wheel button are greyed out until the ramp is finished
```

**Scenario 2: Ramp Down to 0% with Auto-OFF**
```gherkin
Given the FCC is ON at a positive FCC level
And the Auto-OFF setting is enabled
When the user clicks "Ramp Down"
Then the FCC level decreases steadily to reach exactly 0% over the Ramp Duration
And the system waits for the Valve Delay
And the FCC is automatically commanded to turn OFF
And the UI is restored to normal state
```

**Scenario 3: Nominal Ramp Down to 0% (Auto-OFF disabled)**
```gherkin
Given the FCC is ON at a positive FCC level
And the Auto-OFF setting is disabled
When the user clicks "Ramp Down"
Then the FCC level decreases steadily to reach exactly 0% over the Ramp Duration
And the FCC remains ON at 0%
And the UI is restored to normal state
```

**Scenario 4: Stopping a ramp (up or down) mid-flight**
```gherkin
Given an FCC ramp (up or down) is actively running
And the current FCC level is 15%
When the user clicks the "Stop Ramp" button
Then the ramp stops immediately
And the FCC level remains at 15%
And all manual UI controls are re-enabled
And the main window FCC button reverts to its nominal appearance
```

**Scenario 5: External interference aborts the ramp**
```gherkin
Given an FCC ramp is actively running
When the actual FCC level read from SmartSEM differs from the last commanded level by more than 1.0%
Then the system immediately aborts the ramp
And the FCC level remains at the externally set level
And the user is informed that the ramp was aborted due to an external change
And the UI and FCC control window are restored to normal state
```

**Scenario 6: Exiting SBEMimage during an active ramp**
```gherkin
Given an FCC ramp is actively running (in any phase)
When the user attempts to close the SBEMimage application
Then a single exit prompt is displayed stating that the ramp will be aborted and the FCC will stay ON at the current level
And if the user confirms, the ramp is stopped before SmartSEM is disconnected, any pending Auto-OFF is cancelled, and the application closes
And if the user declines, the ramp continues unchanged
```

**Scenario 7: Hardware failure during ramp**
```gherkin
Given an FCC ramp is actively running
When the readback after a commanded step is not a number, or differs from the commanded level by more than 1.0%
Then the system immediately aborts the ramp
And logs the error and displays a warning dialog to the user
And the UI controls are restored, leaving the FCC at the last level read back
```

**Scenario 8: Ramp Up requested when current level is at or above target**
```gherkin
Given the FCC is currently ON and the current FCC level is at or above the ramp-up target level
When the user clicks "Ramp Up"
Then no ramping is initialized
And the system displays an information message that the current level is already at or above the target
```

**Scenario 9: Ramp Up requested when already ON and below target**
```gherkin
Given the FCC is currently ON and the current FCC level is below the ramp-up target level
When the user clicks "Ramp Up"
Then the system initializes the ramp-up procedure starting directly from the current FCC level
And the system does NOT set the level to 0% or wait for the valve delay
```

**Scenario 10: Ramp Down requested when current level is already 0%**
```gherkin
Given the FCC is currently ON and the current FCC level is exactly 0%
When the user clicks "Ramp Down"
Then no ramping is initialized
And the system displays an information message that the current level is already 0%
```

**Scenario 11: Ramp Down requested when already ON and above 0%**
```gherkin
Given the FCC is currently ON and the current FCC level is above 0%
When the user clicks "Ramp Down"
Then the system initializes the ramp-down procedure starting directly from the current FCC level
```

**Scenario 12a: Stopping during the valve-opening wait**
```gherkin
Given an FCC ramp is in the valve-opening wait (before Ramp Up from OFF)
When the user clicks "Stop Ramp"
Then the ramp is cancelled and the FCC remains ON at 0%
```

**Scenario 12b: Stopping during the valve-closing wait**
```gherkin
Given a Ramp Down has reached 0% and is in the valve-closing wait (Auto-OFF pending)
When the user clicks "Stop Ramp"
Then the pending Auto-OFF is cancelled and the FCC remains ON at 0%
```

**Scenario 13: FCC switched OFF externally during a ramp**
```gherkin
Given an FCC ramp is in the ramping phase or in the valve-closing wait
When SmartSEM reports that the FCC is no longer ON
Then the system aborts the ramp, informs the user, and restores the UI without issuing further FCC commands
```

**Scenario 14: Valve fails to open**
```gherkin
Given a Ramp Up from OFF has waited for the Valve Delay
When SmartSEM does not report the FCC as ON
Then the system aborts the ramp, informs the user, and restores the UI
```

**Scenario 15: Auto-OFF fails**
```gherkin
Given a Ramp Down has reached 0% and the Valve Delay has elapsed
When the command to turn the FCC OFF fails (FCC still reported ON)
Then the user is warned that the FCC remains ON at 0%
And the UI is restored to normal state
```

**Scenario 16: Reopening the FCC dialog during a ramp**
```gherkin
Given an FCC ramp was started and the FCC dialog was closed
When the user reopens the FCC dialog
Then the manual controls and the gear-wheel button are greyed out
And the button that started the ramp is labelled "Stop Ramp" while the other ramp button is disabled
And the displayed FCC level follows the live level
```

**Scenario 17: Settings persistence and validation**
```gherkin
Given the user changes ramp settings in the gear-wheel panel within the allowed ranges
When the settings are accepted and the configuration is saved
Then the same values are loaded after restarting SBEMimage
And values outside the allowed ranges cannot be entered
And Ramp Down (target 0%) never changes the stored Ramp Up target
```
