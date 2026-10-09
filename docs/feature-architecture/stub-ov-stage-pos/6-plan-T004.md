# Implementation Plan - T-004 Implement Stage Reading in StubOVDlg

- **Task ID:** T-004
- **Task Title:** Implement Stage Reading in StubOVDlg
- **Agent:** implementation-engineer
- Status: Completed
- **AC IDs:** AC-GUI-STUB-002, AC-GUI-STUB-003

## Summary
Connect `pushButton_get_stage_pos.clicked` to slot `get_current_stage_position` in `StubOVDlg` in `src/viewport_dlg_windows.py`. The slot fetches `stage.get_xy()` and updates `spinBox_X` and `spinBox_Y`.

## Targets, Tests, Done When
- **Targets:** `src/viewport_dlg_windows.py`
- **Tests:** `tests/test_stub_ov_stage_pos.py`
- **Done when:** Clicking button populates `spinBox_X` and `spinBox_Y` with rounded stage coordinates.

## Steps
- [x] T-004.1 Connect `self.pushButton_get_stage_pos.clicked` to `self.get_current_stage_position` in `StubOVDlg.__init__`.
- [x] T-004.2 Implement `get_current_stage_position(self)` method to query `self.stage.get_xy()` and update `spinBox_X` and `spinBox_Y`. Disable/enable button during acquisition.

## File Permissions
- MODIFY: `src/viewport_dlg_windows.py`
