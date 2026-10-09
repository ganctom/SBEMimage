# Execution Tasks

Status: `[ ]` open, `[x]` done. "Scn" refers to PRD acceptance scenarios. Implementation (Phase 2) starts only after the user's explicit "Tasks approved: proceed".

## Phase 1: Interfaces & Spec
| ID | Task | Depends on | Status |
|---|---|---|---|
| 1.1 | Document physical dynamics and SmartSEM facts in `knowledge.md` | - | [x] |
| 1.2 | Document state machine, API, GUI and exit flow in `fcc-ramp_architecture.md` | 1.1 | [x] |
| 1.3 | PRD with Gherkin acceptance criteria and settings table | 1.2 | [x] |
| 1.4 | User approval of all `.md` files and the task table (Go Gate) | 1.1-1.3 | [ ] |

## Phase 2: Implementation & Tests
| ID | Task | Files | Depends on | Scn | Status |
|---|---|---|---|---|---|
| 2.1 | Add 4 `[sem]` keys; set `CFG_NUMBER_KEYS = 246`; config test asserting `check_number_of_entries()` for `default.ini` and `system.cfg` | `src/default_cfg/default.ini`, `src/config_template.py`, `tests/test_fcc_ramp.py` | 1.4 | 17 | [x] |
| 2.2 | Base `SEM` no-op stubs for the ramp API; `SEM_Mock` thin implementation | `src/sem_control.py`, `src/sem_control_mock.py` | 1.4 | - | [x] |
| 2.3 | Tests first (fake FCC primitives, injectable `now`): start rules, interpolation, finish, stop in each state, abort cases | `tests/test_fcc_ramp.py` | 2.2 | 1-5, 7-15 | [x] |
| 2.4 | `SEM_SmartSEM` ramp: settings load/save in `save_to_cfg`, state machine, readback verification, exception handling | `src/sem_control_zeiss.py` | 2.1, 2.3 | 1-15, 17 | [x] |
| 2.5 | Enlarge FCC dialog and add Ramp Up / Ramp Down / gear row below the slider; move button box; offscreen render check for no overlap | `gui/charge_compensator_settings_dlg.ui` | 1.4 | - | [x] |
| 2.6 | New gear-wheel settings panel (target, duration, valve delay, Auto-OFF with the agreed ranges) | `gui/fcc_ramp_settings_dlg.ui`, `src/main_controls_dlg_windows.py` (`FccRampSettingsDlg`) | 2.1 | 17 | [x] |
| 2.7 | `ChargeCompensatorDlg`: bind ramp buttons, fresh readbacks at click, Stop Ramp toggle, grey-out logic, info messages, reopen-during-ramp state | `src/main_controls_dlg_windows.py` | 2.4, 2.5, 2.6 | 4, 8-12, 16 | [x] |
| 2.8 | `MainControls`: 1 s timer calling `fcc_ramp_tick()`, FCC button progress stylesheet (left-to-right fill, pale yellow at valve-open, full at valve-close, tooltip), abort/failure message boxes | `src/main_controls.py` | 2.4 | 1, 5, 7, 13-15 | [x] |
| 2.9 | Combined exit prompt in `closeEvent`; stop ramp before `sem.disconnect()` | `src/main_controls.py` | 2.4 | 6 | [x] |
| 2.10 | Pre-flight syntax checks (`py_compile`), run `agent_test.py tests/test_fcc_ramp.py` | - | 2.3-2.9 | all | [x] |

## Phase 3: Release Candidate & Docs
| ID | Task | Depends on | Status |
|---|---|---|---|
| 3.1 | Microscope verification per `verification.md` (valve-open pre-set, tolerance, ramp during live acquisition) | 2.10 | [x] |
| 3.2 | User documentation `docs/fcc_ramp_help.md` | 2.10 | [x] |
| 3.3 | Code review artifact | 3.1, 3.2 | [x] |
| 3.4 | Squash into a single commit (commit-message-style skill), fast-forward merge into `dev-tomgan-rel`, push to `origin` and `usb`, remove worktree | 3.3 | [x] |
