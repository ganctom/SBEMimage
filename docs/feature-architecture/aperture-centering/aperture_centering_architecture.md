# Aperture Centering Feature Architecture

## 1. Overview & Problem Statement

In Serial Block-Face Scanning Electron Microscopy (SBEM), high-throughput automated acquisitions collect thousands of high-resolution image tiles over weeks or months. Achieving diffraction-limited, isotropic resolution across large fields of view depends directly on objective aperture centering.

When the objective aperture is misaligned with the optical axis:
1. **Coma and Asymmetric Aberrations**: The electron beam enters objective lens focus at an angle, creating directional blurring that degrades tile corners and edges.
2. **Tilted Focal Plane**: The plane of optimal focus becomes tilted relative to the cut specimen block-face, preventing simultaneous sharp focus across the entire tile.
3. **Manual Overhead**: Operators traditionally rely on tedious manual wobble/centering routines in SmartSEM, which are subjective, lack diagnostic logging, and risk operator error during multi-day runs.

The **Aperture Centering** module provides an automated, objective, mathematically grounded calibration system that sweeps electromagnetic deflector coordinates, evaluates optical metrics, models the sharpness surface, and presents clear diagnostic heatmaps.

---

## 2. Mathematical Architecture

### 2.1 Gradient Magnitude (Tenengrad) Operator
For an image $I(x, y)$, high-frequency feature crispness is quantified using Sobel gradient filters in horizontal and vertical directions:

$$G_x = \text{Sobel}(I, \text{CV\_32F}, 1, 0, k=3), \quad G_y = \text{Sobel}(I, \text{CV\_32F}, 0, 1, k=3)$$
$$|\nabla I(x, y)| = \sqrt{G_x(x, y)^2 + G_y(x, y)^2}$$

### 2.2 Center Sharpness (Circular ROI)
In the Center Sharpness strategy (`center_sharpness`):
- A circular mask $M$ of radius $R = 0.98 \cdot \min(c_x, c_y)$ is constructed around the image center $(c_x, c_y)$:

$$M(x, y) = \begin{cases} 1 & \text{if } (x - c_x)^2 + (y - c_y)^2 \le R^2 \\ 0 & \text{otherwise} \end{cases}$$

- Center sharpness is defined as the mean gradient magnitude within the mask:

$$S_{\text{center}} = \frac{1}{|M|} \sum_{(x, y) \in M} |\nabla I(x, y)|$$

- This metric is robust, computationally efficient, and directly correlates with optimal objective alignment without relying on unproven polar symmetry assumptions.

### 2.3 Continuous 2D Paraboloid Surface Fitting
Because discrete sampling steps (e.g. 5% grid steps) may straddle the true continuous optimum, sampled discrete points $(x_i, y_i, S_i)$ are modeled as a 2D quadratic paraboloid:

$$z(x, y) = a x^2 + b y^2 + c x y + d x + e y + f$$

Constructing the linear design matrix $A \in \mathbb{R}^{N \times 6}$:

$$A = \begin{pmatrix} x_1^2 & y_1^2 & x_1 y_1 & x_1 & y_1 & 1 \\ \vdots & \vdots & \vdots & \vdots & \vdots & \vdots \\ x_N^2 & y_N^2 & x_N y_N & x_N & y_N & 1 \end{pmatrix}, \quad \mathbf{z} = \begin{pmatrix} S_1 \\ \vdots \\ S_N \end{pmatrix}$$

The coefficients $\mathbf{p} = (a, b, c, d, e, f)^T$ are solved via ordinary least-squares (`np.linalg.lstsq(A, z, rcond=None)`).

The continuous critical point occurs where the gradient vanishes:

$$\nabla z = \begin{pmatrix} 2a x + c y + d \\ c x + 2b y + e \end{pmatrix} = \begin{pmatrix} 0 \\ 0 \end{pmatrix} \implies \begin{pmatrix} 2a & c \\ c & 2b \end{pmatrix} \begin{pmatrix} x^* \\ y^* \end{pmatrix} = \begin{pmatrix} -d \\ -e \end{pmatrix}$$

#### Hessian Curvature Validation
For $(x^*, y^*)$ to be a valid local maximum:
1. The Hessian $H = \begin{pmatrix} 2a & c \\ c & 2b \end{pmatrix}$ must be negative definite:
   $$\det(H) = 4ab - c^2 > 0 \quad \text{and} \quad a < 0$$
