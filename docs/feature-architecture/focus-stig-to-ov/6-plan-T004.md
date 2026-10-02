# Implementation Plan - T-004 Add auto-trigger checkbox and wire logic in acquisition.py [MUTABLE]

## Metadata [MUTABLE]
- **Task ID:** T-004
- **Task Title:** Add checkbox to `AcqSettingsDlg` and wire auto-trigger logic in `acquisition.py`
- **Agent:** 08-implementation-engineer
- **PRD:** `prd.md`
- **ADL:** `focus-stig-to-ov_architecture.md`
- **Tasks:** `tasks.md`
- Status: Completed
- **AC IDs:** AC-FSO-002

## Summary
Add an opt-in checkbox (default ON) in `AcqSettingsDlg` (`gui/acq_settings_dlg.ui`), save its state in configuration, and wire the auto-trigger check in `acquisition.py` prior to overview acquisition.

## Targets, Tests, Done When [MUTABLE]
- **Targets:** `gui/acq_settings_dlg.ui`, `src/main_controls_dlg_windows.py`, `src/acquisition.py`, `src/default_cfg/default.ini`
- **Tests:** `tests/test_focus_stig_to_ov.py`
- **Done when:** When the checkbox is ON, `apply_focus_stig_from_grids` is called before OV acquisition during stack run; when OFF, it is skipped.

## Steps [MUTABLE]
- [x] T-004.1 Add `checkBox_syncOVFocusStig` (default checked) to `gui/acq_settings_dlg.ui`.
- [x] T-004.2 Wire checkbox reading and saving in `AcqSettingsDlg` (`src/main_controls_dlg_windows.py`) and set default in `src/default_cfg/default.ini`.
- [x] T-004.3 Add call in `Acquisition.acquire_overview` in `src/acquisition.py` guarded by config setting and `afss_active`.
- [x] T-004.4 Add integration tests in `tests/test_focus_stig_to_ov.py`.
- [x] T-004.5 Update `CFG_NUMBER_KEYS` to 242 in `src/config_template.py` to match `default.ini` key count.

## File Permissions
- MODIFY: `gui/acq_settings_dlg.ui`
- MODIFY: `src/main_controls_dlg_windows.py`
- MODIFY: `src/acquisition.py`
- MODIFY: `src/default_cfg/default.ini`
- MODIFY: `src/config_template.py`
- MODIFY: `tests/test_focus_stig_to_ov.py`

## Types / methods / interfaces
- Config key: `cfg['overviews']['sync_focus_stig_from_grids'] = 'True'`

## Data / contracts
- Evaluated prior to acquiring overview frames.

## Side-effects / risks
- Safe acquisition loop integration.

## Verification steps
- Syntax check: `~/miniforge3/envs/sbem-py37/bin/python -m py_compile src/acquisition.py`
- Pytest: `~/miniforge3/envs/sbem-py37/bin/python -m pytest tests/test_focus_stig_to_ov.py -k test_acquisition`
