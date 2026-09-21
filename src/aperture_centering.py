# -*- coding: utf-8 -*-

# ==============================================================================
#   This source file is part of SBEMimage (github.com/SBEMimage)
#   (c) 2018-2026 Friedrich Miescher Institute for Biomedical Research, Basel,
#   and the SBEMimage developers.
#   This software is licensed under the terms of the MIT License.
#   See LICENSE.txt in the project root folder.
# ==============================================================================

"""This module provides automated and interactive aperture centering for ZEISS SEMs.
It sweeps an aperture align grid, acquires frames, evaluates off-axis optical
field curvature, and determines the optimal aperture centering setting.

Two evaluation strategies are available:
  - ``'radial_symmetry'``: polar-based radial symmetry score (sensitive to
    off-axis aberrations even when overall sharpness is high).
  - ``'center_sharpness'``: Sobel gradient magnitude averaged inside a centered
    circular ROI (simple, robust when symmetric blurring dominates)."""

import os
import json
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple, Dict, Any, Optional, Callable

import numpy as np
import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import utils


def evaluate_radial_symmetry(
    img: np.ndarray,
    num_rings: int = 10,
    num_sectors: int = 16,
    max_eval_dim: int = 2048
) -> Dict[str, Any]:
    """Evaluate radial symmetry of focus/sharpness across the image using
    polar unwrapping (cv2.warpPolar).

    Returns a dictionary with symmetry score, asymmetry metric, center sharpness,
    and sector sharpness profile.
    """
    if img is None or img.size == 0:
        return {
            'symmetry_score': 0.0,
            'asymmetry_score': 999.0,
            'center_sharpness': 0.0,
            'mean_sharpness': 0.0,
            'sector_sharpness': [],
            'radial_profile': [],
            'angular_std_profile': []
        }

    # Ensure grayscale 2D float32 or uint8
    if len(img.shape) == 3:
        img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        img_gray = img

    # Adaptive downsampling for high-speed evaluation on large frames
    h, w = img_gray.shape[:2]
    max_dim = max(h, w)
    if max_dim > max_eval_dim:
        scale = float(max_eval_dim) / float(max_dim)
        new_w = int(round(w * scale))
        new_h = int(round(h * scale))
        eval_img = cv2.resize(img_gray, (new_w, new_h), interpolation=cv2.INTER_AREA)
    else:
        eval_img = img_gray

    eval_h, eval_w = eval_img.shape[:2]
    cx = eval_w / 2.0
    cy = eval_h / 2.0
    max_radius = float(min(cx, cy))

    # Compute gradient magnitude (Tenengrad / Sobel)
    gx = cv2.Sobel(eval_img, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(eval_img, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = cv2.magnitude(gx, gy)

    # Polar coordinate mapping around the optical center
    # In OpenCV warpPolar, width (cols) is radius, height (rows) is angle
    polar_radius_bins = num_rings * 16
    polar_angle_bins = num_sectors * 16
    polar = cv2.warpPolar(
        grad_mag,
        (polar_radius_bins, polar_angle_bins),
        (cx, cy),
        max_radius,
        cv2.WARP_POLAR_LINEAR
    )

    # Reshape and average into discrete (num_rings, num_sectors) polar bins
    # polar shape is (polar_angle_bins, polar_radius_bins)
    ring_block = polar_radius_bins // num_rings
    sec_block = polar_angle_bins // num_sectors

    sector_sharpness = np.zeros((num_rings, num_sectors), dtype=np.float32)
    for r in range(num_rings):
        r_start = r * ring_block
        r_end = (r + 1) * ring_block
        for s in range(num_sectors):
            s_start = s * sec_block
            s_end = (s + 1) * sec_block
            sector_sharpness[r, s] = np.mean(polar[s_start:s_end, r_start:r_end])

    # Calculate angular coefficient of variation across each radial ring
    ring_std = np.std(sector_sharpness, axis=1)
    ring_mean = np.mean(sector_sharpness, axis=1) + 1e-6
    ring_cv = ring_std / ring_mean

    # Weighted asymmetry: outer rings provide more off-axis aberration signal
    weights = np.linspace(0.5, 1.5, num_rings)
    weighted_asymmetry = float(np.sum(ring_cv * weights) / np.sum(weights))

    # Radial symmetry score: higher means more symmetric (peak closer to center)
    symmetry_score = float(1.0 / (1.0 + weighted_asymmetry))

    # Center sharpness: average inside inner 20%
    inner_radius = int(round(0.2 * max_radius))
    y_min = max(0, int(round(cy - inner_radius)))
    y_max = min(eval_h, int(round(cy + inner_radius)))
    x_min = max(0, int(round(cx - inner_radius)))
    x_max = min(eval_w, int(round(cx + inner_radius)))
    center_sharpness = float(np.mean(grad_mag[y_min:y_max, x_min:x_max]))
    mean_sharpness = float(np.mean(grad_mag))

    return {
        'symmetry_score': symmetry_score,
        'asymmetry_score': weighted_asymmetry,
        'center_sharpness': center_sharpness,
        'mean_sharpness': mean_sharpness,
        'sector_sharpness': sector_sharpness.tolist(),
        'radial_profile': ring_mean.tolist(),
        'angular_std_profile': ring_std.tolist()
    }


def evaluate_center_sharpness(
    img,                    # type: np.ndarray
    roi_radius_fraction=0.98,
    max_eval_dim=2048
):
    # type: (...) -> Dict[str, Any]
    """Compute Sobel gradient magnitude averaged inside a centered circular ROI.

    This is the simpler strategy (similar to AFSS): it maximises overall
    sharpness at the image centre rather than radial symmetry.  It is robust
    when the dominant defect is symmetric blurring over the whole frame.

    Args:
        roi_radius_fraction: fraction of the shorter image dimension used as
            the circular ROI radius (default 0.98 → 98 % of half-width).
        max_eval_dim: downsample the longer edge to this value before
            evaluation for speed.

    Returns a dict compatible with the ``metrics`` key expected by
    ``run_sweep`` (keys: ``center_sharpness``, ``mean_sharpness``,
    ``symmetry_score`` alias so existing code does not break).
    """
    empty = {
        'center_sharpness': 0.0,
        'mean_sharpness': 0.0,
        'symmetry_score': 0.0,   # alias used in generic code paths
        'asymmetry_score': 999.0,
        'sector_sharpness': [],
        'radial_profile': [],
        'angular_std_profile': []
    }
    if img is None or img.size == 0:
        return empty

    if len(img.shape) == 3:
        img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        img_gray = img

    h, w = img_gray.shape[:2]
    max_dim = max(h, w)
    if max_dim > max_eval_dim:
        scale = float(max_eval_dim) / float(max_dim)
        new_w = int(round(w * scale))
        new_h = int(round(h * scale))
        eval_img = cv2.resize(img_gray, (new_w, new_h), interpolation=cv2.INTER_AREA)
    else:
        eval_img = img_gray

    eval_h, eval_w = eval_img.shape[:2]
    cx = eval_w / 2.0
    cy = eval_h / 2.0
    roi_radius = roi_radius_fraction * min(cx, cy)

    # Sobel gradient magnitude (same metric as AFSS / autofocus sharpness)
    gx = cv2.Sobel(eval_img, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(eval_img, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = cv2.magnitude(gx, gy)

    # Circular mask centred on the image
    yy, xx = np.mgrid[0:eval_h, 0:eval_w]
    dist2 = (xx - cx) ** 2 + (yy - cy) ** 2
    mask = dist2 <= (roi_radius ** 2)

    center_sharpness = float(np.mean(grad_mag[mask])) if mask.any() else 0.0
    mean_sharpness = float(np.mean(grad_mag))

    return {
        'center_sharpness': center_sharpness,
        'mean_sharpness': mean_sharpness,
        # Provide symmetry_score alias (= normalized center sharpness) so that
        # generic result-ranking and JSON code can use the same key.
        'symmetry_score': center_sharpness,
        'asymmetry_score': 0.0,
        'sector_sharpness': [],
        'radial_profile': [],
        'angular_std_profile': []
    }


def fit_2d_surface(xs: List[float], ys: List[float], values: List[float]) -> Optional[Tuple[float, float, float]]:
    """Fit a 2D quadratic paraboloid z = a*x^2 + b*y^2 + c*x*y + d*x + e*y + f
    to find the continuous peak/optimum (x*, y*, predicted_val).

    Returns (opt_x, opt_y, opt_val) if a valid maximum is found within the bounding box,
    otherwise None.
    """
    if len(xs) < 6:
        return None
    x_arr = np.array(xs, dtype=np.float64)
    y_arr = np.array(ys, dtype=np.float64)
    z_arr = np.array(values, dtype=np.float64)

    # Design matrix: [x^2, y^2, x*y, x, y, 1]
    A = np.column_stack([
        x_arr ** 2,
        y_arr ** 2,
        x_arr * y_arr,
        x_arr,
        y_arr,
        np.ones_like(x_arr)
    ])
    try:
        coeffs, _, _, _ = np.linalg.lstsq(A, z_arr, rcond=None)
        a, b, c, d, e, f = coeffs

        # Gradient is zero at critical point:
        # [2a  c] [x] = [-d]
        # [ c 2b] [y]   [-e]
        H = np.array([[2.0 * a, c], [c, 2.0 * b]], dtype=np.float64)
        det = np.linalg.det(H)
        # For a maximum, Hessian must be negative definite: 2a < 0, 2b < 0, det > 0
        if det <= 1e-9 or a >= 0:
            return None

        rhs = np.array([-d, -e], dtype=np.float64)
        opt_xy = np.linalg.solve(H, rhs)
        opt_x, opt_y = float(opt_xy[0]), float(opt_xy[1])

        # Ensure the fitted peak is within or reasonably close to the sampled grid boundary
        min_x, max_x = float(np.min(x_arr)), float(np.max(x_arr))
        min_y, max_y = float(np.min(y_arr)), float(np.max(y_arr))
        span_x = max(max_x - min_x, 1.0)
        span_y = max(max_y - min_y, 1.0)

        if not ((min_x - 0.5 * span_x) <= opt_x <= (max_x + 0.5 * span_x) and
                (min_y - 0.5 * span_y) <= opt_y <= (max_y + 0.5 * span_y)):
            return None

        opt_val = float(a * opt_x**2 + b * opt_y**2 + c * opt_x * opt_y + d * opt_x + e * opt_y + f)
        return opt_x, opt_y, opt_val
    except Exception:
        return None


class ApertureCenteringManager:
    """Manages aperture centering sweeps, frame capture, analysis, logging,
    and visualization."""

    def __init__(self, sem, microtome, base_dir: str):
        self.sem = sem
        self.microtome = microtome
        self.base_dir = base_dir
        self.is_running = False
        self.should_abort = False
        self.latest_run_dir = None
        self.latest_results = None

    def nudge(self, delta_x: float, delta_y: float) -> Tuple[float, float]:
        """Manually nudge the current aperture align X and Y by delta values (in %)."""
        cur_x, cur_y = self.sem.get_aperture_align_xy()
        new_x = cur_x + delta_x
        new_y = cur_y + delta_y
        self.sem.set_aperture_align_xy(new_x, new_y)
        return self.sem.get_aperture_align_xy()

    def run_sweep(
        self,
        grid_size: int = 5,
        step_size: float = 5.0,
        frame_size_selector: int = 6,
        pixel_size: float = 15.0,
        dwell_time: float = 0.2,
        center_x: Optional[float] = None,
        center_y: Optional[float] = None,
        perform_cut: bool = False,
        cut_thickness: float = 35.0,
        cut_duration: Optional[float] = None,
        auto_apply: bool = False,
        eval_strategy: str = 'center_sharpness',
        register_images: bool = False,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        stage_z_callback: Optional[Callable[[float], None]] = None
    ) -> Dict[str, Any]:
        """Execute a grid sweep around the given center (or current SEM center).

        Args:
            eval_strategy: ``'radial_symmetry'`` (default) or
                ``'center_sharpness'``.  The latter evaluates Sobel gradient
                magnitude inside a centered circular ROI – identical in spirit
                to the AFSS autofocus metric, and robust when the dominant
                defect is symmetric blurring across the whole frame.
            register_images: If True, computes translation shifts between
                consecutive frames via phase cross-correlation, shifts them
                into translational alignment, and crops the registered series
                to their shared field of view prior to metric calculation.

        Saves all artifacts in meta/calibrations/aperture_centering/<timestamp>/.
        """
        self.is_running = True
        self.should_abort = False

        if center_x is None or center_y is None:
            initial_x, initial_y = self.sem.get_aperture_align_xy()
        else:
            initial_x, initial_y = float(center_x), float(center_y)

        # Create timestamped run directory
        timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        run_dir = os.path.join(
            self.base_dir, 'meta', 'calibrations', 'aperture_centering', timestamp
        )
        os.makedirs(run_dir, exist_ok=True)
        self.latest_run_dir = run_dir

        log_path = os.path.join(run_dir, 'alignment_log.txt')

        def log(msg: str):
            print(msg)
            with open(log_path, 'a') as f:
                f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")

        log("=" * 60)
        log("SBEMimage Aperture Centering Calibration")
        log(f"Timestamp: {timestamp}")
        log(f"Base Directory: {self.base_dir}")
        log(f"Initial Aperture Align: X={initial_x:.2f}%, Y={initial_y:.2f}%")
        if cut_duration is None:
            if self.microtome is not None:
                actual_cut_duration = getattr(self.microtome, 'full_cut_duration', 15.0)
            else:
                actual_cut_duration = 15.0
        else:
            actual_cut_duration = float(cut_duration)

        if actual_cut_duration is None or actual_cut_duration <= 0:
            actual_cut_duration = 15.0

        log(f"Grid Size: {grid_size} x {grid_size}, Step Size: {step_size:.2f}%")
        log(f"Frame Size Selector: {frame_size_selector}, Dwell Time: {dwell_time} us")
        log(f"Pixel Size: {pixel_size:.1f} nm")
        if perform_cut:
            log(f"Physical Cut Enabled: Cut Thickness = {cut_thickness:.1f} nm, Cut Duration = {actual_cut_duration:.1f} s")

        # Normalise eval_strategy
        if eval_strategy not in ('radial_symmetry', 'center_sharpness'):
            log(f"Warning: Unknown eval_strategy '{eval_strategy}', defaulting to 'radial_symmetry'.")
            eval_strategy = 'radial_symmetry'
        log(f"Evaluation Strategy: {eval_strategy}")
        if register_images:
            log("Register and Crop Images: Enabled (Phase cross-correlation)")
        log("=" * 60)

        # Generate grid offsets
        if grid_size % 2 == 1:
            half_n = grid_size // 2
            offsets = [i * step_size for i in range(-half_n, half_n + 1)]
        else:
            half_n = grid_size / 2.0
            offsets = [(i + 0.5 - half_n) * step_size for i in range(grid_size)]
        grid_points = []
        for i, dy in enumerate(offsets):
            # Snake-like pattern: alternate left-to-right and right-to-left
            row_dx = offsets if i % 2 == 0 else reversed(offsets)
            for dx in row_dx:
                grid_points.append((initial_x + dx, initial_y + dy))

        total_points = len(grid_points)
        results = []

        # Apply imaging frame parameters
        try:
            self.sem.apply_frame_settings(frame_size_selector, pixel_size, dwell_time)
        except Exception as e:
            log(f"Warning: Could not set frame settings via apply_frame_settings: {e}")

        acquired_frame_paths = []
        acquired_grid_points = []

        # Worker pool for concurrent image analysis while SEM scans the next frame
        with ThreadPoolExecutor(max_workers=2) as executor:
            pending_evals = []

            for idx, (gx, gy) in enumerate(grid_points):
                if self.should_abort:
                    log("Sweep aborted by user.")
                    break

                step_msg = f"Step {idx + 1}/{total_points}: Setting Aperture X={gx:.2f}%, Y={gy:.2f}%"
                log(step_msg)
                if progress_callback:
                    progress_callback(idx + 1, total_points, step_msg)

                # 1. Set SEM aperture alignment
                # If physical cutting is disabled, or for the very first step (idx == 0):
                # set the aperture alignment and allow deflector settle time.
                # (When physical cutting is enabled, steps idx > 0 had their aperture set
                # before the previous cut started, giving deflector coils the entire cut duration to settle.)
                if not perform_cut or idx == 0:
                    self.sem.set_aperture_align_xy(gx, gy)
                    time.sleep(1.0)  # Settle time for deflector coils

                # 2. Acquire calibration frame
                frame_filename = f"frame_{idx + 1:03d}_X{gx:+.2f}_Y{gy:+.2f}.tif"
                frame_path = os.path.join(run_dir, frame_filename)

                acquired = self.sem.acquire_frame(frame_path)
                if not acquired:
                    log(f"Error acquiring frame at X={gx:.2f}%, Y={gy:.2f}%")
                    if not os.path.exists(frame_path):
                        dummy_img = np.zeros((768, 1024), dtype=np.uint8)
                        cv2.imwrite(frame_path, dummy_img)

                # 3. Ensure frame is safely finished and completely stored to disk
                wait_file_start = time.time()
                while (not os.path.exists(frame_path) or os.path.getsize(frame_path) == 0) and (time.time() - wait_file_start < 5.0):
                    time.sleep(0.1)
                time.sleep(0.2)
                log(f"Frame safely finished and stored: {frame_filename}")
                acquired_frame_paths.append(frame_path)
                acquired_grid_points.append((gx, gy))

                # 4. Dispatch async image evaluation if not registering images
                if not register_images:
                    def eval_task(fpath, ax, ay, _strategy=eval_strategy):
                        loaded_img = cv2.imread(fpath, cv2.IMREAD_GRAYSCALE)
                        if loaded_img is None:
                            loaded_img = np.zeros((768, 1024), dtype=np.uint8)
                        if _strategy == 'center_sharpness':
                            metrics = evaluate_center_sharpness(loaded_img)
                        else:
                            metrics = evaluate_radial_symmetry(loaded_img)
                        return {
                            'x': ax,
                            'y': ay,
                            'frame_path': fpath,
                            'metrics': metrics
                        }

                    future = executor.submit(eval_task, frame_path, gx, gy)
                    pending_evals.append(future)

                # 5. If physical cutting is enabled and not the last step:
                # 1) Set next aperture alignment BEFORE physical cut starts
                # 2) Advance stage Z
                # 3) Execute physical cut and wait for full_cut_duration
                if perform_cut and self.microtome is not None and idx < (total_points - 1):
                    if self.should_abort:
                        log("Sweep aborted by user before microtome cut.")
                        break

                    # Set next aperture change before physical cut starts
                    next_gx, next_gy = grid_points[idx + 1]
                    log(f"Setting next aperture alignment to X={next_gx:.2f}%, Y={next_gy:.2f}% before physical cut...")
                    self.sem.set_aperture_align_xy(next_gx, next_gy)

                    cut_msg = f"Step {idx + 1}/{total_points}: Frame recorded. Initiating physical cut before next frame..."
                    log(cut_msg)
                    if progress_callback:
                        progress_callback(idx + 1, total_points, cut_msg)

                    try:
                        cur_z = getattr(self.microtome, 'last_known_z', None)
                        if cur_z is None:
                            if hasattr(self.microtome, 'get_stage_z'):
                                cur_z = self.microtome.get_stage_z()
                            else:
                                cur_z = 0.0

                        target_z = cur_z + (cut_thickness / 1000.0)
                        log(f"Advancing microtome stage Z by {cut_thickness:.1f} nm ({cur_z:.3f} -> {target_z:.3f} µm)...")
                        self.microtome.move_stage_to_z(target_z)
                        self.microtome.last_known_z = target_z
                        if (hasattr(self.microtome, 'cfg')
                                and isinstance(getattr(self.microtome, 'cfg', None), dict)
                                and 'microtome' in self.microtome.cfg):
                            self.microtome.cfg['microtome']['last_known_z'] = str(target_z)
                        if stage_z_callback:
                            stage_z_callback(target_z)

                        wait_interval = getattr(self.microtome, 'stage_move_wait_interval', 0.5)
                        time.sleep(wait_interval)

                        log(f"Performing physical cut (waiting full cut duration: {actual_cut_duration:.1f} s)...")
                        self.microtome.do_full_cut()
                        time.sleep(actual_cut_duration)
                        time.sleep(0.5)  # Vibration settling time after cut
                        log("Physical cut cycle completed.")
                    except Exception as e:
                        log(f"Error during microtome cut: {e}")

        cumm_shifts_list = []
        cropped_dims = []

        if register_images and len(acquired_frame_paths) > 1 and not self.should_abort:
            log("Registering calibration images via phase cross-correlation...")
            if progress_callback:
                progress_callback(total_points, total_points, "Registering and cropping calibration frames...")

            shifts = []
            for i in range(1, len(acquired_frame_paths)):
                shift_pair = utils.compute_shifts_cv2([acquired_frame_paths[i - 1], acquired_frame_paths[i]])
                shifts.append(shift_pair[0])

            cumm_shifts = np.cumsum(shifts, axis=0)
            cumm_shifts_list = cumm_shifts.tolist()
            log(f"Cumulative registration shifts relative to first frame (dY, dX pixels):\n{cumm_shifts}")

            # Load, shift, and crop image collection
            ic = utils.load_image_collection(acquired_frame_paths)
            orig_h, orig_w = ic.shape[1], ic.shape[2]
            shifted_ic = utils.shift_collection(ic, cumm_shifts)
            cropped_ic = utils.crop_image_collection(shifted_ic, cumm_shifts)

            if cropped_ic.shape[1] < 32 or cropped_ic.shape[2] < 32:
                log("Warning: Cropped image dimensions too small after registration. Falling back to uncropped images.")
                eval_ic = shifted_ic
            else:
                eval_ic = cropped_ic

            crop_h, crop_w = eval_ic.shape[1], eval_ic.shape[2]
            cropped_dims = [int(crop_h), int(crop_w)]
            log(f"Cropped registered series from ({orig_h}, {orig_w}) to ({crop_h}, {crop_w})")

            reg_dir = os.path.join(run_dir, 'registered')
            os.makedirs(reg_dir, exist_ok=True)

            for i, (gx, gy) in enumerate(acquired_grid_points):
                reg_filename = os.path.basename(acquired_frame_paths[i])
                reg_frame_path = os.path.join(reg_dir, reg_filename)
                cv2.imwrite(reg_frame_path, np.clip(eval_ic[i], 0, 255).astype(np.uint8))

                if eval_strategy == 'center_sharpness':
                    metrics = evaluate_center_sharpness(eval_ic[i])
                else:
                    metrics = evaluate_radial_symmetry(eval_ic[i])

                cur_shift = [float(cumm_shifts[i - 1][0]), float(cumm_shifts[i - 1][1])] if i > 0 else [0.0, 0.0]
                results.append({
                    'x': gx,
                    'y': gy,
                    'frame_path': acquired_frame_paths[i],
                    'registered_frame_path': reg_frame_path,
                    'metrics': metrics,
                    'cumulative_shift': cur_shift
                })
                if eval_strategy == 'center_sharpness':
                    log(
                        f"Result X={gx:.2f}%, Y={gy:.2f}% -> "
                        f"Center Sharpness: {metrics['center_sharpness']:.2f}, "
                        f"Mean Sharpness: {metrics['mean_sharpness']:.2f} (shift: dY={cur_shift[0]:.1f}, dX={cur_shift[1]:.1f})"
                    )
                else:
                    log(
                        f"Result X={gx:.2f}%, Y={gy:.2f}% -> "
                        f"Symmetry Score: {metrics['symmetry_score']:.4f}, "
                        f"Asymmetry: {metrics['asymmetry_score']:.4f}, "
                        f"Center Sharpness: {metrics['center_sharpness']:.2f} (shift: dY={cur_shift[0]:.1f}, dX={cur_shift[1]:.1f})"
                    )
        elif register_images and len(acquired_frame_paths) == 1 and not self.should_abort:
            single_path = acquired_frame_paths[0]
            loaded_img = cv2.imread(single_path, cv2.IMREAD_GRAYSCALE)
            if loaded_img is None:
                loaded_img = np.zeros((768, 1024), dtype=np.uint8)
            if eval_strategy == 'center_sharpness':
                metrics = evaluate_center_sharpness(loaded_img)
            else:
                metrics = evaluate_radial_symmetry(loaded_img)
            results.append({
                'x': acquired_grid_points[0][0],
                'y': acquired_grid_points[0][1],
                'frame_path': single_path,
                'registered_frame_path': single_path,
                'metrics': metrics,
                'cumulative_shift': [0.0, 0.0]
            })
        elif not register_images:
            # Collect analysis results from pending_evals
            for future in pending_evals:
                res = future.result()
                results.append(res)
                metrics = res['metrics']
                if eval_strategy == 'center_sharpness':
                    log(
                        f"Result X={res['x']:.2f}%, Y={res['y']:.2f}% -> "
                        f"Center Sharpness: {metrics['center_sharpness']:.2f}, "
                        f"Mean Sharpness: {metrics['mean_sharpness']:.2f}"
                    )
                else:
                    log(
                        f"Result X={res['x']:.2f}%, Y={res['y']:.2f}% -> "
                        f"Symmetry Score: {metrics['symmetry_score']:.4f}, "
                        f"Asymmetry: {metrics['asymmetry_score']:.4f}, "
                        f"Center Sharpness: {metrics['center_sharpness']:.2f}"
                    )

        if not results or self.should_abort:
            self.sem.set_aperture_align_xy(initial_x, initial_y)
            log(f"Reinstated initial aperture alignment on SEM: X={initial_x:.2f}%, Y={initial_y:.2f}%")
            self.is_running = False
            return {}

        # Determine discrete best result
        best_result = max(results, key=lambda r: r['metrics']['symmetry_score'])
        optimal_x = best_result['x']
        optimal_y = best_result['y']
        optimal_score = best_result['metrics']['symmetry_score']

        # If center_sharpness strategy (or if sufficient points available), fit 2D surface to locate global continuous peak
        xs = [r['x'] for r in results]
        ys = [r['y'] for r in results]
        scores = [r['metrics']['symmetry_score'] for r in results]
        fitted_peak = fit_2d_surface(xs, ys, scores)
        fitted_optimal_x = None
        fitted_optimal_y = None
        fitted_optimal_score = None

        if fitted_peak is not None:
            fitted_optimal_x, fitted_optimal_y, fitted_optimal_score = fitted_peak
            log(f"2D Surface Fit located continuous optimum: X={fitted_optimal_x:.2f}%, Y={fitted_optimal_y:.2f}% (predicted {fitted_optimal_score:.4f})")
            if eval_strategy == 'center_sharpness':
                optimal_x = round(fitted_optimal_x, 2)
                optimal_y = round(fitted_optimal_y, 2)
                optimal_score = fitted_optimal_score

        initial_score = results[0]['metrics']['symmetry_score']
        for r in results:
            if abs(r['x'] - initial_x) < 1e-4 and abs(r['y'] - initial_y) < 1e-4:
                initial_score = r['metrics']['symmetry_score']
                break

        if eval_strategy == 'center_sharpness':
            score_label = 'Center Sharpness'
        else:
            score_label = 'Symmetry Score'

        log("=" * 60)
        log(f"Optimal Aperture Alignment Found: X={optimal_x:.2f}%, Y={optimal_y:.2f}%")
        log(f"Initial {score_label}: {initial_score:.4f} -> Optimal: {optimal_score:.4f}")
        log("=" * 60)

        # Save results JSON
        json_path = os.path.join(run_dir, 'sharpness_data.json')
        output_data = {
            'timestamp': timestamp,
            'grid_size': grid_size,
            'step_size': step_size,
            'pixel_size': pixel_size,
            'perform_cut': perform_cut,
            'cut_thickness': cut_thickness,
            'cut_duration': actual_cut_duration,
            'eval_strategy': eval_strategy,
            'register_images': register_images,
            'cumulative_shifts': cumm_shifts_list,
            'cropped_dimensions': cropped_dims,
            'initial_x': initial_x,
            'initial_y': initial_y,
            'optimal_x': optimal_x,
            'optimal_y': optimal_y,
            'initial_score': initial_score,
            'optimal_score': optimal_score,
            'discrete_optimal_x': best_result['x'],
            'discrete_optimal_y': best_result['y'],
            'fitted_optimal_x': fitted_optimal_x,
            'fitted_optimal_y': fitted_optimal_y,
            'fitted_optimal_score': fitted_optimal_score,
            'results': results
        }
        with open(json_path, 'w') as f:
            json.dump(output_data, f, indent=2)

        # Generate 2D Heatmap & Diagnostic Plots
        plot_path = os.path.join(run_dir, 'aperture_centering_heatmap.png')
        self.generate_plots(output_data, plot_path)
        log(f"Saved diagnostic plots to: {plot_path}")

        # Reinstate initial aperture alignment on SEM by default unless auto_apply is True
        if auto_apply:
            self.sem.set_aperture_align_xy(optimal_x, optimal_y)
            log(f"Auto-applied optimal aperture alignment on SEM: X={optimal_x:.2f}%, Y={optimal_y:.2f}%")
        else:
            self.sem.set_aperture_align_xy(initial_x, initial_y)
            log(f"Reinstated initial aperture alignment on SEM: X={initial_x:.2f}%, Y={initial_y:.2f}%")

        self.latest_results = output_data
        self.is_running = False
        return output_data

    @staticmethod
    def generate_plots(data: Dict[str, Any], save_path: str):
        """Generate a 2D score heatmap and secondary diagnostic plot of the calibration run."""
        results = data['results']
        xs = [r['x'] for r in results]
        ys = [r['y'] for r in results]
        scores = [r['metrics']['symmetry_score'] for r in results]
        strategy = data.get('eval_strategy', 'radial_symmetry')
        init_x = data.get('initial_x', 0.0)
        init_y = data.get('initial_y', 0.0)
        opt_x = data.get('optimal_x', 0.0)
        opt_y = data.get('optimal_y', 0.0)
        fitted_x = data.get('fitted_optimal_x')
        fitted_y = data.get('fitted_optimal_y')

        if strategy == 'center_sharpness':
            score_label = 'Center Sharpness'
            heatmap_title = f'Aperture Centering: Center Sharpness (Initial: X={init_x:.2f}%, Y={init_y:.2f}%)'
        else:
            score_label = 'Radial Symmetry Score'
            heatmap_title = f'Aperture Centering: Focal Plane Symmetry (Initial: X={init_x:.2f}%, Y={init_y:.2f}%)'

        unique_x = sorted(list(set(xs)))
        unique_y = sorted(list(set(ys)))
        grid_w = len(unique_x)
        grid_h = len(unique_y)

        fig, axes = plt.subplots(1, 2, figsize=(13, 5))

        # 1. 2D Score Heatmap
        if grid_w > 1 and grid_h > 1:
            heatmap = np.zeros((grid_h, grid_w), dtype=np.float32)
            for r in results:
                ix = unique_x.index(r['x'])
                iy = unique_y.index(r['y'])
                heatmap[iy, ix] = r['metrics']['symmetry_score']

            im = axes[0].imshow(
                heatmap,
                extent=[min(unique_x), max(unique_x), min(unique_y), max(unique_y)],
                origin='lower',
                cmap='viridis',
                aspect='auto'
            )
            fig.colorbar(im, ax=axes[0], label=score_label)
        else:
            sc = axes[0].scatter(xs, ys, c=scores, cmap='viridis', s=100)
            fig.colorbar(sc, ax=axes[0], label=score_label)

        # Highlight Initial and Optimal Positions
        if fitted_x is not None and fitted_y is not None:
            optimal_label = f'Optimal Center (Fit: X={fitted_x:.2f}%, Y={fitted_y:.2f}%)'
        else:
            optimal_label = f'Optimal Center (X={opt_x:.2f}%, Y={opt_y:.2f}%)'

        axes[0].plot(
            init_x, init_y,
            marker='x', color='red', markersize=12, mew=2, label=f'Initial (X={init_x:.2f}%, Y={init_y:.2f}%)'
        )
        axes[0].plot(
            opt_x, opt_y,
            marker='*', color='yellow', markersize=16, mew=1.5, mec='black', label=optimal_label
        )
        axes[0].set_xlabel('Aperture Align X (%)')
        axes[0].set_ylabel('Aperture Align Y (%)')
        axes[0].set_title(heatmap_title)
        axes[0].legend(loc='best')
        axes[0].grid(True, linestyle='--', alpha=0.5)
        axes[0].invert_yaxis()

        # 2. Secondary panel
        best_r = max(results, key=lambda r: r['metrics']['symmetry_score'])
        init_r = results[0]
        for r in results:
            if abs(r['x'] - data['initial_x']) < 1e-4 and abs(r['y'] - data['initial_y']) < 1e-4:
                init_r = r
                break

        if strategy == 'center_sharpness':
            # 2D Heatmap for Mean Sharpness
            mean_scores = [r['metrics'].get('mean_sharpness', 0.0) for r in results]
            if grid_w > 1 and grid_h > 1:
                mean_heatmap = np.zeros((grid_h, grid_w), dtype=np.float32)
                for r in results:
                    ix = unique_x.index(r['x'])
                    iy = unique_y.index(r['y'])
                    mean_heatmap[iy, ix] = r['metrics'].get('mean_sharpness', 0.0)

                im_mean = axes[1].imshow(
                    mean_heatmap,
                    extent=[min(unique_x), max(unique_x), min(unique_y), max(unique_y)],
                    origin='lower',
                    cmap='viridis',
                    aspect='auto'
                )
                fig.colorbar(im_mean, ax=axes[1], label='Mean Sharpness')
            else:
                sc_mean = axes[1].scatter(xs, ys, c=mean_scores, cmap='viridis', s=100)
                fig.colorbar(sc_mean, ax=axes[1], label='Mean Sharpness')

            axes[1].plot(
                init_x, init_y,
                marker='x', color='red', markersize=12, mew=2, label=f'Initial (X={init_x:.2f}%, Y={init_y:.2f}%)'
            )
            axes[1].plot(
                opt_x, opt_y,
                marker='*', color='yellow', markersize=16, mew=1.5, mec='black', label=optimal_label
            )
            axes[1].set_xlabel('Aperture Align X (%)')
            axes[1].set_ylabel('Aperture Align Y (%)')
            axes[1].set_title('Aperture Centering: Mean Sharpness')
            axes[1].legend(loc='best')
            axes[1].grid(True, linestyle='--', alpha=0.5)
            axes[1].invert_yaxis()
        else:
            # Radial Profiles Comparison (Initial vs Optimal)
            init_rad = init_r['metrics'].get('radial_profile', [])
            best_rad = best_r['metrics'].get('radial_profile', [])
            rings = list(range(len(best_rad)))

            if init_rad and best_rad:
                axes[1].plot(rings, init_rad, 'r-o', label=f"Initial (X={init_r['x']:.1f}%, Y={init_r['y']:.1f}%)")
                axes[1].plot(rings, best_rad, 'g-s', label=f"Optimal (X={best_r['x']:.1f}%, Y={best_r['y']:.1f}%)")
                axes[1].set_xlabel('Radial Ring Index (0=Center -> Outer)')
                axes[1].set_ylabel('Mean Sharpness')
                axes[1].set_title('Sharpness Falloff vs. Radius')
                axes[1].legend(loc='best')
                axes[1].grid(True, linestyle='--', alpha=0.5)

        plt.tight_layout()
        plt.savefig(save_path, dpi=150)
        plt.close(fig)
