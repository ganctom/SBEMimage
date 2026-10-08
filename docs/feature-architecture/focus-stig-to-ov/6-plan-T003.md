# Implementation Plan - T-003 Wire manual trigger button in OVSettingsDlg [MUTABLE]

## Metadata [MUTABLE]
- **Task ID:** T-003
- **Task Title:** Wire manual trigger button in `OVSettingsDlg`
- **Agent:** 08-implementation-engineer
- **PRD:** `prd.md`
- **ADL:** `focus-stig-to-ov_architecture.md`
- **Tasks:** `tasks.md`
- Status: Completed
- **AC IDs:** AC-FSO-001

## Summary
Add a "Copy focus/stig from grid" push button to `gui/overview_settings_dlg.ui` and wire it in `OVSettingsDlg` to trigger `ovm.apply_focus_stig_from_grids(self.gm)`.

## Targets, Tests, Done When [MUTABLE]
- **Targets:** `gui/overview_settings_dlg.ui`, `src/main_controls_dlg_windows.py`
- **Tests:** `tests/test_focus_stig_to_ov.py`
- **Done when:** Clicking the manual button invokes `ovm.apply_focus_stig_from_grids(self.gm)` and shows user feedback/log.

## Steps [MUTABLE]
- [x] T-003.1 Add `pushButton_copyFocusStigFromGrid` to `gui/overview_settings_dlg.ui`.
- [x] T-003.2 Connect button signal in `OVSettingsDlg` in `src/main_controls_dlg_windows.py`.
- [x] T-003.3 Add unit test verifying button connection and trigger in `tests/test_focus_stig_to_ov.py`.

## File Permissions
- MODIFY: `gui/overview_settings_dlg.ui`
- MODIFY: `src/main_controls_dlg_windows.py`
- MODIFY: `tests/test_focus_stig_to_ov.py`

## Types / methods / interfaces
- `OVSettingsDlg.copy_focus_stig_from_grid(self)`

## Data / contracts
- Invokes `self.ovm.apply_focus_stig_from_grids(self.gm)`.
- Updates UI display or logs outcome.

## Side-effects / risks
- GUI layout adjustments in Qt Designer file.

## Verification steps
- Syntax check: `~/miniforge3/envs/sbem-py37/bin/python -m py_compile src/main_controls_dlg_windows.py`
- Pytest: `~/miniforge3/envs/sbem-py37/bin/python -m pytest tests/test_focus_stig_to_ov.py -k test_ov_settings_dlg`
