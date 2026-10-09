# Domain Knowledge: Focal Charge Compensation (FCC)

Terminology: **FCC level (%)** = SmartSEM `AP_CC_PRESSURE` (0-100). The docstrings in the code call it "pressure"; in this feature we always say "FCC level".

## Physical Dynamics
- **Focal Charge Compensator (FCC)**: a hardware system (gas injection needle) in ZEISS SEMs that neutralizes local charging on non-conductive samples (such as resin blocks in SBEM).
- **Abrupt changes are unwanted**: they can cause pressure fluctuations in the chamber, destabilize the beam and imaging, or perturb the sample/microtome setup. The ramp spreads a change over minutes.
- **Valve**: opening or closing the FCC valve (`CMD_CC_IN` / `CMD_CC_OUT`) takes time. Default wait is 15 s (configurable 1-60 s); it is not known whether SmartSEM exposes a "valve ready" status, so a fixed wait is used and ON/OFF is verified via `DP_CC_STATUS` afterwards.
- **Level granularity**: the ramp commands levels rounded to 0.1% (the granularity of the existing dialog's spinbox/slider). A small level change over a long duration therefore produces a staircase of 0.1% steps.

## SmartSEM Interface Facts (verified in code)
| Item | Fact |
|---|---|
| `DP_CAPCC_FITTED` | FCC installed (`has_fcc()`); returns False in simulation mode |
| `DP_CC_STATUS` | contains "on" / "off" (`is_fcc_on()`, `is_fcc_off()`) |
| `AP_CC_PRESSURE` | FCC level, get and set (`get_fcc_level()`, `set_fcc_level()`) |
| `CMD_CC_IN` / `CMD_CC_OUT` | FCC on / off (`turn_fcc_on()`, `turn_fcc_off()`) |
| `sem_get` | returns `""` on exception |
| `sem_set`, `sem_execute` | return `0` (= success!) even when an exception occurred. Return values cannot be trusted; the ramp verifies by readback. |
| Existing dialog `turn_on` | re-applies the last stored level right after turning ON (possible spike); the dialog only sets the level while the FCC is ON |
| Existing dialog | created per open, `exec_()` modal, destroyed on close; has a 1 s update thread for state and chamber pressure (not for the level) |

## Implementation Notes
- Ramping is done in software: successive `set_fcc_level()` calls driven by a 1 s `QTimer` in `MainControls` that calls the Qt-free `SEM_SmartSEM.fcc_ramp_tick()`. The tick itself acts every 5 s.
- Levels come from time-based linear interpolation (no drift if a tick is late).
- Tolerance 1.0% is used both for external-interference detection and for step readback verification.
- Existing user `.ini` files get the new keys automatically: `process_cfg` fills missing keys from the default template.

## Open Hardware Questions (to be answered on the microscope, see `verification.md`)
1. Can `AP_CC_PRESSURE` be set while the FCC is OFF, and does turning ON then avoid a spike at the previously stored level?
2. Does the readback of `AP_CC_PRESSURE` lag behind a set during a ramp by more than 1.0%?
3. How long does the valve really need to open/close? Is 15 s a good default?
4. Does ramping during a live acquisition cause COM errors or missed grabs (no extra locking is used)?
