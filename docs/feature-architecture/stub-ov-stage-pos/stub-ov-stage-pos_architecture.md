# Stub Overview Stage Position Button Architecture

## 1. Overview & Problem Statement
In SBEMimage, the Stub Overview acquisition dialog (`StubOVDlg`) previously required users to manually enter center coordinates $(X, Y)$ in µm. Operators often position the sample stage at the physical center of the stub using joystick or SEM controls, but had no quick way to copy the stage position into the dialog.
This feature integrates a compact **"Read XY"** button directly next to the $X$ and $Y$ spinboxes in the Stub Overview dialog, without altering the dialog window's width (252px), respecting compact layout constraints.

## 2. Component Design & Signal Flow
- **UI Element**: `pushButton_get_stage_pos` added to `gui/stub_ov_dlg.ui` at geometry `(150, 39, 91, 24)` with text `"Read XY"`.
- **Slot Implementation**: `StubOVDlg.get_current_stage_position()` queries `self.stage.get_xy()`.
- **Coordinate Conversion**: Values returned in µm are rounded to integers via `int(round(coord))` and assigned to `spinBox_X` and `spinBox_Y`.
- **Concurrency & Safety**:
  - `pushButton_get_stage_pos` is disabled during active acquisition alongside `pushButton_acquire` and `spinBox_X`/`spinBox_Y`.
  - Re-enabled upon completion (`STUB OV SUCCESS`).
  - Exceptions during hardware communication are caught and presented cleanly via `QMessageBox.warning`, preventing UI crashes.

## 3. Verification & Testing
- Unit tests in `tests/test_stub_ov_stage_pos.py` verify:
  1. Dialog initialization and window geometry invariant (width = 252px).
  2. Coordinate fetching and spinbox population with rounding.
  3. Exception handling on stage communication errors.