2. The peak must fall within a reasonable boundary of the sampled grid:
   $$x_{\min} - 0.5 \Delta x \le x^* \le x_{\max} + 0.5 \Delta x$$
   $$y_{\min} - 0.5 \Delta y \le y^* \le y_{\max} + 0.5 \Delta y$$

If these criteria are satisfied, $(x^*, y^*)$ is adopted as the continuous optimal aperture center; otherwise, the discrete maximum on the sampled grid is retained as a safe fallback.

---

## 3. Physical Dynamics & Hardware Integration

### 3.1 Snake-Like Traversal Grid
To prevent magnetic hysteresis in the electromagnetic deflector coils, grid points $(x_i, y_j)$ follow an alternating snake-like path starting at the top-left:
- Row $j$ even ($j = 0, 2, \dots$): $x$ sweeps from $-k \cdot \text{step} \to +k \cdot \text{step}$.
- Row $j$ odd ($j = 1, 3, \dots$): $x$ sweeps from $+k \cdot \text{step} \to -k \cdot \text{step}$.

### 3.2 Hardware Limits & Coordinate Clamping
- Aperture deflector range is governed by instrument limits queried from SmartSEM (`sem_api.GetLimits('AP_APERTURE_ALIGN_X', ...)` / `GetLimits('AP_APERTURE_ALIGN_Y', ...)`), falling back to `aperture_align_limits` in `system.cfg` (default: $[-100.0\%, 100.0\%, -100.0\%, 100.0\%]$).
- All nudge increments and sweep grid coordinates are clamped strictly within $[min\_x, max\_x, min\_y, max\_y]$.

### 3.3 Diamond Knife Sectioning & Specimen De-Charging
Capturing dozens of high-resolution calibration frames at a single spot on non-conductive plastic blocks induces extreme negative charge.
When `perform_cut` is enabled:
1. Step $i$ frame is acquired.
2. The deflector alignment for step $i+1$ is applied **immediately**.
3. Ultramicrotome stage moves up by `cut_thickness` (e.g. 35 nm), updating `last_known_z` and synchronizing the acquisition system.
4. The physical knife stroke executes (`do_full_cut`), waiting for `full_cut_duration` (typically 15 s).
5. During the knife cut, electromagnetic deflector transients completely decay, allowing immediate capture of step $i+1$ upon knife retraction.

### 3.4 Translation Registration & Shared FOV Crop
Large aperture deflections produce small lateral beam shifts.
1. Subpixel phase cross-correlation (`utils.compute_shifts_cv2`) registers consecutive frames.
2. Images are translated (`utils.shift_collection`) and cropped to their shared bounding intersection (`utils.crop_image_collection`) automatically before sharpness evaluation.

### 3.5 Beam-Off Safety & API Error Recovery
- **Beam Off Guard**: At the start of the sweep and before each step (prior to frame capture and knife cuts), the system verifies `not sem.is_eht_off()` (or `sem.is_eht_on()`). If the beam is detected as off, the sweep immediately aborts, reinstates initial aperture coordinates, and raises a descriptive `RuntimeError`.
- **API Timeout / Communication Failure**: Any exception during `set_aperture_align_xy` or `acquire_frame` triggers immediate recovery of the initial aperture alignment on the microscope and alerts the operator via a modal warning.

---

## 4. Concurrency, Memory & Storage Architecture

### 4.1 Asynchronous Image Evaluation & Safe Plotting
- While physical cutting is disabled, frame scanning is sequential, with background metric computation executed on a `ThreadPoolExecutor`.
- Plotting runs headlessly via `matplotlib.use('Agg')` with explicit cleanup (`plt.close(fig)`), rendering Center Sharpness and Mean Sharpness heatmaps with inverted SmartSEM Y-axes.
- All standard output `print()` calls are omitted in production to avoid cluttering terminal logs, persisting structured logs to `alignment_log.txt`.

### 4.2 Directory & File Conventions
All calibration artifacts are saved under:
`meta/calibrations/aperture_centering/<YYYY-MM-DD_HHMMSS>/`

Structure:
```
meta/calibrations/aperture_centering/2026-09-21_141000/
├── alignment_log.txt              # Full chronological text log
├── sharpness_data.json            # Machine-readable metric database
├── aperture_centering_heatmap.png # 2-panel diagnostic visualization (Center & Mean Sharpness)
├── frame_001_X-10.00_Y-10.00.tif  # Raw calibration frames
├── frame_002_X-5.00_Y-10.00.tif
└── registered/                    # Registered & cropped series
    ├── frame_001_X-10.00_Y-10.00.tif
    └── ...
```
