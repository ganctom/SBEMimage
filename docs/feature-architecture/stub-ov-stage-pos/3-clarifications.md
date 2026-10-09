# 3. Clarifications

## Coverage Map
- Feature context: answered
- Platform context: answered
- Tech decision posture: answered
- Existing consumers and compatibility expectation: not-applicable-with-reason (no consumers, it's a UI button)
- Migration or rollout needs: not-applicable-with-reason (no migration)
- Stack constraints: not-applicable-with-reason (standard PyQt5)
- Versioning or contract stability: not-applicable-with-reason
- Data migration: not-applicable-with-reason

## Log

- **CL-STUB-OV-001**: The goal is to add a button that populates the X and Y coordinate spinboxes (`spinBox_X`, `spinBox_Y`) in the Stub Overview dialog with the current stage coordinates.
- **CL-STUB-OV-002**: Use the existing stage reading functionality from the microscope object.
- **CL-STUB-OV-003**: The button should be located next to the X and Y spinboxes in the UI.
