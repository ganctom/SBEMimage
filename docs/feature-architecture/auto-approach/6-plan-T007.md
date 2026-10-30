# Implementation Plan - T-007 Gatan 3View .ack/.ac2/.err Handshake Hardening [MUTABLE]

## Metadata [MUTABLE]
- **Task ID:** T-007
- **Task Title:** Harden Gatan 3View `near_knife()`, `clear_knife()`, and `do_full_approach_cut()` `.ack`/`.ac2`/`.err` Handshake Verification in `src/microtome_control_gatan.py`, `src/microtome_control.py`, and `src/microtome_control_mock.py` (`dm/*.s` Unmodified)
- **Agent:** `implementation-engineer`
- **PRD:** `1-prd.md`
- **ADL:** `2-adl.md`
- **Tasks:** `5-tasks.md`
- **AC IDs:** `AC-SBEM-AUTO_APPROACH-002`, `AC-SBEM-AUTO_APPROACH-004`, `AC-SBEM-AUTO_APPROACH-005`
- Status: Completed

## Summary
Harden Gatan 3View knife and approach cut operations in `src/microtome_control_gatan.py`, update base class contracts in `src/microtome_control.py`, and implement corresponding mock behavior in `src/microtome_control_mock.py` without modifying DigitalMicrograph scripts (`dm/*.s` unmodified per `AD-AUTO_APPROACH-008`).
Specifically:
1. `_send_dm_command()`: Delete any stale `self.ERROR_FILE` (`DMcom.err`) and `self.WARNING_FILE` via `utils.try_to_remove(...)` alongside `OUTPUT_FILE`, `ACK_FILE`, and `ACK_CUT_FILE` prior to writing/renaming `INPUT_FILE` to `COMMAND_FILE` (preventing 0.1s polling race conditions).
2. `near_knife() -> bool`:
   - Pre-entry guard: `if self.error_state != Error.none: return False`
   - Send command `MicrotomeStage_Near` via `_send_dm_command()`
   - Post-send guard: `if self.error_state != Error.none: return False`
   - Poll for `self.ERROR_FILE` (`.err`) and `self.ACK_FILE` (`.ack`) with 0.1s sleep up to 10.0s timeout
   - If `.err` exists, set `self.error_state = Error.cutting`, log error via `utils.log_error('KNIFE', ...)`, and return `False`
   - If `.ack` found, return `True`
   - On timeout without `.ack`, set `self.error_state = Error.dm_comm_response`, log error via `utils.log_error('KNIFE', ...)`, and return `False`.
3. `clear_knife() -> bool`:
   - Pre-entry guard: `if self.error_state != Error.none: return False`
   - Send command `MicrotomeStage_Clear` via `_send_dm_command()`
   - Post-send guard: `if self.error_state != Error.none: return False`
   - Poll for `self.ERROR_FILE` (`.err`) and `self.ACK_FILE` (`.ack`) with 0.1s sleep up to 10.0s timeout
   - If `.err` exists, set `self.error_state = Error.cutting`, log error via `utils.log_error('KNIFE', ...)`, and return `False`
   - If `.ack` found, return `True`
   - On timeout without `.ack`, set `self.error_state = Error.dm_comm_response`, log error via `utils.log_error('KNIFE', ...)`, and return `False`.
4. `do_full_approach_cut() -> bool`:
   - Pre-entry guard: `if self.error_state != Error.none: return False`
   - Send `MicrotomeStage_FullApproachCut` via `_send_dm_command()`
   - Post-send guard: `if self.error_state != Error.none: return False`
   - Adaptive poll for `self.ACK_CUT_FILE` (`.ac2`) or `self.ERROR_FILE` (`.err`) at 0.2s intervals up to `self.full_cut_duration` (preventing double-sleep and idle lag once .ac2 arrives)
   - Call `self.check_cut_cycle_status()` to verify `.ac2` completion, handle grace window, and detect `.err`
   - On `.err` or timeout, log error via `utils.log_error('KNIFE', ...)`, and return `False` if `self.error_state != Error.none`
   - Return `True` on verified `.ac2` cut completion.
5. Base class `Microtome` in `src/microtome_control.py`: Document `-> bool` return signatures and keep `raise NotImplementedError`.
6. `Microtome_Mock` in `src/microtome_control_mock.py`: Return `False` if `self.error_state != Error.none`, `True` on nominal state.
7. Unit tests in `tests/test_auto_approach.py`: Test `Microtome_3View`, `Microtome_Mock`, and `Microtome` base contracts under redirected temp paths with sleep patched.

