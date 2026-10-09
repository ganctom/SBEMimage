# ov-rotation Feature Architecture

## 1. Overview & Problem Statement

### Legacy Limitation
`Overview` inherits `rotation` from `Grid` and the config already stores
`ov_rotation`. However, four downstream consumers silently ignore it:

| Consumer | Current behaviour | Target |
|---|---|---|
| `Overview.__init__()` | hardcodes `rotation=0` in `super().__init__()` | pass through the loaded rotation |
| `Overview.bounding_box()` | axis-aligned box of unrotated OV | keeps unrotated box as origin reference for debris detection |
| `acquire_overview()` | no `set_scan_rotation` call | apply & conditionally reset scan rotation |
| `_vp_place_overview()` | axis-aligned draw | rotate painter around OV centre |
| `OVSettingsDlg` | no rotation widget | `doubleSpinBox_rotation` + inherit-from-grid |

---

## 2. Mathematical Architecture

### 2.1 Coordinate Conventions

SBEMimage uses three coordinate systems:

| System | Description | Unit |
|---|---|---|
| **s** (stage) | SEM stage X/Y | µm |
| **d** (display) | Converted from stage for viewport math | µm |
| **v** (viewport) | Pixel position within the Qt viewport widget | px |

Rotation angles are stored in degrees. SBEMimage's internal rotation convention
is **counter-clockwise positive** (following standard mathematics). SmartSEM
uses **clockwise positive** for its scan rotation parameter. The conversion for
non-MagC mode is:

$$\theta_\text{sem} = (360 - \theta_\text{sbem}) \bmod 360$$

For $\theta_\text{sbem} = 0$, $\theta_\text{sem} = 0$, so no scan rotation is
applied (entry guard `if theta_sem > 0`).

### 2.2 Overview Coordinate Frame & Debris Detection Area Projection

When an overview has a non-zero rotation angle $\theta$, the Viewport rotates the `QPainter` by $\theta$ around the OV centre before drawing the OV image and the debris detection area rectangle.

To enclose active tiles without missing any parts regardless of OV rotation angle, each active tile's corner coordinates $(x, y)$ in display coordinates are projected into the OV image's internal coordinate frame $(u, v)$ where $(0, 0)$ is the OV top-left:
$$u = ((x - c_x)\cos\theta + (y - c_y)\sin\theta) + W/2$$
$$v = (-(x - c_x)\sin\theta + (y - c_y)\cos\theta) + H/2$$

The bounding box $[u_\text{min}, u_\text{max}] \times [v_\text{min}, v_\text{max}]$ across all active tile corners overlapping the OV field of view is scaled to pixel coordinates and expanded by `margin`. When drawn in the Viewport via the rotated QPainter, the rectangle is oriented at $\theta$ and tightly encloses the active tiles.

`bounding_box()` returns the unrotated axis-aligned bounds ($c_x \pm W/2, c_y \pm H/2$) as the base display reference. It is the user's responsibility to position and size the overview field of view so that target detection regions fall within it.

### 2.3 Viewport Rendering

The OV centre in viewport coordinates:

$$c_x^v = v_x + \frac{W_p \cdot r}{2}, \quad c_y^v = v_y + \frac{H_p \cdot r}{2}$$

where $W_p, H_p$ are pixel dimensions of the OV and $r$ is the viewport
resize ratio.

The painter transform applied before drawing:

$$T = \text{translate}(c_x^v, c_y^v) \cdot \text{rotate}(\theta_\text{sbem}) \cdot \text{translate}(-c_x^v, -c_y^v)$$

Qt's `QPainter.rotate(theta)` uses **clockwise** convention for positive
angles. Since the grid rendering already uses this same Qt API with its
`rotation` field, the visual direction is consistent between grids and OVs.

### 2.4 Acquisition Guard & SmartSEM Hardware Dynamics

```
acquire_overview(ov_index):
    ...
    theta_sbem = ovm[ov_index].rotation
    if not magc_mode:
        theta_sem = (360 - theta_sbem) % 360
    else:
        theta_sem = theta_sbem
    if theta_sem > 0:
        sem.set_scan_rotation(theta_sem)
    try:
        sem.acquire_frame(ov_save_path)
    finally:
        if theta_sem > 0:
            sem.set_scan_rotation(0)     # protect next 0°-rotation OV / grid
    ...
```

SmartSEM hardware sequence:
- **Enable (>0°)**: Set `DP_SCAN_ROT = 1` first (coil switch ON), then `AP_SCANROTATION = angle`.
- **Disable (==0°)**: Set `DP_SCAN_ROT = 0` only without writing `AP_SCANROTATION = 0` (which would re-assert the tick mark in SmartSEM).

---

## 3. GUI Layout

### 3.1 Dialog dimensions: 222 × 560 px

### 3.2 Layout

```
y=  10  comboBox_OVSelector
y=  50  label "OV size (px):"          comboBox_frameSize
y=  80  label "OV size (µm²):"         label_frameSize
y= 110  label "Magnification:"          spinBox_magnification
y= 140  label "Pixel size (nm):"        doubleSpinBox_pixelSize (read-only)
y= 170  label "Dwell time (µs):"        comboBox_dwellTime
── new rotation block ─────────────────────────────────────
y= 200  label "Rotation angle (°):"    doubleSpinBox_rotation  [step=1.0, dec=1, 0–360]
y= 230  comboBox_inheritGrid [10,230,68,22]   pushButton_inheritRotation [83,230,128,24] ("Get rotation angle")
── (shifted down ~60 px from original) ────────────────────
y= 260  label "OV acquisition interval:" spinBox_acqInterval
y= 290  label "Interval offset (default: 0):" spinBox_acqIntervalOffset
y= 320  explanatory labels (2 rows)
y= 370  radioButton_active  radioButton_inactive
y= 400  pushButton_clearViewportImage
y= 430  separator line
y= 450  pushButton_save
y= 480  pushButton_addOV   pushButton_deleteOV
```

### 3.3 Inherit-from-Grid Logic

`comboBox_inheritGrid` is populated with the labels of all grids (`gm.number_grids`
items, e.g. `["Grid 0", "Grid 1", …]`). Default selection:

```python
default_idx = min(self.current_ov, self.gm.number_grids - 1)
self.comboBox_inheritGrid.setCurrentIndex(default_idx)
```

On `pushButton_inheritRotation` clicked:

```python
grid_idx = self.comboBox_inheritGrid.currentIndex()
self.doubleSpinBox_rotation.setValue(self.gm[grid_idx].rotation)
```

The combo is updated (default re-selected) each time a different OV is selected
via `change_ov()`.

---

## 4. Hardware & Concurrency Pipeline

- Scan rotation is a synchronous SEM API call (no threading concern).
- The acquisition loop for overviews is single-threaded within the Acquisition
  worker thread.
- The post-acquisition `set_scan_rotation(0)` guard ensures subsequent
  operations (next OV, grid acquisition, manual imaging) are not affected by
  a leftover rotation.

---

## 5. Storage & Output Artifacts

- **Config key**: `[overviews] ov_rotation = [θ₀, θ₁, …]` — already defined.
  No schema change needed.
- **Acquired images**: rotation is baked into the pixel data by SmartSEM;
  no post-processing rotation of the saved `.bmp` is required or performed.
- **Viewport display**: rotation is applied at paint-time on the loaded QPixmap;
  the on-disk workspace `.bmp` file is not modified.
