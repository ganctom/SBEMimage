# Stage Calibration Guide

## Overview
The **Stage Calibration** tool computes coordinate transformation parameters (scale factors and rotation angles) between the physical microscope stage coordinates and the SEM image scanning axes.

Calibration options are available via **Calibration** → **Stage Calibration**.

---

## Calibration Methods

### 1. Multi-Point Grid Calibration
The multi-point strategy acquires an $N \times N$ grid of overlapping images around the anchor position, introducing randomized jitter to compute pairwise translation vectors with subpixel phase correlation.

#### Parameters:
- **Grid dimension ($N$)**: The dimension of the image grid (e.g., $3 \times 3$ or $5 \times 5$).
- **Frame size**: SEM frame size used for calibration images.
- **Number of runs**: Number of independent grid sweeps to perform.
- **Calibration radius ($\mu\text{m}$)**: Maximum radial distance around the anchor stage position within which subsequent runs will randomly position their starting centers. This was previously referred to as *Wander radius*.
- **Package**: Software library used for subpixel phase cross-correlation (`cv2`, `imreg_dft`, or `skimage`).

#### Safeguards & Hardware Protection:
- **EHT Monitoring**: Verifies high tension is active before and during the calibration sweep, aborting if the beam drops.
- **Stage Limits**: Automatically verifies all target grid positions are within physical stage limits before commanding moves.
- **Motor Error Detection**: Inspects stage and microtome error registers after every move, terminating gracefully on hardware failures.
- **Real-time Viewport Tracking**: Continuously updates stage position markers and redraws the Viewport throughout the sweep.

---

### 2. Traditional 3-Image Calibration
Acquires a reference image at the origin, one after an X shift, and one after a Y shift. Parameters are computed directly from the 2 shift vectors.
