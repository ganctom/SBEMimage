# PRD: feat/stub-ov-stage-pos

## 1. System Objective
Integrate a 'Get current stage position' button to the Stub Overview dialogue window. The button will read the current stage X and Y coordinates from the microscope and populate `spinBox_X` and `spinBox_Y` in the UI.

## 2. Acceptance Criteria (AC)
- **AC-GUI-STUB-001**: A new QPushButton is added to the Stub Overview UI next to the X and Y coordinate spinboxes. To prevent enlarging the dialog window (current width 252px), the button text will be a compact string such as "Read XY" or "Get XY", fitting neatly in the ~111px remaining space to the right of the spinboxes.
- **AC-GUI-STUB-002**: Clicking the button reads the current X and Y stage coordinates using the existing microscope stage functionality.
- **AC-GUI-STUB-003**: The X and Y spinboxes in the dialog are updated with the retrieved coordinates.

## 3. Hard Constraints
- **Target Runtime**: Python 3.7.6 (x86_64 Rosetta / Conda sbem-py37).
  - NO walrus operator (`:=`).
  - NO PEP 585 generics (`list[str]`); use `typing.List[str]`.
  - NO PEP 604 unions (`int | None`); use `typing.Optional[int]` or `typing.Union`.
  - NO f-strings with `=` (`f"{var=}"`).
- **Hardware Dynamics**: Must not interfere with active acquisitions; standard stage reading should be safe.
- **Fail-Safe Integrity**: If the stage read fails, the UI should not crash (handle exceptions gracefully).

## 4. In-Scope Boundaries
- `gui/stub_ov_dlg.ui`: Add the QPushButton next to the X and Y spinboxes.
- `src/viewport_dlg_windows.py`: Connect the new button's `clicked` signal and implement the slot to fetch stage coordinates and update the spinboxes.

## 5. Anti-Targets
- Do not refactor legacy PyQt GUI code outside feature scope.
- Do not introduce dependencies unsupported by Python 3.7.6.
- Do not change how the Stub Overview acquire process works, only modify the input fields.

## 6. Architectural Discussion & Design
- **Top-Down Specification**: Add `pushButton_get_stage_pos` to UI. Connect to a new slot `get_current_stage_position` in `StubOVDlg` (which resides in `viewport_dlg_windows.py`).
- **Deep Interfaces**: The slot uses `self.sysctrl.microscope.get_stage_xy()` or equivalent existing method.
