# Focal Charge Compensation (FCC) Ramping Guide

## Overview
The **Focal Charge Compensator (FCC)** ramping feature automates smooth, linear pressure transitions during chamber gas equilibration. It prevents rapid pressure shocks that could cause vacuum instability, specimen damage, or gas flow surges.

Access the FCC controls via the **FCC** button on the Main Controls window or via the SEM settings dialogs.

---

## Ramping Operations

### 1. Ramp Up
- **From OFF:** Pre-sets the FCC flow level to `0.0%`, opens the gas needle valve (`CMD_CC_IN`), and pauses for the configured **Valve settling delay** before steadily incrementing the pressure to the **Ramp Up target level** over the configured **Ramp duration**.
- **From ON (below target):** Directly initiates linear ramping from the current flow level up to the target without resetting to `0%` or re-waiting the valve settling delay.
- **Validation:** If the current level is already at or above the target level, ramping is refused and an informational message is shown.

### 2. Ramp Down
- **Nominal Ramp Down:** Decrements flow linearly over the configured duration until the ramp-down target (`0.0%` nominal) is reached.
- **Automated Turn-OFF:** When the ramp-down reaches `0.0%` and **Turn FCC OFF after Ramp Down** is enabled, the system waits for the valve settling delay and commands the valve closed (`CMD_CC_OUT`). If the valve fails to close, the user is alerted that the FCC remains ON at `0.0%`.
- **Validation:** If the FCC is OFF or already at or below the ramp-down target, ramping down is refused.

### 3. Stopping Mid-Ramp
Clicking **Stop Ramp** in the Charge Compensator dialog immediately halts the ramping state machine. The FCC remains ON at the exact pressure reached when stopped; no hardware command is issued and pending automated shutoffs are cancelled.

---

## Configuration Settings
Click the **Gear (⚙)** button in the Charge Compensator dialog to adjust settings:

- **Ramp Up target level (%)**: Target pressure level (0.1% to 100.0%, default 30.0%).
- **Ramp duration (min)**: Duration over which the ramp transitions linearly (1 to 120 minutes, default 5 min).
- **Valve settling delay (s)**: Settling delay after opening or before closing the gas valve (2 to 600 seconds, default 15 s).
- **Turn FCC OFF after Ramp Down**: Checkbox enabling automated valve shutoff when ramp-down reaches 0.0% (default: checked).

Settings are automatically persisted to `default.ini` under the `[sem]` section:
- `fcc_ramp_target`
- `fcc_ramp_duration_min`
- `fcc_ramp_valve_delay`
- `fcc_ramp_auto_off`

---

## Visual Feedback & Status Indicators

### Main Controls FCC Button
During an active ramp, the **FCC** button on the main window dynamically reflects ramp progression:
- **Valve Opening:** Pale yellow background with tooltip *"Waiting for valve..."*.
- **Ramping (Up or Down):** Left-to-right yellow gradient fill proportional to ramp progress ($0\%$ to $100\%$) with tooltip showing direction and percentage.
- **Valve Closing:** Full yellow fill with tooltip *"Waiting for valve..."*.
- **Idle / Finished:** Reverts to nominal button styling.

### External Interference & Error Protection
- If an operator manually alters the FCC pressure or toggles the valve directly in SmartSEM by more than $1.0\%$ during an automated ramp, SBEMimage immediately aborts the ramp to prevent control conflicts, leaving the FCC at its current state.
- In the event of communication failures or invalid readbacks from the SmartSEM API, the ramp aborts safely with an alert dialog.

### Exit Protection
If the user attempts to close SBEMimage while a ramp is active, a single combined prompt warns:
> *"An FCC ramp is active. If you exit, the ramp is aborted and the FCC stays ON at the current level. Exit anyway?"*

Confirming exit stops the ramp cleanly before disconnecting from the SEM hardware. Declining allows the ramp to continue uninterrupted.

---

## Automated Stack Completion Ramp-Down

In the **Acquisition Settings** dialog (`AcqSettingsDlg`), an **Auto FCC ramp-down when stack finished** checkbox is positioned directly below *Turn off EHT when stack finished*:

- **Operation:** When ticked, upon successful completion of an acquisition stack, SBEMimage automatically initiates an FCC flow ramp-down.
- **Sequence:** The stack acquisition loop waits until the FCC ramp-down has completely finished (or is aborted) before evaluating the *Turn off EHT* setting. If *Turn off EHT when stack finished* is also enabled, the EHT is turned off only after the FCC ramp-down completes.
- **Hardware Availability:** If the connected microscope does not have an FCC unit installed (`has_fcc()` is `False`), the checkbox is automatically greyed out and unchecked in the user interface, while leaving saved settings in configuration files intact.
- **Persistence:** Saved in `default.ini` and `system.cfg` under `[acq] -> fcc_ramp_down_after_stack`.
