# Stage Calibration Feature Architecture

## 1. Overview & Problem Statement

Stage calibration establishes the mathematical transformation between the SEM imaging coordinate system (d-frame, in micrometres or pixels) and the physical microscope stage coordinate system (s-frame, in micrometres). Accurate calibration is paramount in Serial Block-Face SEM (SBEM) to ensure that adjacent tiles in large multi-tile mosaics align with deterministic, sub-micron precision.

### The Legacy Limitation
The legacy calibration routine acquired only 3 images arranged in a small L-shape (centre, +X shift, +Y shift) and calculated scale factors and rotation angles from isolated displacement vectors. While mechanically simple, this approach suffered from significant drawbacks:
- **Local Distortion Bias**: Optical and scan distortions near frame borders systematically distorted the calculated shifts.
- **Extrapolation Errors**: Errors in the two local vectors amplified dramatically when extrapolated across large acquisition areas (centimetres wide). Real discrepancies between tiles were frequently an order of magnitude larger than the physical repeatability of the stage motors.
- **Axis Inversion Ambiguity**: Stage motor polarity differences across microscope models could lead to unhandled negative scale factors and flipped rotation angles.

---

## 2. Mathematical Architecture

The redesigned stage calibration replaces isolated vectors with an overdetermined, multi-point grid evaluated via **Ordinary Least Squares (OLS)**.

### 2.1 Coordinate Transformation Model
The physical stage displacement vector $\begin{pmatrix} \Delta s_x \\ \Delta s_y \end{pmatrix}$ corresponding to an observed SEM displacement vector $\begin{pmatrix} \Delta d_x \\ \Delta d_y \end{pmatrix}$ is governed by a 2D affine linear map:

$$\begin{pmatrix} \Delta s_x \\ \Delta s_y \end{pmatrix} = \begin{pmatrix} a & b \\ c & d \end{pmatrix} \begin{pmatrix} \Delta d_x \\ \Delta d_y \end{pmatrix}$$

where:
- $\Delta d_x = \text{shift}_{px, x} \times \frac{\text{pixel\_size}}{1000}$ ($\mu\text{m}$)
- $\Delta d_y = \text{shift}_{px, y} \times \frac{\text{pixel\_size}}{1000}$ ($\mu\text{m}$)
- $\Delta s_x, \Delta s_y$ are the actual physical stage moves recorded during acquisition ($\mu\text{m}$).

### 2.2 Overdetermined Linear System
For an $N \times N$ grid, adjacent horizontal pairs ($N(N - 1)$) and vertical pairs ($N(N - 1)$) yield $K = 2N(N - 1)$ pairwise measurement equations:

$$A = \begin{pmatrix} \Delta d_{x, 1} & \Delta d_{y, 1} \\ \Delta d_{x, 2} & \Delta d_{y, 2} \\ \vdots & \vdots \\ \Delta d_{x, K} & \Delta d_{y, K} \end{pmatrix}, \quad \mathbf{b}_x = \begin{pmatrix} \Delta s_{x, 1} \\ \vdots \\ \Delta s_{x, K} \end{pmatrix}, \quad \mathbf{b}_y = \begin{pmatrix} \Delta s_{y, 1} \\ \vdots \\ \Delta s_{y, K} \end{pmatrix}$$

The coefficient vectors $\begin{pmatrix} a \\ b \end{pmatrix}$ and $\begin{pmatrix} c \\ d \end{pmatrix}$ are solved independently via `np.linalg.lstsq(A, b, rcond=None)`.

### 2.3 Parameter Extraction & Axis Inversion Handling
From coefficients $a, b, c, d$, the physical rotation angles $\theta_x, \theta_y$ and scale factors $s_x, s_y$ are extracted:

$$\theta_y = \text{atan2}(-b, a), \quad \theta_x = \text{atan2}(c, d)$$
$$\Delta\theta = \theta_x - \theta_y$$

#### Motor Inversion Reconciliation
On microscopes where stage motor axes are physically inverted relative to the raster scan convention, the unconstrained affine fit yields $\cos(\Delta\theta) < 0$ (implying negative scale factors). To maintain downstream compatibility with positive scale factor requirements ($s_x, s_y > 0$) while preserving mathematical matrix equivalence:

$$\text{if } \cos(\Delta\theta) < 0: \quad \theta_x \leftarrow \theta_x - \pi, \quad \theta_y \leftarrow \theta_y - \pi, \quad \Delta\theta \leftarrow \theta_x - \theta_y$$

The scale factors are then extracted as true positive magnitudes:

$$s_x = |\cos(\Delta\theta)| \cdot \sqrt{a^2 + b^2}, \quad s_y = |\cos(\Delta\theta)| \cdot \sqrt{c^2 + d^2}$$

