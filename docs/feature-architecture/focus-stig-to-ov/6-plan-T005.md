# Implementation Plan - T-005 Move UI Checkbox [MUTABLE]

## Metadata [MUTABLE]
- **Task ID:** T-005
- **Task Title:** Move UI Checkbox from Acquisition Settings to Autofocus Settings
- **Agent:** 08-implementation-engineer
- **PRD:** `prd.md`
- **ADL:** `focus-stig-to-ov_architecture.md`
- **Tasks:** `tasks.md`
- Status: Completed
- **AC IDs:** AC-FSO-002

## Summary
Remove the overview focus/stig synchronization checkbox from Acquisition Settings and relocate it to Autofocus/Tracking Settings under Tracking mode in General settings, ensuring proper layout spacing and no widget overlap.

## Targets, Tests, Done When [MUTABLE]
- **Targets:** `gui/acq_settings_dlg.ui`, `gui/acq_settings_dlg_mock.ui`, `gui/autofocus_settings_dlg.ui`
- **Tests:** `tests/test_focus_stig_to_ov.py`
- **Done when:** `~/miniforge3/envs/sbem-py37/bin/pytest tests/test_focus_stig_to_ov.py -k test_autofocus_settings_dlg_no_ui_overlap` passes cleanly on Python 3.7.6.

## Steps [MUTABLE]
- [x] T-005.1 Revert `gui/acq_settings_dlg.ui` and `gui/acq_settings_dlg_mock.ui` removing old checkbox.
- [x] T-005.2 Add checkbox to `gui/autofocus_settings_dlg.ui` under Tracking mode in General settings.
- [x] T-005.3 Adjust geometries to prevent overlaps and expand dialog height.
- [x] T-005.4 Add overlap regression test in `tests/test_focus_stig_to_ov.py`.
