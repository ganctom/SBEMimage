# Stub Overview Stage Position Transfer (stub-ov-stage-pos)

SBEMimage allows quick population of the Stub Overview center coordinates directly from the microscope's current stage position. This eliminates manual coordinate entry and speeds up acquisition setup.

---

## Background & Objective

When setting up a Stub Overview mosaic image, operators specify the center coordinates $(X, Y)$ in stage coordinates (µm) and the number of rows and columns.
Previously, users had to manually read the stage coordinates from the SEM interface and type them into the dialog spinboxes.

With this feature:
- A compact **Read XY** button is integrated directly next to the $X$ and $Y$ coordinate spinboxes in the **Acquire Stub Overview** dialog window.
- Clicking **Read XY** immediately queries the current stage coordinates and populates `spinBox_X` and `spinBox_Y` with rounded integer values.

---

## How to Use

1. **Position the Microscope**:
   - Using the microscope joystick or SEM control software, navigate the stage to the desired center of the stub overview image.

2. **Open the Stub Overview Dialog**:
   - In the **Viewport** window, select **Acquire Stub Overview...** (or click the corresponding toolbar button).

3. **Read Stage Position**:
   - In the **Centre coordinates (X, Y) in µm** section, click the **Read XY** button.
   - The $X$ and $Y$ spinboxes will instantly update to match the current stage location.

4. **Start Acquisition**:
   - Set the desired grid size (rows and columns) and click **Image stub**.

---

## Safety and Design Considerations

- **Dialog Geometry Invariant**:
  - The dialog maintains its compact 252 px window width. The "Read XY" button fits neatly into the available space to the right of the spinboxes.
- **Acquisition Lock**:
  - The "Read XY" button is automatically disabled during an ongoing stub overview acquisition, alongside the coordinate spinboxes and the "Image stub" button, preventing accidental changes while imaging.
- **Fail-Safe Error Handling**:
  - If stage communication fails or times out, the error is caught safely and displayed via an informative message box (`Error reading stage position`) without causing the dialog or application to crash. Existing coordinate values remain unchanged.
