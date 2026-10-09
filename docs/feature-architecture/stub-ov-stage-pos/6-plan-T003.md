# Implementation Plan - T-003 Add Read XY Button to UI

- **Task ID:** T-003
- **Task Title:** Add Read XY Button to UI
- **Agent:** implementation-engineer
- Status: Completed
- **AC IDs:** AC-GUI-STUB-001

## Summary
Add `pushButton_get_stage_pos` labeled "Read XY" into `gui/stub_ov_dlg.ui` next to `spinBox_Y` without modifying dialog geometry (keeping width 252).

## Targets, Tests, Done When
- **Targets:** `gui/stub_ov_dlg.ui`
- **Tests:** Verify UI loads without error in PyQt5.
- **Done when:** `pushButton_get_stage_pos` exists in `gui/stub_ov_dlg.ui`, positioned at approx x=150, y=39, width=90, height=24.

## Steps
- [x] T-003.1 Inspect current UI elements around coordinates (y=40).
- [x] T-003.2 Insert `QPushButton` with `objectName="pushButton_get_stage_pos"` and text "Read XY".
- [x] T-003.3 Add `pushButton_get_stage_pos` to tabstops list.

## File Permissions
- MODIFY: `gui/stub_ov_dlg.ui`