## Targets, Tests, Done When [MUTABLE]
- **Targets:** `src/microtome_control_gatan.py`, `src/microtome_control.py`, `src/microtome_control_mock.py`
- **Tests:** `tests/test_auto_approach.py`
- **Done when:** `~/miniforge3/envs/sbem-py37/bin/python agent_test.py tests/test_auto_approach.py` passes with zero errors; unit tests assert `.ack` / `.err` / timeout verification and boolean returns for `near_knife()`, `clear_knife()`, and `do_full_approach_cut()` across `Microtome_3View` (nominal `.ack`/`.ac2`, `.err` failure, timeout, delayed-.ac2 recovery, and faulted-state entry guards), `Microtome_Mock` (nominal `True`, faulted `False`), and `Microtome` base (`NotImplementedError`).

## Steps [MUTABLE]
- [x] T-007.1 **[implementation-engineer]** Update `Microtome` base class method signatures and docstrings in `src/microtome_control.py` for `near_knife() -> bool`, `clear_knife() -> bool`, and `do_full_approach_cut() -> bool`.
- [x] T-007.2 **[implementation-engineer]** Update `Microtome_3View._send_dm_command()` in `src/microtome_control_gatan.py` to delete any pre-existing `self.ERROR_FILE` and `self.WARNING_FILE` via `utils.try_to_remove(...)` alongside `OUTPUT_FILE`, `ACK_FILE`, and `ACK_CUT_FILE` prior to writing/renaming `INPUT_FILE` to `COMMAND_FILE` (AR2-T007-002).
- [x] T-007.3 **[implementation-engineer]** Implement boolean `.ack`/`.err` handshake polling with entry and post-send error guards in `Microtome_3View.near_knife()` and `Microtome_3View.clear_knife()` in `src/microtome_control_gatan.py`:
  - Check `if self.error_state != Error.none: return False` at method entry (AR2-T007-001);
  - Send command via `_send_dm_command()`;
  - Check `if self.error_state != Error.none: return False` immediately after send (AR2-T007-001);
  - Poll for `self.ERROR_FILE` (`.err`) and `self.ACK_FILE` (`.ack`) with 0.1s sleep up to 10.0s timeout;
  - On `.err`, set `self.error_state = Error.cutting`, call `utils.log_error('KNIFE', ...)`, and return `False` (AR2-T007-005);
  - On `.ack`, return `True`;
  - On timeout without `.ack`, set `self.error_state = Error.dm_comm_response`, call `utils.log_error('KNIFE', ...)`, and return `False` (AR2-T007-005).
- [x] T-007.4 **[implementation-engineer]** Implement adaptive `.ac2`/`.err` status verification with entry and post-send error guards in `Microtome_3View.do_full_approach_cut()` in `src/microtome_control_gatan.py`:
  - Check `if self.error_state != Error.none: return False` at method entry (AR2-T007-001);
  - Send `MicrotomeStage_FullApproachCut` via `_send_dm_command()`;
  - Check `if self.error_state != Error.none: return False` immediately after send (AR2-T007-001);
  - Poll for `self.ACK_CUT_FILE` (`.ac2`) or `self.ERROR_FILE` (`.err`) at 0.2s steps up to `self.full_cut_duration` (AR2-T007-003);
  - Call `self.check_cut_cycle_status()`;
  - If `self.error_state != Error.none`: call `utils.log_error('KNIFE', ...)` and return `False`;
  - Return `True` on verified `.ac2` cut completion.
- [x] T-007.5 **[implementation-engineer]** Implement boolean returns and error guards in `Microtome_Mock.near_knife()`, `Microtome_Mock.clear_knife()`, and `Microtome_Mock.do_full_approach_cut()` in `src/microtome_control_mock.py`: return `False` if `self.error_state != Error.none`, `True` otherwise.
- [x] T-007.6 **[implementation-engineer]** Add unit test suite in `tests/test_auto_approach.py` (§1.4.3):
  - Test `Microtome` base class methods raise `NotImplementedError` (AR2-T007-004);
  - Test `Microtome_Mock` returns `True` nominally and `False` when `error_state != Error.none` across `near_knife()`, `clear_knife()`, and `do_full_approach_cut()` (AR2-T007-004);
  - Test `Microtome_3View` initialized with `simulation_mode='True'`, file attributes (`INPUT_FILE`, `OUTPUT_FILE`, `COMMAND_FILE`, `ACK_FILE`, `ACK_CUT_FILE`, `ERROR_FILE`, `WARNING_FILE`) redirected into `self.test_dir`, and `sleep` patched (AR2-T007-005):
    - `test_microtome_near_clear_handshake_verification()`: nominal `.ack` arrival (`True`), pre-existing `.err` deletion on send (AR2-T007-002), `.err` failure (`False`, `Error.cutting`), timeout (`False`, `Error.dm_comm_response`), send failure (`False`, `Error.dm_comm_send`), and faulted-state entry rejection (`False`, preserves `Error.mismatch_z`) (AR2-T007-001);
    - `test_microtome_do_full_approach_cut_ac2_verification()`: nominal `.ac2` confirmation (`True`), `.err` failure (`False`, `Error.cutting`), missing-`.ac2` timeout (`False`, `Error.dm_comm_response`), delayed-`.ac2` grace recovery (`True`, `Error.none`) (AR2-T007-004), and faulted-state entry rejection (`False`) (AR2-T007-001).