#### Safety Clamping
Scale factors are safety-clamped to $[0.1, 10.0]$ to guard against degenerate fits caused by completely featureless calibration images:
```python
scale_x = max(0.1, min(10.0, scale_x))
scale_y = max(0.1, min(10.0, scale_y))
```

---

## 3. Physical Dynamics & Artifact Mitigation

### 3.1 SEM Lens Distortion Filter (Central 60% Crop)
Electron optics exhibit barrel/pincushion distortion and scan non-linearities that scale exponentially toward image edges.
- **Mitigation**: All calibration images are symmetrically cropped prior to registration: only the central 60% of the image ($[0.2H : 0.8H, 0.2W : 0.8W]$) is retained.
- **Overlap Constraint**: Calibration stage moves are strictly constrained to $\text{shift} < 0.5 \times \text{FOV}$ (with automatic suggestion at $0.3 \times \text{FOV}$) to guarantee overlap within the central 60% crop region.

### 3.2 Mechanical Settling Delay (0.6s)
Microscope stage motors (particularly ultramicrotome sub-stages) experience decaying mechanical oscillation and motor drift immediately upon completing a move.
- **Mitigation**: A mandatory `sleep(0.6)` delay is executed after every stage move before initiating frame grab, eliminating motion blur and trailing shift artifacts.

### 3.3 Micro-Jitter Anti-Aliasing
Periodic lead-screw runout or sub-stage pitch errors can systematically bias regular grid calibrations.
- **Mitigation**: A random $\pm 10\%$ jitter is injected into each grid coordinate:
  $$s_x = x_0 + (i - \text{offset}) \cdot \text{shift} + \text{jitter}_x$$
  Because the true hardware coordinates $(s_x, s_y)$ are recorded and fed to the least-squares solver, periodic errors cancel out without degrading regression accuracy.

---

## 4. High-Performance Computation Pipeline

### 4.1 Adaptive Downsampling
For high-resolution calibration frames ($> 1024$ px), images are adaptively downsampled using area interpolation (`cv2.INTER_AREA`):
$$\text{scale} = \frac{1024}{\max(H, W)}$$
Phase cross-correlation is evaluated on the downsampled image with subpixel peak interpolation and re-scaled back to full resolution, reducing 2D FFT computation time by $>10\times$.

### 4.2 Hardware-Accelerated Phase Correlation with Fallback
1. **Primary**: Native C++ AVX2 `cv2.phaseCorrelate(i2, i1, hann_window)`. Computes subpixel shift in $< 5\text{ ms}$.
2. **Response Gate**: If peak response $< 0.05$ (e.g. low signal-to-noise ratio), falls back automatically to feature-based ORB RANSAC matching (`utils.align_images_cv2`).

### 4.3 Parallel Multithreading
Pairwise image registration tasks ($2N(N-1)$ per run) are embarrassingly parallel. They are executed concurrently across all available CPU cores using `concurrent.futures.ThreadPoolExecutor(max_workers=min(os.cpu_count() or 4, 8))`.

---

## 5. Statistical Multi-Run & Outlier Rejection

To ensure stability against localized resin defects, dust, or knife marks:
1. **Random Wander**: The user can configure $M$ runs. Runs $2 \dots M$ randomly wander within a user-specified `wander_radius` around the anchor coordinate, verifying hardware safety via `stage.pos_within_limits([tx, ty])`.
2. **RMSE Quality Assessment**: Each run computes root-mean-square error (RMSE in $\mu\text{m}$):
   $$\text{RMSE} = \frac{\text{RMSE}_x + \text{RMSE}_y}{2}$$
3. **Outlier Discard**: Any run with $\text{RMSE} > 3 \times \text{median}(\text{RMSE})$ is discarded.
4. **Final Aggregation**: The final parameters $(\text{scale}_x, \text{scale}_y, \theta_x, \theta_y)$ are calculated via the **Median** of the accepted runs.

---

## 6. Storage & UI Architecture

### 6.1 Ephemeral Storage
Calibration images are stored in memory/temporary disk via `tempfile.TemporaryDirectory()`. Files are created, loaded into RAM, and automatically destroyed when exiting context, preventing workspace bloat.

### 6.2 Non-Destructive UI Layout
In `gui/stage_calibration_dlg.ui` and `src/main_controls_dlg_windows.py`:
- The legacy "Calculate calibration parameters" section maintains its original visual hierarchy, coordinate inputs, and direct calculation triggers.
- The new multi-point grid controls (**Grid size**, **Frame size**, **Number of runs**, **Wander radius**) are placed in a distinct column to the right, maintaining backward compatibility for legacy workflows while exposing advanced multi-point calibration.
