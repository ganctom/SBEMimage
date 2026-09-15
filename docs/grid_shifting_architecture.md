# Grid Shifting Feature Architecture

## Overview
The Grid Shifting feature is designed to reduce localized accumulated electron dose and avoid quadruple beam exposure at tile intersections during Serial Block-Face SEM (SBEM) acquisition. It achieves this by applying a deterministic, iterating spatial shift to the entire grid layout on successive slices (usually looping every 3 or 5 slices). 

This document details the mathematical coordinate transformations, hardware interactions, and visualization logic required to implement this feature robustly while integrating with Autofocus and the Viewport.

## Coordinate Systems and Mathematical Transformations

To shift the grid correctly, the software translates a desired shift in grid pixels into a physical stage movement.

1. **Grid Pixel Coordinates**: The grid defines shifts intrinsically as `shift_px_x` and `shift_px_y`.
2. **SEM/d-frame Coordinates (Microns)**: The pixel shift is scaled by the grid's `pixel_size`. 
3. **Grid Rotation (`theta`)**: SBEMimage supports rotating the grid layout by `theta` degrees. The stage displacement vector must be rotated by `theta` to align the shift with the grid's internal X/Y axes:
   ```python
   delta_dx = local_dx * cos(theta) - local_dy * sin(theta)
   delta_dy = local_dx * sin(theta) + local_dy * cos(theta)
   ```
4. **Stage/s-frame Coordinates**: The SEM displacement `(delta_dx, delta_dy)` is passed through the stage calibration matrix `convert_d_to_s` to generate the physical hardware commands `shift_stage_dx` and `shift_stage_dy`.

During `acquire_tile`, this shift vector is applied as a **rigid, global translation** to every tile's target stage coordinate. 

## Working Distance (WD) Compensation

Because the sample surface (the block-face) is often tilted relative to the SEM's focal plane, moving the stage laterally changes the required Working Distance to maintain focus.

When **Autofocus Tracking Mode 3** (Focus Gradient) is active, the feature automatically computes the necessary $\Delta$WD (`shift_wd_delta`) induced by the grid shift.
It calculates this using the dot product of the physical stage shift and the fitted focal plane gradient (`params_wd`):
```python
self.shift_wd_delta = self.shift_stage_dx * params_wd[0] + self.shift_stage_dy * params_wd[1]
```
This guarantees that as the entire grid shifts up or down the tilted block-face, the working distance precisely tracks the sample plane.

### The Stigmation Deflection Challenge
Initially, the grid-shift feature attempted to also apply a $\Delta$Stigmation (`shift_stig_x/y_delta`) based on the gradient plane. However, this caused severe issues: updating the hardware stigmators dynamically physically deflected the electron beam (stigmator wobble). Because stigmator wobble is non-linear, this beam deflection varied per-tile across the grid, destroying the rigid stage translation and causing tiles to drift optically.
**Resolution**: Grid shifting is now explicitly isolated from stigmation. `set_wd` and `set_stig_xy` were decoupled, ensuring that grid-shift only alters Working Distance, leaving stigmation strictly to the Autofocus routines.

## Viewport Slice-by-Slice Compensation

When a user browses the acquired Z-stack in the `SliceView`, the physical grid shift must be visually cancelled out so the tissue appears stationary.

**The Rotation Trap**: Since the stage shifted by `theta`, it seems logical to rotate the Viewport compensation vector by `theta`. However, this is mathematically incorrect because the SEM *actively rotates its scanning beam by `theta`* during acquisition to align with the grid.
Because the acquired `.tif` image is already rotated, the tissue shift inside the image is purely horizontal/vertical relative to the image borders. 

**Resolution**: The `SliceView` compensation simply applies the unrotated pixel shift (`shift_px_x`, `shift_px_y`) directly to the image canvas. This flawlessly cancels out the physical stage movement, keeping the tissue locked in place while scrolling through slices.
