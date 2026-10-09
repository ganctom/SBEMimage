# Domain Knowledge: ov-rotation

## 1. Physical / Optical Dynamics

### Scan Rotation
- **SmartSEM scan rotation** rotates the electron-beam raster pattern around
  the frame centre. It is a purely electronic operation (no mechanical stage
  motion) with negligible settling time (sub-millisecond at typical angles).
- Angles are in degrees, 0–360. Setting 0° means the raster is aligned to the
  SEM stage X-axis (horizontal scan).
- SBEMimage uses the convention `theta_sem = (360 - theta_sbem) % 360` for
  non-MagC mode. This sign flip is required because SBEMimage's internal
  coordinate system has the Y-axis inverted relative to SmartSEM's displayed
  coordinate frame. **Evidence**: `acquisition.py:2164–2165`.

### OV as a 1×1 Grid
- `Overview` inherits from `Grid`. A 1×1 grid has exactly one tile (tile 0).
- The `rotation` property already exists on `Grid` and is stored/loaded via
  `ov_rotation` in the session config (`default.ini` section `[overviews]`).
- **Bug**: `Overview.__init__` hardcodes `rotation=0` in the `super().__init__()`
  call, discarding the `ov_rotation` config value entirely.

## 2. Hardware Quirks & Timings

### Scan Rotation Reset & SmartSEM Parameter Ordering Quirks
After acquiring an OV with θ>0°, `set_scan_rotation(0)` must be called before
moving on. The risk scenario:

```
OV[0]  θ=45° → set_scan_rotation(45)  →  acquire  →  set_scan_rotation(0)  ✓
OV[1]  θ=0°  → (guard: theta=0, skip set_scan_rotation)  →  acquire at 0°  ✓

Without reset after OV[0]:
OV[0]  θ=45° → set_scan_rotation(45)  →  acquire  →  [no reset]
OV[1]  θ=0°  → (guard: theta=0, skip set_scan_rotation)  →  acquire at 45° ✗
```

**SmartSEM API Parameter Order Quirk**:
In `sem_control_zeiss.py`, `set_scan_rotation` interacts with two parameters:
1. `DP_SCAN_ROT`: digital enable flag (1 = ON / ticked, 0 = OFF / unticked).
2. `AP_SCANROTATION`: analog rotation angle parameter (in degrees).

Hardware/API dynamics:
- **Enabling (`angle > 0`)**: `DP_SCAN_ROT = 1` **must** be set before `AP_SCANROTATION = angle`.
  If `DP_SCAN_ROT` is 0 (disabled), SmartSEM rejects or ignores calls to `AP_SCANROTATION`.
- **Disabling (`angle == 0`)**: `DP_SCAN_ROT = 0` is set to turn off scan rotation.
  `AP_SCANROTATION` **must not** be called when disabling; writing to `AP_SCANROTATION` triggers
  SmartSEM's internal parameter-change handler which automatically re-checks `DP_SCAN_ROT = 1`
  and displays 360°.

### Viewport Refresh OV (`acq_func.acquire_ov`)
When the user clicks "Refresh OV(s)" in the Viewport, `acq_func.acquire_ov()` executes.
It must apply the OV's configured rotation angle (with SmartSEM polarity `(360 - θ) % 360`)
and reset to 0 in a protected `finally` block, mirroring `acquire_overview()` in `acquisition.py`.

## 3. Mathematical & Algorithmic Principles

### Overview Debris Detection Area Projection

When an OV has a non-zero rotation angle $\theta$, the OV image coordinate axes
are rotated by $\theta$ relative to the global display coordinate system:
- In the OV image frame, $(0, 0)$ is the top-left pixel, and axes $\vec{u}$ and $\vec{v}$
  run along the rotated width and height.
- In the Viewport, `_vp_place_overview()` rotates the QPainter by $\theta$ around
  the OV centre before drawing the OV image and the debris detection rectangle.

To accurately enclose active tiles without missing any parts, each active tile's
corner coordinates $(x, y)$ in display coordinates are projected into the OV image
coordinate frame:
$$u = ((x - c_x)\cos\theta + (y - c_y)\sin\theta) + W/2$$
$$v = (-(x - c_x)\sin\theta + (y - c_y)\cos\theta) + H/2$$

The bounding box $[u_\text{min}, u_\text{max}] \times [v_\text{min}, v_\text{max}]$
across all active tile corners that overlap the OV footprint $[0, W] \times [0, H]$
is then scaled to OV pixel coordinates and expanded by `margin`.
When drawn in the Viewport via the rotated QPainter, the rectangle is oriented at $\theta$
and tightly and accurately encloses the active tiles.

### Viewport Rotation Transform
The OV image (a QPixmap) is placed at viewport coordinates `(vx, vy)` with
`width_p × height_p` pixels. The centre of the OV in viewport coordinates is:

```
cx_v = vx + (width_p * resize_ratio) / 2
cy_v = vy + (height_p * resize_ratio) / 2
```

To rotate by θ (degrees, clockwise in Qt painter coordinates):
```
QPainter.save()
QPainter.translate(cx_v, cy_v)
QPainter.rotate(theta)          # Qt positive = clockwise
QPainter.translate(-cx_v, -cy_v)
# draw pixmap and bounding rect as before
QPainter.restore()
```

Qt's `QPainter.rotate()` is **clockwise** for positive angles, which matches
the existing grid rotation direction used in `viewport.py:1768`.

### Config / Storage
- `ov_rotation` key in `[overviews]` section stores a JSON list of floats,
  one per OV (e.g. `[0, 45.0, 90.0]`). Already written by
  `OverviewManager.save_to_cfg()`.
- Default is `[0]` for backward compatibility.

### QPixmap Caching vs Fresh Disk Image Reload
- When "Refresh OV(s)" is clicked, the newly acquired frame is saved to `workspace/OV<index>.bmp`.
- Direct usage of `QPixmap(file_path)` in Qt/PyQt checks `QPixmapCache`. If a file with that path was already loaded previously, Qt returns the stale cached image from RAM without reading the newly overwritten file from disk!
- To guarantee that Viewport always displays the freshly acquired image at the new rotation angle, `QPixmapCache.clear()` and `QPixmap.fromImage(QImage(file_path))` are used in `Overview.vp_file_path.setter` and `StubOverview.vp_file_path.setter`.