- [x] T-007.7 **[implementation-engineer]** Run bytecode pre-flight check (`~/miniforge3/envs/sbem-py37/bin/python -m py_compile src/microtome_control_gatan.py src/microtome_control.py src/microtome_control_mock.py tests/test_auto_approach.py`) and verify green test suite via `~/miniforge3/envs/sbem-py37/bin/python agent_test.py tests/test_auto_approach.py`.
- [x] T-007.8 **[implementation-engineer]** Update `docs/feature-architecture/auto-approach/5-tasks.md` to mark `[x]` in the `Dependencies` table, update line 35 to `*Status: Completed*`, and set `Status: Completed` in `6-plan-T007.md:11` (AR2-T007-006).

## File Permissions
- MODIFY: `src/microtome_control_gatan.py`
- MODIFY: `src/microtome_control.py`
- MODIFY: `src/microtome_control_mock.py`
- MODIFY: `tests/test_auto_approach.py`
- MODIFY: `docs/feature-architecture/auto-approach/5-tasks.md`

## Types / methods / interfaces
- `src/microtome_control_gatan.py`:
  - `Microtome_3View._send_dm_command(self, cmd, set_values=[])`
  - `Microtome_3View.near_knife(self) -> bool`
  - `Microtome_3View.clear_knife(self) -> bool`
  - `Microtome_3View.do_full_approach_cut(self) -> bool`
- `src/microtome_control.py`:
  - `Microtome.near_knife(self) -> bool`
  - `Microtome.clear_knife(self) -> bool`
  - `Microtome.do_full_approach_cut(self) -> bool`
- `src/microtome_control_mock.py`:
  - `Microtome_Mock.near_knife(self) -> bool`
  - `Microtome_Mock.clear_knife(self) -> bool`
  - `Microtome_Mock.do_full_approach_cut(self) -> bool`

## Data / contracts
- Hardware Handshake Invariants:
  - `_send_dm_command(cmd)` deletes existing `ERROR_FILE` (`.err`), `WARNING_FILE`, `ACK_FILE` (`.ack`), `ACK_CUT_FILE` (`.ac2`), and `OUTPUT_FILE` (`.out`) before creating the command trigger file.
  - Entry guard: calling `near_knife()`, `clear_knife()`, or `do_full_approach_cut()` when `self.error_state != Error.none` immediately returns `False` without sending commands to DM or altering `error_state`.
  - Post-send guard: if `_send_dm_command()` sets `self.error_state != Error.none` (e.g. `Error.dm_comm_send`), method immediately returns `False` without polling or sleeping.
  - Adaptive cut waiting: `do_full_approach_cut()` polls for `.ac2` / `.err` at 0.2s steps up to `self.full_cut_duration`, proceeding immediately once DM signals completion.
  - DM script writes `.ack` when knife motion commands (`MicrotomeStage_Near`, `MicrotomeStage_Clear`) complete.
  - DM script writes `.ac2` when approach cut cycle (`MicrotomeStage_FullApproachCut`) completes stroke down, deactivating oscillator and stroke up.
  - DM script writes `.err` if any hardware fault occurs during command processing or physical motion.
  - On error, `error_state` is set to `Error.cutting` or `Error.dm_comm_response`, `utils.log_error('KNIFE', ...)` is called, and the method returns `False`.
  - Python 3.7.6 compatibility: no walrus operators, no PEP 585 generics, no PEP 604 unions.

## Side-effects / risks
- Existing manual approach dialog (`ApproachDlg.approach_thread()` in `src/main_controls_dlg_windows.py:4631-4632`) previously had `sleep(self.approach_cut_duration)` after `do_full_approach_cut()`. Adaptive polling in `do_full_approach_cut()` eliminates idle wait inside the method once `.ac2` arrives, avoiding redundant stalls before T-009 refactors `ApproachDlg`.
- Standard stack acquisition calls `do_full_cut()`, not `do_full_approach_cut()`. Normal acquisitions remain untouched.
- Katana microtome (`src/microtome_control_katana.py`) and DM scripts (`dm/*.s`) are strictly unmodified.
