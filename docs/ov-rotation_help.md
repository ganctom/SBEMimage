# Overview Image Rotation (ov-rotation)

SBEMimage supports arbitrary scan rotation (0.0° – 360.0°) for each Overview (OV) image independently. This enables aligning overview fields of view with specimen tissue geometry, sample edges, or high-magnification acquisition grids.

---

## Accessing and Configuring Overview Rotation

Open the dialog from the **Main Controls** window:
Click on the **OV Setup** button (or via the Overview dropdown).

In the **Overview Setup** dialog:

1. **Rotation angle (°)**:
   - Sets the scan rotation angle for the selected OV.
   - Range: `0.0°` to `360.0°`, with a single step of `1.0°` and one decimal point precision.
   - Located directly below the **Dwell time (µs)** setting.

2. **Inheriting Rotation from a Grid**:
   - The dropdown list displays all active tile grids defined in the session.
   - The default selected grid index matches the current OV index (e.g. OV 0 defaults to Grid 0, OV 1 defaults to Grid 1, clamped to the number of available grids).
   - Click the **Get rotation angle** button to immediately copy the selected grid's rotation angle into the **Rotation angle (°)** spinbox.

3. **Saving Settings**:
   - Click **Save settings for OV NNN**.
   - If the rotation angle changed, the viewport clears the previous unrotated image preview and re-draws the overview boundary at the new rotation angle.

---

## Hardware and Scan Dynamics

- **SmartSEM Polarity Conversion**:
  - SBEMimage uses standard mathematical coordinate conventions (counter-clockwise positive), whereas SmartSEM scan rotation is clockwise positive.
  - SBEMimage automatically transforms the angle using $\theta_{\text{sem}} = (360 - \theta_{\text{sbem}}) \bmod 360$ during overview acquisition.
  - When rotation is `0.0°`, no hardware scan-rotation commands are sent.

- **Fail-Safe Restoration Guard**:
  - Immediately following frame acquisition, SBEMimage automatically resets the SEM scan rotation to `0.0°` inside a protected `finally` block.
  - When resetting rotation to `0.0°`, SmartSEM's digital scan rotation parameter (`DP_SCAN_ROT`) is explicitly cleared last, ensuring the scan rotation tick mark is turned completely OFF.
  - This ensures that if the next overview or tile grid has a 0° rotation (or if acquisition is aborted or interrupted by an error), subsequent acquisitions and manual imaging operations are never left with residual scan rotation.

---

## Viewport Display and Debris Detection

- **Viewport Display**:
  - Overview pixmaps and their boundary frames are rotated directly around the overview's center coordinate.
  - Overview labels rotate along with the top-left corner of the overview rectangle.
  - Viewport mouse clicks and selection coordinates are inverse-rotated around the overview center, allowing seamless click-selection of rotated overviews.

- **Debris Detection Area**:
  - The debris detection area is computed by projecting active tile corners directly into the overview image's coordinate frame.
  - When the overview has a non-zero rotation angle, the debris detection rectangle is rotated accordingly in the Viewport, tightly and accurately enclosing the active tiles without cutting off tile corners.
  - It remains the user's responsibility to position and size the overview image such that the target debris detection area lies fully within the overview field of view.
