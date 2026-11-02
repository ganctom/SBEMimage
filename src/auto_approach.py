# -*- coding: utf-8 -*-
"""
Auto-Approach Engine (Qt-Free).

Implements single-scan odd/even raster scan-line self-calibration, bounded
subpixel registration, dual SSIM modes (Normalized and Gradient), contrast-matched
Cyan/Magenta overlay rendering, and complete Gatan 3View hardware state machine
with non-destructive knife safety invariants.

Follows strict Python 3.7.6 constraints: no walrus operator, no PEP 585/604 syntax.
Zero PyQt5 or QObject imports (AD-AUTO_APPROACH-001).
"""

from __future__ import division

import datetime as dt
import json
import logging
import math
import os
import threading
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

import cv2
import numpy as np
import scipy.ndimage
from skimage.metrics import structural_similarity
from skimage.registration import phase_cross_correlation

from utils import Error


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain Enumerations & Constants
# ---------------------------------------------------------------------------

class ApproachState(object):
    IDLE = 'IDLE'
    CALIBRATING_BASELINE = 'CALIBRATING_BASELINE'
    CUTTING_BATCH = 'CUTTING_BATCH'
    CLEARING_KNIFE = 'CLEARING_KNIFE'
    ACQUIRING_TILES = 'ACQUIRING_TILES'
    EVALUATING = 'EVALUATING'
    CONTACT_DETECTED = 'CONTACT_DETECTED'
    SAFETY_LIMIT_REACHED = 'SAFETY_LIMIT_REACHED'
    PREFLIGHT_FAILED = 'PREFLIGHT_FAILED'
    ABORTED = 'ABORTED'
    ERROR = 'ERROR'


class SSIMMode(object):
    NORMALIZED = 0
    GRADIENT = 1


# ---------------------------------------------------------------------------
# Data Contracts & NamedTuples
# ---------------------------------------------------------------------------

class AutoApproachConfig(NamedTuple):
    mode: int
    slice_thickness_nm: int
    batch_slices: int
    max_depth_um: float
    probe_tiles: List[str]
    dwell_time_override_us: float
    ssim_mode: int

    @classmethod
    def from_cfg(cls, d: Dict[str, Any]) -> 'AutoApproachConfig':
        """Parse from [approach] config dictionary."""
        probe_val = d.get('probe_tiles', '[]')
        if isinstance(probe_val, list):
            probe_tiles = [str(x) for x in probe_val]
        else:
            try:
                probe_tiles = [str(x) for x in json.loads(str(probe_val))]
            except Exception:
                probe_tiles = []

        return cls(
            mode=int(d.get('mode', 0)),
            slice_thickness_nm=int(d.get('slice_thickness', 100)),
            batch_slices=int(d.get('batch_slices', 5)),
            max_depth_um=float(d.get('max_depth_um', 20.0)),
            probe_tiles=probe_tiles,
            dwell_time_override_us=float(d.get('dwell_time_override', -1.0)),
            ssim_mode=int(d.get('ssim_mode', SSIMMode.NORMALIZED)),
        )

    def to_cfg(self) -> Dict[str, str]:
        """Serialize to [approach] config dictionary."""
        return {
            'mode': str(self.mode),
            'slice_thickness': str(self.slice_thickness_nm),
            'batch_slices': str(self.batch_slices),
            'max_depth_um': str(self.max_depth_um),
            'probe_tiles': json.dumps(self.probe_tiles),
            'dwell_time_override': str(self.dwell_time_override_us),
            'ssim_mode': str(self.ssim_mode),
        }


class TileCalibrationProfile(NamedTuple):
    tile_key: str
    valid: bool
    pyramid_level: int
    internal_ssim: float
    noise_dissimilarity: float
    cut_dissimilarity_limit: float
    max_shift_px: int
    failure_reason: Optional[str]


class TileStepEvaluation(NamedTuple):
    tile_key: str
    step_index: int
    raw_image_path: str
    overlay_image_path: Optional[str]
    shift_yx_px: Tuple[float, float]
    cross_ssim: float
    dissimilarity: float
    contact_detected: bool


class ApproachStepRecord(NamedTuple):
    step_index: int
    slices_cut_cumulative: int
    depth_removed_um: float
    z_stage_um: float
    triggered_tiles: List[str]
    tile_evaluations: Dict[str, TileStepEvaluation]


class ApproachProgress(NamedTuple):
    state: str
    step_index: int
    slices_cut_total: int
    depth_removed_um: float
    max_depth_um: float
    current_batch_slice: int
    batch_slices: int
    triggered_tiles: List[str]
    run_dir: Optional[str]
    message: str


ProgressCallback = Callable[[ApproachProgress, Optional[ApproachStepRecord]], None]
StageCallback = Callable[[str], None]


# ---------------------------------------------------------------------------
# Algorithmic Core: Validation, Pyramids, Registration, SSIM, Compositor
# ---------------------------------------------------------------------------

def validate_tile_frame(img: Optional[np.ndarray]) -> Tuple[bool, Optional[str]]:
    """Check whether a tile frame is valid for approach tracking."""
    if img is None:
        return False, "Image acquisition failed (frame is None)"
    if not isinstance(img, np.ndarray) or img.size == 0:
        return False, "Frame is empty or invalid array"
    if img.ndim != 2:
        return False, "Frame must be 2D grayscale array"

    h, w = img.shape
    if h < 64 or w < 64:
        return False, "Frame dimensions too small (< 64x64)"

    mean_val = float(np.mean(img))
    std_val = float(np.std(img))

    if mean_val <= 1.0:
        return False, "Frame is completely blank/black (mean <= 1.0)"
    if mean_val >= 254.0:
        return False, "Frame is completely saturated/white (mean >= 254.0)"
    if std_val < 0.5:
        return False, "Frame is featureless/flat (std < 0.5)"

    return True, None


def split_and_interpolate_odd_even(img: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Split frame into even and odd scan lines and align symmetrically on lattice y = 2r + 1.5.

    Guarantees exact centroid coincidence (< 1e-9 px) and identical noise variance (5/8).
    """
    img_f = img.astype(np.float64, copy=False)
    h = img_f.shape[0]
    m = h // 2
    e0 = img_f[0:2 * m:2, :]
    o0 = img_f[1:2 * m:2, :]

    # E~[r] = 1/4 E[r] + 3/4 E[r+1]  (centroid = 1/4(2r) + 3/4(2r+2) = 2r + 1.5)
    # O~[r] = 3/4 O[r] + 1/4 O[r+1]  (centroid = 3/4(2r+1) + 1/4(2r+3) = 2r + 1.5)
    e_tilde = 0.25 * e0[0:m - 1, :] + 0.75 * e0[1:m, :]
    o_tilde = 0.75 * o0[0:m - 1, :] + 0.25 * o0[1:m, :]
    return e_tilde, o_tilde


def downsample_2x_block_average(img: np.ndarray) -> np.ndarray:
    """Downsample image by 2x using block-area averaging."""
    h, w = img.shape
    h_even = (h // 2) * 2
    w_even = (w // 2) * 2
    cropped = img[:h_even, :w_even]
    return 0.25 * (
        cropped[0::2, 0::2] +
        cropped[0::2, 1::2] +
        cropped[1::2, 0::2] +
        cropped[1::2, 1::2]
    )


def compute_stage_clamp_px(pixel_size_nm: float, pyramid_level: int, h: int, w: int) -> int:
    """Calculate stage wander clamp s_max per architecture Section 2.2."""
    effective_px_nm = max(float(pixel_size_nm) * (2 ** pyramid_level), 0.1)
    wander_limit = int(math.ceil(15000.0 / effective_px_nm))
    dim_limit = int(math.floor(0.15 * min(h, w)))
    return max(2, min(wander_limit, dim_limit))


def preprocess_approach_frame(
    img: Optional[np.ndarray],
    sigma: float = 1.0,
    clip_limit: float = 2.0,
    tile_grid: Tuple[int, int] = (8, 8)
) -> Optional[np.ndarray]:
    """
    Preprocess approach frame with Gaussian denoising and CLAHE contrast equalization.

    Applies:
      1. Gaussian filter (sigma=1.0) to suppress high-frequency Poisson shot noise.
      2. CLAHE (clipLimit=2.0, tileGridSize=(8, 8)) to remove macroscopic illumination
         and stain gradients while enhancing specimen ultrastructure boundaries.
    """
    if img is None or not isinstance(img, np.ndarray) or img.size == 0:
        return img

    if img.dtype != np.uint8:
        min_v = float(np.min(img))
        max_v = float(np.max(img))
        if max_v > min_v:
            img_u8 = np.clip((img - min_v) / (max_v - min_v) * 255.0, 0.0, 255.0).astype(np.uint8)
        else:
            img_u8 = np.zeros(img.shape, dtype=np.uint8)
    else:
        img_u8 = img

    blurred = cv2.GaussianBlur(img_u8, (0, 0), sigmaX=sigma, sigmaY=sigma)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tuple(tile_grid))
    equalized = clahe.apply(blurred)
    return equalized


def compute_structural_contrast(img_raw: Optional[np.ndarray]) -> float:
    """
    Decompose raw single-scan baseline frame variance into detector noise and specimen contrast.

    Calculates:
      diff = E~[r] - O~[r]
      sigma_noise^2 = 0.5 * Var(diff)
      sigma_total^2 = Var(img_raw)
      sigma_struct^2 = max(0.0, sigma_total^2 - sigma_noise^2)
      gamma_struct = sqrt(sigma_struct^2) / (sqrt(sigma_total^2) + 1e-6)

    Returns gamma_struct in [0.0, 1.0].
    """
    if img_raw is None or not isinstance(img_raw, np.ndarray) or img_raw.ndim != 2:
        return 0.0
    h, w = img_raw.shape
    if h < 4 or w < 4:
        return 0.0

    img_f = img_raw.astype(np.float64, copy=False)
    e_tilde, o_tilde = split_and_interpolate_odd_even(img_f)
    diff = e_tilde - o_tilde
    var_noise = 0.5 * float(np.var(diff))
    var_total = float(np.var(img_f))
    var_struct = max(0.0, var_total - var_noise)
    gamma = math.sqrt(var_struct) / (math.sqrt(var_total) + 1e-6)
    return float(np.clip(gamma, 0.0, 1.0))


def compute_tile_cut_threshold(gamma_struct: float) -> float:
    """
    Compute dynamic tile-specific cut dissimilarity threshold.

    d_trigger(tile) = clamp(0.35 + 7.5 * (0.75 - gamma_struct), 0.300, 0.660)
    """
    thresh = 0.35 + 7.5 * (0.75 - float(gamma_struct))
    return float(np.clip(thresh, 0.300, 0.660))


def register_and_crop(
    prev_img: np.ndarray,
    curr_img: np.ndarray,
    pixel_size_nm: float,
    pyramid_level: int = 0
) -> Tuple[np.ndarray, np.ndarray, Tuple[float, float]]:
    """
    Subpixel register curr_img to prev_img at pyramid level l*.

    Performs phase_cross_correlation on a 10% center crop ([0.10H:0.90H, 0.10W:0.90W])
    to eliminate boundary artifacts, scan transients, and knife perimeter shadows.
    Shifts full curr_img and crops the overlapping valid area.
    Returns (prev_crop, curr_crop, (dy, dx)).
    """
    p_prev = prev_img.astype(np.float64, copy=False)
    p_curr = curr_img.astype(np.float64, copy=False)

    for _ in range(pyramid_level):
        p_prev = downsample_2x_block_average(p_prev)
        p_curr = downsample_2x_block_average(p_curr)

    h, w = p_prev.shape
    s_max = compute_stage_clamp_px(pixel_size_nm, pyramid_level, h, w)

    # 10% Center Crop for cross correlation to avoid edge artifacts and scan flyback
    y1, y2 = int(0.10 * h), int(0.90 * h)
    x1, x2 = int(0.10 * w), int(0.90 * w)
    if (y2 - y1) >= 16 and (x2 - x1) >= 16:
        c_prev = p_prev[y1:y2, x1:x2]
        c_curr = p_curr[y1:y2, x1:x2]
    else:
        c_prev = p_prev
        c_curr = p_curr

    try:
        corr_res = phase_cross_correlation(c_prev, c_curr, upsample_factor=10)
        # scikit-image 0.17.2 returns (shifts, error, phasediff)
        shift = corr_res[0] if isinstance(corr_res, (tuple, list)) else corr_res
        dy = float(shift[0])
        dx = float(shift[1])
    except Exception as e:
        logger.warning("phase_cross_correlation failed: %s; zeroing shift", e)
        dy, dx = 0.0, 0.0

    # Safety clamp: if shift exceeds physical stage wander (e.g. 100% shaved correlation collapse)
    if abs(dy) > s_max or abs(dx) > s_max:
        dy, dx = 0.0, 0.0
        c = 2
        crop_prev = p_prev[c:h - c, c:w - c]
        crop_curr = p_curr[c:h - c, c:w - c]
        return crop_prev, crop_curr, (0.0, 0.0)

    # Shift full curr to align with prev
    shifted_curr = scipy.ndimage.shift(p_curr, (dy, dx), order=1, mode='nearest')

    cy = max(int(math.ceil(abs(dy))) + 1, 1)
    cx = max(int(math.ceil(abs(dx))) + 1, 1)

    crop_prev = p_prev[cy:h - cy, cx:w - cx]
    crop_curr = shifted_curr[cy:h - cy, cx:w - cx]

    return crop_prev, crop_curr, (dy, dx)


def evaluate_ssim(
    prev_crop: np.ndarray,
    curr_crop: np.ndarray,
    ssim_mode: int,
    prev_std: Optional[float] = None
) -> float:
    """Evaluate structural similarity under Normalized SSIM or Gradient SSIM."""
    if prev_crop.shape != curr_crop.shape or prev_crop.size == 0:
        return 0.0

    if ssim_mode == SSIMMode.NORMALIZED:
        u = prev_crop.astype(np.float64, copy=False)
        v = curr_crop.astype(np.float64, copy=False)

        mu_u = float(np.mean(u))
        sigma_u = float(np.std(u))
        u_std_ref = prev_std if (prev_std is not None and prev_std > 0) else sigma_u

        mu_v = float(np.mean(v))
        sigma_v = float(np.std(v))

        # Smooth-resin variance floor guard (architecture Section 2.3)
        denom_u = max(sigma_u, 1e-6)
        denom_v = max(sigma_v, 0.25 * u_std_ref, 1e-6)

        u_norm = np.clip((u - mu_u) / denom_u, -4.0, 4.0)
        v_norm = np.clip((v - mu_v) / denom_v, -4.0, 4.0)

        score = structural_similarity(u_norm, v_norm, data_range=8.0)
        return float(np.clip(score, -1.0, 1.0))

    elif ssim_mode == SSIMMode.GRADIENT:
        u = prev_crop.astype(np.float32, copy=False)
        v = curr_crop.astype(np.float32, copy=False)

        gx_u = cv2.Sobel(u, cv2.CV_32F, 1, 0, ksize=3)
        gy_u = cv2.Sobel(u, cv2.CV_32F, 0, 1, ksize=3)
        mag_u = cv2.magnitude(gx_u, gy_u)

        gx_v = cv2.Sobel(v, cv2.CV_32F, 1, 0, ksize=3)
        gy_v = cv2.Sobel(v, cv2.CV_32F, 0, 1, ksize=3)
        mag_v = cv2.magnitude(gx_v, gy_v)

        p99_u = float(np.percentile(mag_u, 99))
        p99_v = float(np.percentile(mag_v, 99))

        norm_u = np.clip(mag_u / max(p99_u, 1e-6), 0.0, 1.0).astype(np.float64)
        norm_v = np.clip(mag_v / max(p99_v, 1e-6), 0.0, 1.0).astype(np.float64)

        score = structural_similarity(norm_u, norm_v, data_range=1.0)
        return float(np.clip(score, -1.0, 1.0))

    return 0.0


def evaluate_pearson_r(
    prev_crop: np.ndarray,
    curr_crop: np.ndarray
) -> float:
    """
    Evaluate global Pearson correlation coefficient between registered overlapping crops.

    Returns correlation r in [-1.0, 1.0].
    Returns 0.0 if either crop has zero variance (e.g. flat resin or sensor failure)
    or if shapes do not match or arrays are empty.
    """
    if prev_crop.shape != curr_crop.shape or prev_crop.size == 0:
        return 0.0

    u = prev_crop.astype(np.float64, copy=False)
    v = curr_crop.astype(np.float64, copy=False)

    u_centered = u - np.mean(u)
    v_centered = v - np.mean(v)

    norm_u = float(np.sqrt(np.sum(u_centered * u_centered)))
    norm_v = float(np.sqrt(np.sum(v_centered * v_centered)))

    if norm_u < 1e-6 or norm_v < 1e-6:
        return 0.0

    r = float(np.sum(u_centered * v_centered) / (norm_u * norm_v))
    return float(np.clip(r, -1.0, 1.0))


def evaluate_tile_pair(
    prev_img: np.ndarray,
    curr_img: np.ndarray,
    calib_profile: TileCalibrationProfile,
    ssim_mode: int,
    pixel_size_nm: float
) -> Tuple[float, float, bool, Tuple[float, float]]:
    """
    Preprocess, register, and evaluate Pearson correlation between consecutive tile frames.

    Returns (pearson_r, dissimilarity, contact_detected, shift_yx_px).
    """
    prep_prev = preprocess_approach_frame(prev_img)
    prep_curr = preprocess_approach_frame(curr_img)

    pyramid_lvl = calib_profile.pyramid_level
    crop_prev, crop_curr, shift_yx = register_and_crop(
        prep_prev, prep_curr, pixel_size_nm, pyramid_lvl
    )

    pearson_r = evaluate_pearson_r(crop_prev, crop_curr)
    dissimilarity = max(0.0, 1.0 - pearson_r)

    contact_detected = bool(dissimilarity >= calib_profile.cut_dissimilarity_limit)
    return pearson_r, dissimilarity, contact_detected, shift_yx


def calibrate_tile_single_scan(
    img: Optional[np.ndarray],
    pixel_size_nm: float,
    ssim_mode: int,
    tile_key: str = ''
) -> TileCalibrationProfile:
    """
    Single-scan odd/even raster scan-line self-calibration on lattice y = 2r + 1.5.

    Splits frame into even and odd lines, aligns symmetrically via 2-tap interpolation:
      E~[r] = 1/4 E[r] + 3/4 E[r+1]
      O~[r] = 3/4 O[r] + 1/4 O[r+1]
    Decomposes raw baseline variance into detector noise and specimen ultrastructure contrast,
    computing the dynamic tile-specific cut dissimilarity threshold:
      d_trigger(tile) = clamp(0.35 + 7.5 * (0.75 - gamma_struct), 0.300, 0.660).
    Verifies that the frame has sufficient specimen ultrastructure SNR (Pearson r >= 0.85).
    """
    valid, reason = validate_tile_frame(img)
    if not valid or img is None:
        return TileCalibrationProfile(
            tile_key=tile_key,
            valid=False,
            pyramid_level=0,
            internal_ssim=0.0,
            noise_dissimilarity=1.0,
            cut_dissimilarity_limit=0.45,
            max_shift_px=2,
            failure_reason=reason
        )

    h, w = img.shape
    m = h // 2
    if m < 32:
        return TileCalibrationProfile(
            tile_key=tile_key,
            valid=False,
            pyramid_level=0,
            internal_ssim=0.0,
            noise_dissimilarity=1.0,
            cut_dissimilarity_limit=0.45,
            max_shift_px=2,
            failure_reason="Tile height insufficient for odd/even raster split (< 64 px)"
        )

    e_tilde, o_tilde = split_and_interpolate_odd_even(img)

    pyr_e = e_tilde
    pyr_o = o_tilde
    best_lvl = 0
    best_ssim = -1.0

    for lvl in range(5):
        # Enforce downsampling down to min original dimension >= 64 (pyr_e min dim >= 32)
        if min(pyr_e.shape[0] * 2, pyr_e.shape[1]) < 64:
            break

        c = 2
        crop_e = pyr_e[c:-c, c:-c]
        crop_o = pyr_o[c:-c, c:-c]

        score = evaluate_pearson_r(crop_e, crop_o)
        if score > best_ssim:
            best_ssim = score
            best_lvl = lvl

        pyr_e = downsample_2x_block_average(pyr_e)
        pyr_o = downsample_2x_block_average(pyr_o)

    if best_ssim < 0.85:
        # Pass dimensions at scale best_lvl
        dim_h_fail = max(h >> best_lvl, 16)
        dim_w_fail = max(w >> best_lvl, 16)
        return TileCalibrationProfile(
            tile_key=tile_key,
            valid=False,
            pyramid_level=best_lvl,
            internal_ssim=best_ssim,
            noise_dissimilarity=max(0.0, 1.0 - best_ssim),
            cut_dissimilarity_limit=0.45,
            max_shift_px=compute_stage_clamp_px(pixel_size_nm, best_lvl, dim_h_fail, dim_w_fail),
            failure_reason="Insufficient surface texture SNR (internal Pearson r %.3f < 0.85)" % best_ssim
        )

    # In the Gaussian + CLAHE preprocessing pipeline, evaluation operates at level 0
    final_lvl = 0
    noise_dissim = max(0.0, 1.0 - best_ssim)
    gamma_struct = compute_structural_contrast(img)
    trigger_thresh = compute_tile_cut_threshold(gamma_struct)
    max_shift = compute_stage_clamp_px(pixel_size_nm, final_lvl, h, w)

    return TileCalibrationProfile(
        tile_key=tile_key,
        valid=True,
        pyramid_level=final_lvl,
        internal_ssim=best_ssim,
        noise_dissimilarity=noise_dissim,
        cut_dissimilarity_limit=trigger_thresh,
        max_shift_px=max_shift,
        failure_reason=None
    )


def compose_cyan_magenta_overlay(
    prev_img: np.ndarray,
    curr_img: np.ndarray,
    shift_yx: Tuple[float, float],
    pyramid_level: int = 0,
    scale_to_width: int = 1024
) -> np.ndarray:
    """
    Compose contrast-matched Cyan/Magenta difference overlay (RGB uint8).

    Neutral gray: unchanged structure (R = G = B)
    Cyan (#00FFFF): pre-cut features shaved away (prev > curr)
    Magenta (#FF00FF): newly exposed cut boundaries (curr > prev)
    """
    scale_factor = 2 ** pyramid_level
    full_dy = shift_yx[0] * scale_factor
    full_dx = shift_yx[1] * scale_factor

    h, w = prev_img.shape
    if w > scale_to_width:
        down_factor = float(scale_to_width) / float(w)
        target_h = int(round(h * down_factor))
        target_w = scale_to_width
        prev_disp = cv2.resize(prev_img, (target_w, target_h), interpolation=cv2.INTER_AREA)
        curr_disp = cv2.resize(curr_img, (target_w, target_h), interpolation=cv2.INTER_AREA)
        disp_dy = full_dy * down_factor
        disp_dx = full_dx * down_factor
    else:
        prev_disp = prev_img.copy()
        curr_disp = curr_img.copy()
        disp_dy = full_dy
        disp_dx = full_dx

    # Align current image to previous
    curr_aligned = scipy.ndimage.shift(
        curr_disp.astype(np.float64, copy=False),
        (disp_dy, disp_dx),
        order=1,
        mode='nearest'
    )
    prev_aligned = prev_disp.astype(np.float64, copy=False)

    # Symmetric robust contrast normalization via median and IQR / std
    med_prev = float(np.median(prev_aligned))
    p75_prev = float(np.percentile(prev_aligned, 75))
    p25_prev = float(np.percentile(prev_aligned, 25))
    iqr_prev = max(p75_prev - p25_prev, 0.0)
    std_prev = float(np.std(prev_aligned))
    scale_base_prev = max(iqr_prev, 1.349 * std_prev, 1.0)

    med_curr = float(np.median(curr_aligned))
    p75_curr = float(np.percentile(curr_aligned, 75))
    p25_curr = float(np.percentile(curr_aligned, 25))
    iqr_curr = max(p75_curr - p25_curr, 0.0)
    std_curr = float(np.std(curr_aligned))
    scale_base_curr = max(iqr_curr, 1.349 * std_curr, 1.0)

    # Symmetric dispersion: floor curr against prev for shaved block faces
    scale_prev = scale_base_prev
    scale_curr = max(scale_base_curr, 0.25 * scale_base_prev)

    # Normalize onto [0, 255] uint8 centered around 128
    norm_prev = np.clip(128.0 + (prev_aligned - med_prev) * (64.0 / scale_prev), 0.0, 255.0).astype(np.uint8)
    norm_curr = np.clip(128.0 + (curr_aligned - med_curr) * (64.0 / scale_curr), 0.0, 255.0).astype(np.uint8)

    # Invalidate boundary shift extrapolation: fill shifted margin bands with matching prev values
    # so boundary extrapolation shows neutral monochrome gray (0 cyan, 0 magenta).
    pad_y = int(np.ceil(abs(disp_dy)))
    pad_x = int(np.ceil(abs(disp_dx)))
    if pad_y > 0:
        if disp_dy > 0:
            norm_curr[:pad_y, :] = norm_prev[:pad_y, :]
        elif disp_dy < 0:
            norm_curr[-pad_y:, :] = norm_prev[-pad_y:, :]
    if pad_x > 0:
        if disp_dx > 0:
            norm_curr[:, :pad_x] = norm_prev[:, :pad_x]
        elif disp_dx < 0:
            norm_curr[:, -pad_x:] = norm_prev[:, -pad_x:]

    # RGB composite: R = Curr, G = Prev, B = max(Prev, Curr)
    r = norm_curr
    g = norm_prev
    b = np.maximum(norm_prev, norm_curr)

    rgb = np.dstack((r, g, b))
    return rgb


# ---------------------------------------------------------------------------
# Core AutoApproachEngine State Machine
# ---------------------------------------------------------------------------

class AutoApproachEngine(object):
    """
    Qt-Free core approach orchestrator for Gatan 3View systems.

    Executes verified cut batches interleaved with probe-tile SEM imaging,
    auto-detects first surface contact, enforces strict non-destructive knife
    invariants, and writes structured run artifacts to disk.
    """

    def __init__(
        self,
        sem: Any,
        microtome: Any,
        stage: Any,
        grid_manager: Any,
        cfg: AutoApproachConfig,
        base_dir: str,
        progress_callback: Optional[ProgressCallback] = None,
        stage_callback: Optional[StageCallback] = None
    ) -> None:
        self.sem = sem
        self.microtome = microtome
        self.stage = stage
        self.grid_manager = grid_manager
        self.cfg = cfg
        self.base_dir = base_dir
        self.progress_callback = progress_callback
        self.stage_callback = stage_callback

        self._abort_event = threading.Event()
        self._current_sem_rotation = None  # type: Optional[float]
        self.state = ApproachState.IDLE
        self.run_dir = None  # type: Optional[str]
        self.calibrations = {}  # type: Dict[str, TileCalibrationProfile]
        self.step_records = []  # type: List[ApproachStepRecord]
        self.previous_frames = {}  # type: Dict[str, np.ndarray]

    @property
    def _abort_requested(self) -> bool:
        return self._abort_event.is_set()

    def request_abort(self) -> None:
        """Signal the engine to halt further cutting cleanly."""
        self._abort_event.set()
        logger.info("AutoApproachEngine: abort requested by operator")

    def _notify_progress(
        self,
        state: str,
        step_index: int,
        slices_cut: int,
        depth_um: float,
        current_batch_slice: int,
        triggered_tiles: List[str],
        message: str,
        step_record: Optional[ApproachStepRecord] = None
    ) -> None:
        self.state = state
        if self.progress_callback is not None:
            prog = ApproachProgress(
                state=state,
                step_index=step_index,
                slices_cut_total=slices_cut,
                depth_removed_um=depth_um,
                max_depth_um=self.cfg.max_depth_um,
                current_batch_slice=current_batch_slice,
                batch_slices=self.cfg.batch_slices,
                triggered_tiles=triggered_tiles,
                run_dir=self.run_dir,
                message=message
            )
            try:
                self.progress_callback(prog, step_record)
            except Exception as e:
                logger.exception("AutoApproachEngine: progress_callback raised exception: %s", e)

    def _save_manifest(
        self,
        terminal_state: str,
        total_slices: int,
        total_depth_um: float
    ) -> None:
        if not self.run_dir or not os.path.isdir(self.run_dir):
            return

        manifest_path = os.path.join(self.run_dir, 'manifest.json')
        calib_dict = {}
        for k, prof in self.calibrations.items():
            calib_dict[k] = {
                'valid': prof.valid,
                'pyramid_level': prof.pyramid_level,
                'internal_ssim': prof.internal_ssim,
                'noise_dissimilarity': prof.noise_dissimilarity,
                'cut_dissimilarity_limit': prof.cut_dissimilarity_limit,
                'max_shift_px': prof.max_shift_px,
                'failure_reason': prof.failure_reason
            }

        steps_list = []
        for rec in self.step_records:
            evals = {}
            for tk, ev in rec.tile_evaluations.items():
                raw_rel = ''
                if ev.raw_image_path:
                    if os.path.isabs(ev.raw_image_path):
                        try:
                            raw_rel = os.path.relpath(ev.raw_image_path, self.run_dir).replace('\\', '/')
                        except Exception:
                            raw_rel = ev.raw_image_path.replace('\\', '/')
                    else:
                        raw_rel = ev.raw_image_path.replace('\\', '/')

                overlay_rel = None
                if ev.overlay_image_path:
                    if os.path.isabs(ev.overlay_image_path):
                        try:
                            overlay_rel = os.path.relpath(ev.overlay_image_path, self.run_dir).replace('\\', '/')
                        except Exception:
                            overlay_rel = ev.overlay_image_path.replace('\\', '/')
                    else:
                        overlay_rel = ev.overlay_image_path.replace('\\', '/')

                evals[tk] = {
                    'step_index': ev.step_index,
                    'raw_image_path': raw_rel,
                    'overlay_image_path': overlay_rel,
                    'shift_yx_px': list(ev.shift_yx_px),
                    'cross_ssim': ev.cross_ssim,
                    'dissimilarity': ev.dissimilarity,
                    'contact_detected': ev.contact_detected
                }
            steps_list.append({
                'step_index': rec.step_index,
                'slices_cut_cumulative': rec.slices_cut_cumulative,
                'depth_removed_um': rec.depth_removed_um,
                'z_stage_um': rec.z_stage_um,
                'triggered_tiles': rec.triggered_tiles,
                'tile_evaluations': evals
            })

        data = {
            'timestamp': dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'terminal_state': terminal_state,
            'total_slices_cut': total_slices,
            'total_depth_removed_um': total_depth_um,
            'config': self.cfg.to_cfg(),
            'calibrations': calib_dict,
            'steps': steps_list
        }

        try:
            with open(manifest_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("AutoApproachEngine: failed to save manifest.json: %s", e)

    def _resolve_tile(self, tile_key: str) -> Optional[Any]:
        try:
            parts = tile_key.split('.')
            g = int(parts[0])
            t = int(parts[1])
            return self.grid_manager[g][t]
        except Exception:
            return None

    def _resolve_grid(self, tile_key: str) -> Optional[Any]:
        try:
            g = int(tile_key.split('.')[0])
            return self.grid_manager[g]
        except Exception:
            return None

    def run(self) -> ApproachProgress:
        """
        Execute full Automated Approach procedure.

        Guarantees non-destructive error knife-freeze, beam blanking, and safe abort.
        """
        # Reset instance state for clean re-entrant runs (AR3-T011-002, AR3-T011-003)
        self._abort_event.clear()
        self._current_sem_rotation = None
        self.calibrations = {}
        self.step_records = []
        self.previous_frames = {}

        self._slices_cut_total = 0
        self._depth_removed_total_um = 0.0
        self._current_step_idx = 0

        if self._abort_requested:
            msg = "Approach aborted by operator before start"
            logger.info(msg)
            self._save_manifest(ApproachState.ABORTED, 0, 0.0)
            self._notify_progress(ApproachState.ABORTED, 0, 0, 0.0, 0, [], msg)
            return ApproachProgress(ApproachState.ABORTED, 0, 0, 0.0, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

        try:
            return self._run_procedure()
        except Exception as e:
            msg = "Unhandled hardware/approach exception: %s" % e
            logger.error("AutoApproachEngine: %s", msg, exc_info=True)
            self.state = ApproachState.ERROR
            self._save_manifest(ApproachState.ERROR, self._slices_cut_total, self._depth_removed_total_um)
            self._notify_progress(ApproachState.ERROR, self._current_step_idx, self._slices_cut_total, self._depth_removed_total_um, 0, [], msg)
            return ApproachProgress(
                ApproachState.ERROR, self._current_step_idx, self._slices_cut_total, self._depth_removed_total_um,
                self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg
            )
        finally:
            if hasattr(self.sem, 'set_beam_blanking'):
                try:
                    self.sem.set_beam_blanking(1)
                except Exception:
                    pass

    def _run_procedure(self) -> ApproachProgress:
        # Beam blanked during all non-acquisition intervals
        if hasattr(self.sem, 'set_beam_blanking'):
            self.sem.set_beam_blanking(1)

        timestamp_str = dt.datetime.now().strftime('%Y-%m-%d_%H%M%S')
        self.run_dir = os.path.join(self.base_dir, 'meta', 'approach', timestamp_str)
        raw_dir = os.path.join(self.run_dir, 'raw')
        overlays_dir = os.path.join(self.run_dir, 'overlays')
        try:
            os.makedirs(raw_dir, exist_ok=True)
            os.makedirs(overlays_dir, exist_ok=True)
        except Exception as e:
            msg = "AutoApproachEngine: cannot create run directory: %s" % e
            logger.error(msg)
            self._notify_progress(ApproachState.ERROR, 0, 0, 0.0, 0, [], msg)
            return ApproachProgress(ApproachState.ERROR, 0, 0, 0.0, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

        # -------------------------------------------------------------------
        # 1. Comprehensive Pre-Flight Validation Before ANY Knife/Stage Motion
        # -------------------------------------------------------------------
        self._notify_progress(
            ApproachState.CALIBRATING_BASELINE, 0, 0, 0.0, 0, [],
            "Validating system state, sample Z, EHT, and probe tiles..."
        )

        # EHT state check
        if hasattr(self.sem, 'is_eht_on') and not self.sem.is_eht_on():
            msg = "Pre-flight aborted: SEM EHT is OFF"
            logger.error(msg)
            self._save_manifest(ApproachState.PREFLIGHT_FAILED, 0, 0.0)
            self._notify_progress(ApproachState.PREFLIGHT_FAILED, 0, 0, 0.0, 0, [], msg)
            return ApproachProgress(ApproachState.PREFLIGHT_FAILED, 0, 0, 0.0, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

        # Hardware error check (AR3-T011-001: inspect microtome, stage, and SEM error states)
        microtome_err = getattr(self.microtome, 'error_state', Error.none)
        stage_err = getattr(self.stage, 'error_state', Error.none)
        sem_err = getattr(self.sem, 'error_state', Error.none)
        if microtome_err != Error.none or stage_err != Error.none or sem_err != Error.none:
            msg = "Pre-flight aborted: hardware in error state (microtome=%s, stage=%s, sem=%s)" % (
                str(microtome_err), str(stage_err), str(sem_err)
            )
            logger.error(msg)
            self._save_manifest(ApproachState.ERROR, 0, 0.0)
            self._notify_progress(ApproachState.ERROR, 0, 0, 0.0, 0, [], msg)
            return ApproachProgress(ApproachState.ERROR, 0, 0, 0.0, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

        # Sample Z nominal check
        try:
            z_pos = self.stage.get_z()
        except Exception as e:
            logger.error("AutoApproachEngine: failed to read stage Z: %s", e)
            z_pos = None

        micro_err_z = getattr(self.microtome, 'error_state', Error.none)
        stage_err_z = getattr(self.stage, 'error_state', Error.none)
        if z_pos is None or z_pos < 0.0 or micro_err_z != Error.none or stage_err_z != Error.none:
            msg = "Pre-flight aborted: sample Z-axis is in non-nominal state (Z=%s, microtome=%s, stage=%s)" % (
                str(z_pos), str(micro_err_z), str(stage_err_z)
            )
            logger.error(msg)
            self._save_manifest(ApproachState.ERROR, 0, 0.0)
            self._notify_progress(ApproachState.ERROR, 0, 0, 0.0, 0, [], msg)
            return ApproachProgress(ApproachState.ERROR, 0, 0, 0.0, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

        # Stage Z ceiling check against microtome.z_range
        z_range = getattr(self.microtome, 'z_range', None)
        if z_range is not None and len(z_range) >= 2 and z_pos > z_range[1]:
            msg = "Pre-flight aborted: stage Z (%.2f um) exceeds ceiling (%.2f um)" % (z_pos, z_range[1])
            logger.error(msg)
            self._save_manifest(ApproachState.ERROR, 0, 0.0)
            self._notify_progress(ApproachState.ERROR, 0, 0, 0.0, 0, [], msg)
            return ApproachProgress(ApproachState.ERROR, 0, 0, 0.0, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

        if not self.cfg.probe_tiles:
            msg = "Pre-flight aborted: no probe reference tiles configured"
            logger.error(msg)
            self._save_manifest(ApproachState.PREFLIGHT_FAILED, 0, 0.0)
            self._notify_progress(ApproachState.PREFLIGHT_FAILED, 0, 0, 0.0, 0, [], msg)
            return ApproachProgress(ApproachState.PREFLIGHT_FAILED, 0, 0, 0.0, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

        # Validate all probe tiles and XY stage limits before moving anything
        for tk in self.cfg.probe_tiles:
            tile_obj = self._resolve_tile(tk)
            grid_obj = self._resolve_grid(tk)
            if tile_obj is None or grid_obj is None or not getattr(grid_obj, 'active', True):
                msg = "Pre-flight aborted: probe tile '%s' is invalid or in inactive grid" % tk
                logger.error(msg)
                self._save_manifest(ApproachState.PREFLIGHT_FAILED, 0, 0.0)
                self._notify_progress(ApproachState.PREFLIGHT_FAILED, 0, 0, 0.0, 0, [], msg)
                return ApproachProgress(ApproachState.PREFLIGHT_FAILED, 0, 0, 0.0, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

            if hasattr(self.stage, 'pos_within_limits') and not self.stage.pos_within_limits(tile_obj.sx_sy):
                msg = "Pre-flight aborted: probe tile '%s' XY %s outside stage limits" % (tk, str(tile_obj.sx_sy))
                logger.error(msg)
                self._save_manifest(ApproachState.PREFLIGHT_FAILED, 0, 0.0)
                self._notify_progress(ApproachState.PREFLIGHT_FAILED, 0, 0, 0.0, 0, [], msg)
                return ApproachProgress(ApproachState.PREFLIGHT_FAILED, 0, 0, 0.0, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

        # -------------------------------------------------------------------
        # 2. Command and Verify Initial Clear Knife Before XY Stage Moves
        # -------------------------------------------------------------------
        if self._abort_requested:
            msg = "Approach stopped by operator before baseline calibration"
            logger.info(msg)
            self._save_manifest(ApproachState.ABORTED, 0, 0.0)
            self._notify_progress(ApproachState.ABORTED, 0, 0, 0.0, 0, [], msg)
            return ApproachProgress(ApproachState.ABORTED, 0, 0, 0.0, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

        self._notify_progress(
            ApproachState.CLEARING_KNIFE, 0, 0, 0.0, 0, [],
            "Clearing knife for baseline imaging..."
        )
        try:
            clear_ret = self.microtome.clear_knife()
        except Exception as e:
            logger.error("AutoApproachEngine: exception clearing knife at baseline: %s", e)
            clear_ret = False
        if (clear_ret is False) or (getattr(self.microtome, 'error_state', Error.none) != Error.none):
            msg = "Failed to clear knife during initial approach start"
            logger.error(msg)
            self._save_manifest(ApproachState.ERROR, 0, 0.0)
            self._notify_progress(ApproachState.ERROR, 0, 0, 0.0, 0, [], msg)
            return ApproachProgress(ApproachState.ERROR, 0, 0, 0.0, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

        if self._abort_requested:
            msg = "Approach stopped by operator before baseline tile acquisition"
            logger.info(msg)
            self._save_manifest(ApproachState.ABORTED, 0, 0.0)
            self._notify_progress(ApproachState.ABORTED, 0, 0, 0.0, 0, [], msg)
            return ApproachProgress(ApproachState.ABORTED, 0, 0, 0.0, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

        # -------------------------------------------------------------------
        # 3. Acquire Single Baseline Grab & Self-Calibrate Each Probe Tile
        # -------------------------------------------------------------------
        self._notify_progress(
            ApproachState.ACQUIRING_TILES, 0, 0, 0.0, 0, [],
            "Acquiring single baseline scan for probe tiles..."
        )
        baseline_evals = {}  # type: Dict[str, TileStepEvaluation]
        all_calibrations_ok = True

        for tile_key in self.cfg.probe_tiles:
            if self._abort_requested:
                msg = "Approach stopped by operator during baseline tile acquisition"
                logger.info(msg)
                self._save_manifest(ApproachState.ABORTED, 0, 0.0)
                self._notify_progress(ApproachState.ABORTED, 0, 0, 0.0, 0, [], msg)
                return ApproachProgress(ApproachState.ABORTED, 0, 0, 0.0, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

            tile_obj = self._resolve_tile(tile_key)
            grid_obj = self._resolve_grid(tile_key)
            if tile_obj is None or grid_obj is None:
                continue

            # Move XY stage
            try:
                move_ok = self.stage.move_to_xy(tile_obj.sx_sy)
            except Exception as e:
                logger.error("AutoApproachEngine: exception moving stage XY: %s", e)
                move_ok = False
            if (move_ok is False) or (getattr(self.stage, 'error_state', Error.none) != Error.none) or (getattr(self.microtome, 'error_state', Error.none) != Error.none) or (getattr(self.sem, 'error_state', Error.none) != Error.none):
                msg = "Stage XY move error for tile '%s'" % tile_key
                logger.error(msg)
                self._save_manifest(ApproachState.ERROR, 0, 0.0)
                self._notify_progress(ApproachState.ERROR, 0, 0, 0.0, 0, [], msg)
                return ApproachProgress(ApproachState.ERROR, 0, 0, 0.0, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

            if self._abort_requested:
                msg = "Approach stopped by operator during baseline tile acquisition"
                logger.info(msg)
                self._save_manifest(ApproachState.ABORTED, 0, 0.0)
                self._notify_progress(ApproachState.ABORTED, 0, 0, 0.0, 0, [], msg)
                return ApproachProgress(ApproachState.ABORTED, 0, 0, 0.0, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

            if self.stage_callback is not None:
                try:
                    self.stage_callback('XY')
                except Exception as e:
                    logger.warning("AutoApproachEngine: stage_callback('XY') error: %s", e)

            dwell = self.cfg.dwell_time_override_us if self.cfg.dwell_time_override_us > 0 else grid_obj.dwell_time
            self.sem.apply_frame_settings(grid_obj.frame_size_selector, grid_obj.pixel_size, dwell)

            # Apply scan rotation: match parent grid rotation, or 0.0 if grid is unrotated (AR3-T011-003)
            grid_rot = getattr(grid_obj, 'rotation', 0.0)
            theta_sem = (360.0 - float(grid_rot)) % 360.0
            if theta_sem > 0.0:
                self.sem.set_scan_rotation(theta_sem)
                self._current_sem_rotation = theta_sem
            elif self._current_sem_rotation is not None:
                self.sem.set_scan_rotation(0.0)
                self._current_sem_rotation = 0.0

            # Apply per-tile optics only if configured (wd > 0 sentinel)
            if getattr(tile_obj, 'wd', 0.0) > 0.0:
                if hasattr(self.sem, 'set_wd'):
                    self.sem.set_wd(tile_obj.wd)
                if hasattr(tile_obj, 'stig_xy') and hasattr(self.sem, 'set_stig_xy') and tile_obj.stig_xy is not None:
                    self.sem.set_stig_xy(*tile_obj.stig_xy)

            raw_name = "step_000_g%04d_t%04d.tif" % (int(tile_key.split('.')[0]), int(tile_key.split('.')[1]))
            raw_path = os.path.join(raw_dir, raw_name)

            # Unblank beam strictly during frame grab
            self.sem.set_beam_blanking(0)
            try:
                grab_ok = self.sem.acquire_frame(raw_path)
            except Exception as e:
                logger.error("AutoApproachEngine: exception acquiring frame: %s", e)
                grab_ok = False
            finally:
                if hasattr(self.sem, 'set_beam_blanking'):
                    try:
                        self.sem.set_beam_blanking(1)
                    except Exception:
                        pass

            if not grab_ok or not os.path.exists(raw_path) or getattr(self.sem, 'error_state', Error.none) != Error.none:
                msg = "SEM frame grab failed on tile '%s' during baseline calibration" % tile_key
                logger.error(msg)
                self._save_manifest(ApproachState.ERROR, 0, 0.0)
                self._notify_progress(ApproachState.ERROR, 0, 0, 0.0, 0, [], msg)
                return ApproachProgress(ApproachState.ERROR, 0, 0, 0.0, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

            if self._abort_requested:
                msg = "Approach stopped by operator during baseline tile acquisition"
                logger.info(msg)
                self._save_manifest(ApproachState.ABORTED, 0, 0.0)
                self._notify_progress(ApproachState.ABORTED, 0, 0, 0.0, 0, [], msg)
                return ApproachProgress(ApproachState.ABORTED, 0, 0, 0.0, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

            img = cv2.imread(raw_path, cv2.IMREAD_GRAYSCALE)
            calib = calibrate_tile_single_scan(img, grid_obj.pixel_size, self.cfg.ssim_mode, tile_key=tile_key)
            self.calibrations[tile_key] = calib

            if not calib.valid:
                all_calibrations_ok = False
            else:
                self.previous_frames[tile_key] = img

            baseline_evals[tile_key] = TileStepEvaluation(
                tile_key=tile_key,
                step_index=0,
                raw_image_path=raw_path,
                overlay_image_path=None,
                shift_yx_px=(0.0, 0.0),
                cross_ssim=1.0,
                dissimilarity=0.0,
                contact_detected=False
            )

            # Intermediate per-tile progress notification for live Viewport refresh (AC-AA-FP-016)
            partial_step0 = ApproachStepRecord(
                step_index=0,
                slices_cut_cumulative=0,
                depth_removed_um=0.0,
                z_stage_um=z_pos,
                triggered_tiles=[],
                tile_evaluations=dict(baseline_evals)
            )
            self._notify_progress(
                ApproachState.CALIBRATING_BASELINE, 0, 0, 0.0, 0, [],
                "Baseline: evaluated tile %s" % tile_key,
                step_record=partial_step0
            )

        step0_record = ApproachStepRecord(
            step_index=0,
            slices_cut_cumulative=0,
            depth_removed_um=0.0,
            z_stage_um=z_pos,
            triggered_tiles=[],
            tile_evaluations=baseline_evals
        )
        self.step_records.append(step0_record)

        if not all_calibrations_ok:
            failing = [k for k, p in self.calibrations.items() if not p.valid]
            reasons = [p.failure_reason for p in self.calibrations.values() if p.failure_reason]
            msg = "Pre-flight aborted: probe tiles failed calibration: %s (%s)" % (
                ", ".join(failing), "; ".join(reasons)
            )
            logger.error(msg)
            self._save_manifest(ApproachState.PREFLIGHT_FAILED, 0, 0.0)
            self._notify_progress(ApproachState.PREFLIGHT_FAILED, 0, 0, 0.0, 0, [], msg, step_record=step0_record)
            return ApproachProgress(ApproachState.PREFLIGHT_FAILED, 0, 0, 0.0, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

        # Baseline completed nominally
        self._save_manifest(ApproachState.EVALUATING, 0, 0.0)
        self._notify_progress(
            ApproachState.EVALUATING, 0, 0, 0.0, 0, [],
            "Baseline calibrated nominally for %d tile(s)" % len(self.cfg.probe_tiles),
            step_record=step0_record
        )

        # Integer nanometer arithmetic to prevent IEEE-754 float drift (AR3-T005-004)
        slice_thickness_nm = int(self.cfg.slice_thickness_nm)
        slice_thickness_um = float(slice_thickness_nm) / 1000.0
        max_depth_nm = int(round(self.cfg.max_depth_um * 1000.0))
        depth_removed_total_nm = 0
        slices_cut_total = 0
        step_idx = 0
        self._slices_cut_total = 0
        self._depth_removed_total_um = 0.0
        self._current_step_idx = 0

        # -------------------------------------------------------------------
        # 4. Main Batch Cutting & Approach Loop
        # -------------------------------------------------------------------
        while True:
            step_idx += 1
            self._current_step_idx = step_idx
            remaining_depth_nm = max_depth_nm - depth_removed_total_nm
            depth_removed_total_um = float(depth_removed_total_nm) / 1000.0

            # Stop when remaining depth is less than a single slice
            if remaining_depth_nm < slice_thickness_nm:
                msg = "Safety limit reached: max depth %.2f um reached without contact" % self.cfg.max_depth_um
                logger.info(msg)
                self._save_manifest(ApproachState.SAFETY_LIMIT_REACHED, slices_cut_total, depth_removed_total_um)
                self._notify_progress(ApproachState.SAFETY_LIMIT_REACHED, step_idx - 1, slices_cut_total, depth_removed_total_um, 0, [], msg)
                return ApproachProgress(ApproachState.SAFETY_LIMIT_REACHED, step_idx - 1, slices_cut_total, depth_removed_total_um, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

            if self._abort_requested:
                msg = "Approach aborted by operator before batch %d" % step_idx
                logger.info(msg)
                self._save_manifest(ApproachState.ABORTED, slices_cut_total, depth_removed_total_um)
                self._notify_progress(ApproachState.ABORTED, step_idx - 1, slices_cut_total, depth_removed_total_um, 0, [], msg)
                return ApproachProgress(ApproachState.ABORTED, step_idx - 1, slices_cut_total, depth_removed_total_um, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

            # Cap batch slice count so depth never exceeds max_depth_um
            max_slices_remaining = remaining_depth_nm // slice_thickness_nm
            batch_slice_count = min(self.cfg.batch_slices, max_slices_remaining)

            # Move knife to Near
            self._notify_progress(
                ApproachState.CUTTING_BATCH, step_idx, slices_cut_total, depth_removed_total_um,
                0, [], "Moving knife to Near for batch %d (%d slices)..." % (step_idx, batch_slice_count)
            )
            try:
                near_ret = self.microtome.near_knife()
            except Exception as e:
                logger.error("AutoApproachEngine: exception moving knife to Near: %s", e)
                near_ret = False
            if (near_ret is False) or (getattr(self.microtome, 'error_state', Error.none) != Error.none):
                msg = "Error moving knife to Near; freezing knife in place"
                logger.error(msg)
                self._save_manifest(ApproachState.ERROR, slices_cut_total, depth_removed_total_um)
                self._notify_progress(ApproachState.ERROR, step_idx, slices_cut_total, depth_removed_total_um, 0, [], msg)
                return ApproachProgress(ApproachState.ERROR, step_idx, slices_cut_total, depth_removed_total_um, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

            # Execute batch cuts in Near
            batch_interrupted_by_abort = False
            for b_i in range(1, batch_slice_count + 1):
                if self._abort_requested:
                    batch_interrupted_by_abort = True
                    break

                self._notify_progress(
                    ApproachState.CUTTING_BATCH, step_idx, slices_cut_total, depth_removed_total_um,
                    b_i, [], "Batch %d: cutting slice %d of %d..." % (step_idx, b_i, batch_slice_count)
                )

                # Move stage Z
                try:
                    curr_z = self.stage.get_z()
                    if curr_z is None or curr_z < 0.0 or getattr(self.stage, 'error_state', Error.none) != Error.none or getattr(self.microtome, 'error_state', Error.none) != Error.none:
                        move_ok = False
                    else:
                        target_z = curr_z + slice_thickness_um
                        if z_range is not None and len(z_range) >= 2 and target_z > z_range[1]:
                            move_ok = False
                        else:
                            move_ok = self.stage.move_to_z(target_z, safe_mode=True)
                except Exception as e:
                    logger.error("AutoApproachEngine: stage move_to_z exception: %s", e)
                    move_ok = False

                if (move_ok is False) or (getattr(self.stage, 'error_state', Error.none) != Error.none) or (getattr(self.microtome, 'error_state', Error.none) != Error.none):
                    msg = "Error advancing stage Z; freezing knife in place"
                    logger.error(msg)
                    self._save_manifest(ApproachState.ERROR, slices_cut_total, depth_removed_total_um)
                    self._notify_progress(ApproachState.ERROR, step_idx, slices_cut_total, depth_removed_total_um, b_i, [], msg)
                    return ApproachProgress(ApproachState.ERROR, step_idx, slices_cut_total, depth_removed_total_um, self.cfg.max_depth_um, b_i, self.cfg.batch_slices, [], self.run_dir, msg)

                # Execute approach cut (Near position)
                try:
                    cut_ok = self.microtome.do_full_approach_cut()
                except Exception as e:
                    logger.error("AutoApproachEngine: exception executing do_full_approach_cut: %s", e)
                    cut_ok = False
                if (cut_ok is False) or (getattr(self.microtome, 'error_state', Error.none) != Error.none):
                    msg = "Error executing do_full_approach_cut(); freezing knife in place"
                    logger.error(msg)
                    self._save_manifest(ApproachState.ERROR, slices_cut_total, depth_removed_total_um)
                    self._notify_progress(ApproachState.ERROR, step_idx, slices_cut_total, depth_removed_total_um, b_i, [], msg)
                    return ApproachProgress(ApproachState.ERROR, step_idx, slices_cut_total, depth_removed_total_um, self.cfg.max_depth_um, b_i, self.cfg.batch_slices, [], self.run_dir, msg)

                slices_cut_total += 1
                depth_removed_total_nm += slice_thickness_nm
                depth_removed_total_um = float(depth_removed_total_nm) / 1000.0
                self._slices_cut_total = slices_cut_total
                self._depth_removed_total_um = depth_removed_total_um

                # Notify stage callback of Z update after physical cut
                if self.stage_callback is not None:
                    try:
                        self.stage_callback('Z')
                    except Exception as e:
                        logger.warning("AutoApproachEngine: stage_callback('Z') error: %s", e)

                self._notify_progress(
                    ApproachState.CUTTING_BATCH, step_idx, slices_cut_total, depth_removed_total_um,
                    b_i, [], "Batch %d: cut %d of %d completed" % (step_idx, b_i, batch_slice_count)
                )

            # If user aborted during batch
            if batch_interrupted_by_abort or self._abort_requested:
                # Active cut has completed .ac2; clear knife cleanly
                self._notify_progress(
                    ApproachState.CLEARING_KNIFE, step_idx, slices_cut_total, depth_removed_total_um,
                    0, [], "Clearing knife after user abort..."
                )
                try:
                    clear_ret = self.microtome.clear_knife()
                except Exception as e:
                    logger.error("AutoApproachEngine: exception clearing knife on abort: %s", e)
                    clear_ret = False
                if (clear_ret is False) or (getattr(self.microtome, 'error_state', Error.none) != Error.none):
                    msg = "Error clearing knife on abort; freezing knife in place"
                    logger.error(msg)
                    self._save_manifest(ApproachState.ERROR, slices_cut_total, depth_removed_total_um)
                    self._notify_progress(ApproachState.ERROR, step_idx, slices_cut_total, depth_removed_total_um, 0, [], msg)
                    return ApproachProgress(ApproachState.ERROR, step_idx, slices_cut_total, depth_removed_total_um, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

                msg = "Approach stopped by operator after %d slices (%.2f um depth)" % (
                    slices_cut_total, depth_removed_total_um
                )
                logger.info(msg)
                self._save_manifest(ApproachState.ABORTED, slices_cut_total, depth_removed_total_um)
                self._notify_progress(ApproachState.ABORTED, step_idx, slices_cut_total, depth_removed_total_um, 0, [], msg)
                return ApproachProgress(ApproachState.ABORTED, step_idx, slices_cut_total, depth_removed_total_um, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

            # Nominal end-of-batch: Clear knife before XY stage moves
            self._notify_progress(
                ApproachState.CLEARING_KNIFE, step_idx, slices_cut_total, depth_removed_total_um,
                0, [], "Clearing knife for probe tile acquisition..."
            )
            try:
                clear_ret = self.microtome.clear_knife()
            except Exception as e:
                logger.error("AutoApproachEngine: exception clearing knife after batch: %s", e)
                clear_ret = False
            if (clear_ret is False) or (getattr(self.microtome, 'error_state', Error.none) != Error.none):
                msg = "Error clearing knife after batch %d; freezing knife in place" % step_idx
                logger.error(msg)
                self._save_manifest(ApproachState.ERROR, slices_cut_total, depth_removed_total_um)
                self._notify_progress(ApproachState.ERROR, step_idx, slices_cut_total, depth_removed_total_um, 0, [], msg)
                return ApproachProgress(ApproachState.ERROR, step_idx, slices_cut_total, depth_removed_total_um, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

            # ---------------------------------------------------------------
            # 5. Acquire Probe Tiles & Evaluate Cut Dissimilarity
            # ---------------------------------------------------------------
            if self._abort_requested:
                msg = "Approach stopped by operator before probe tile acquisition (step %d)" % step_idx
                logger.info(msg)
                self._save_manifest(ApproachState.ABORTED, slices_cut_total, depth_removed_total_um)
                self._notify_progress(ApproachState.ABORTED, step_idx, slices_cut_total, depth_removed_total_um, 0, [], msg)
                return ApproachProgress(ApproachState.ABORTED, step_idx, slices_cut_total, depth_removed_total_um, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

            self._notify_progress(
                ApproachState.ACQUIRING_TILES, step_idx, slices_cut_total, depth_removed_total_um,
                0, [], "Acquiring probe tiles for step %d..." % step_idx
            )
            step_evals = {}  # type: Dict[str, TileStepEvaluation]
            triggered_tiles = []  # type: List[str]

            for tile_key in self.cfg.probe_tiles:
                if self._abort_requested:
                    msg = "Approach stopped by operator during probe tile acquisition (step %d)" % step_idx
                    logger.info(msg)
                    self._save_manifest(ApproachState.ABORTED, slices_cut_total, depth_removed_total_um)
                    self._notify_progress(ApproachState.ABORTED, step_idx, slices_cut_total, depth_removed_total_um, 0, [], msg)
                    return ApproachProgress(ApproachState.ABORTED, step_idx, slices_cut_total, depth_removed_total_um, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

                tile_obj = self._resolve_tile(tile_key)
                grid_obj = self._resolve_grid(tile_key)
                if tile_obj is None or grid_obj is None:
                    continue

                try:
                    move_ok = self.stage.move_to_xy(tile_obj.sx_sy)
                except Exception as e:
                    logger.error("AutoApproachEngine: exception moving stage XY: %s", e)
                    move_ok = False
                if (move_ok is False) or (getattr(self.stage, 'error_state', Error.none) != Error.none) or (getattr(self.microtome, 'error_state', Error.none) != Error.none) or (getattr(self.sem, 'error_state', Error.none) != Error.none):
                    msg = "Stage XY move error for tile '%s'" % tile_key
                    logger.error(msg)
                    self._save_manifest(ApproachState.ERROR, slices_cut_total, depth_removed_total_um)
                    self._notify_progress(ApproachState.ERROR, step_idx, slices_cut_total, depth_removed_total_um, 0, [], msg)
                    return ApproachProgress(ApproachState.ERROR, step_idx, slices_cut_total, depth_removed_total_um, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

                if self._abort_requested:
                    msg = "Approach stopped by operator during probe tile acquisition (step %d)" % step_idx
                    logger.info(msg)
                    self._save_manifest(ApproachState.ABORTED, slices_cut_total, depth_removed_total_um)
                    self._notify_progress(ApproachState.ABORTED, step_idx, slices_cut_total, depth_removed_total_um, 0, [], msg)
                    return ApproachProgress(ApproachState.ABORTED, step_idx, slices_cut_total, depth_removed_total_um, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

                if self.stage_callback is not None:
                    try:
                        self.stage_callback('XY')
                    except Exception as e:
                        logger.warning("AutoApproachEngine: stage_callback('XY') error: %s", e)

                dwell = self.cfg.dwell_time_override_us if self.cfg.dwell_time_override_us > 0 else grid_obj.dwell_time
                self.sem.apply_frame_settings(grid_obj.frame_size_selector, grid_obj.pixel_size, dwell)

                # Apply scan rotation: match parent grid rotation, or 0.0 if grid is unrotated (AR3-T011-003)
                grid_rot = getattr(grid_obj, 'rotation', 0.0)
                theta_sem = (360.0 - float(grid_rot)) % 360.0
                if theta_sem > 0.0:
                    self.sem.set_scan_rotation(theta_sem)
                    self._current_sem_rotation = theta_sem
                elif self._current_sem_rotation is not None:
                    self.sem.set_scan_rotation(0.0)
                    self._current_sem_rotation = 0.0

                # Apply per-tile optics only if configured (wd > 0 sentinel)
                if getattr(tile_obj, 'wd', 0.0) > 0.0:
                    if hasattr(self.sem, 'set_wd'):
                        self.sem.set_wd(tile_obj.wd)
                    if hasattr(tile_obj, 'stig_xy') and hasattr(self.sem, 'set_stig_xy') and tile_obj.stig_xy is not None:
                        self.sem.set_stig_xy(*tile_obj.stig_xy)

                raw_name = "step_%03d_g%04d_t%04d.tif" % (
                    step_idx, int(tile_key.split('.')[0]), int(tile_key.split('.')[1])
                )
                raw_path = os.path.join(raw_dir, raw_name)

                self.sem.set_beam_blanking(0)
                try:
                    grab_ok = self.sem.acquire_frame(raw_path)
                except Exception as e:
                    logger.error("AutoApproachEngine: exception acquiring frame: %s", e)
                    grab_ok = False
                finally:
                    if hasattr(self.sem, 'set_beam_blanking'):
                        try:
                            self.sem.set_beam_blanking(1)
                        except Exception:
                            pass

                if not grab_ok or not os.path.exists(raw_path) or getattr(self.sem, 'error_state', Error.none) != Error.none:
                    msg = "SEM frame grab failed on tile '%s' during step %d" % (tile_key, step_idx)
                    logger.error(msg)
                    self._save_manifest(ApproachState.ERROR, slices_cut_total, depth_removed_total_um)
                    self._notify_progress(ApproachState.ERROR, step_idx, slices_cut_total, depth_removed_total_um, 0, [], msg)
                    return ApproachProgress(ApproachState.ERROR, step_idx, slices_cut_total, depth_removed_total_um, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

                if self._abort_requested:
                    msg = "Approach stopped by operator during probe tile acquisition (step %d)" % step_idx
                    logger.info(msg)
                    self._save_manifest(ApproachState.ABORTED, slices_cut_total, depth_removed_total_um)
                    self._notify_progress(ApproachState.ABORTED, step_idx, slices_cut_total, depth_removed_total_um, 0, [], msg)
                    return ApproachProgress(ApproachState.ABORTED, step_idx, slices_cut_total, depth_removed_total_um, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

                curr_img = cv2.imread(raw_path, cv2.IMREAD_GRAYSCALE)
                valid_step, step_err = validate_tile_frame(curr_img)
                if not valid_step or curr_img is None:
                    msg = "Invalid/corrupt frame on tile '%s' during step %d: %s" % (tile_key, step_idx, step_err)
                    logger.error(msg)
                    self._save_manifest(ApproachState.ERROR, slices_cut_total, depth_removed_total_um)
                    self._notify_progress(ApproachState.ERROR, step_idx, slices_cut_total, depth_removed_total_um, 0, [], msg)
                    return ApproachProgress(ApproachState.ERROR, step_idx, slices_cut_total, depth_removed_total_um, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

                prev_img = self.previous_frames.get(tile_key, curr_img)
                calib = self.calibrations.get(tile_key)

                if calib is None or not calib.valid:
                    cross_ssim, dissim, contact, shift_yx = 0.0, 1.0, True, (0.0, 0.0)
                else:
                    cross_ssim, dissim, contact, shift_yx = evaluate_tile_pair(
                        prev_img, curr_img, calib, self.cfg.ssim_mode, grid_obj.pixel_size
                    )

                # Render and save Cyan/Magenta overlay
                pyr_lvl = calib.pyramid_level if calib else 0
                overlay_rgb = compose_cyan_magenta_overlay(prev_img, curr_img, shift_yx, pyramid_level=pyr_lvl)
                overlay_name = "step_%03d_g%04d_t%04d_cm.png" % (
                    step_idx, int(tile_key.split('.')[0]), int(tile_key.split('.')[1])
                )
                overlay_path = os.path.join(overlays_dir, overlay_name)
                try:
                    cv2.imwrite(overlay_path, cv2.cvtColor(overlay_rgb, cv2.COLOR_RGB2BGR))
                except Exception as e:
                    logger.warning("Failed to save overlay image '%s': %s", overlay_path, e)

                # Update previous frame for next step
                self.previous_frames[tile_key] = curr_img

                if contact:
                    triggered_tiles.append(tile_key)

                step_evals[tile_key] = TileStepEvaluation(
                    tile_key=tile_key,
                    step_index=step_idx,
                    raw_image_path=raw_path,
                    overlay_image_path=overlay_path,
                    shift_yx_px=shift_yx,
                    cross_ssim=cross_ssim,
                    dissimilarity=dissim,
                    contact_detected=contact
                )

                # Intermediate per-tile progress notification for live Viewport refresh (AC-AA-FP-016)
                partial_step_rec = ApproachStepRecord(
                    step_index=step_idx,
                    slices_cut_cumulative=slices_cut_total,
                    depth_removed_um=depth_removed_total_um,
                    z_stage_um=self.stage.get_z() if hasattr(self.stage, 'get_z') else 0.0,
                    triggered_tiles=list(triggered_tiles),
                    tile_evaluations=dict(step_evals)
                )
                self._notify_progress(
                    ApproachState.EVALUATING, step_idx, slices_cut_total, depth_removed_total_um,
                    batch_slice_count, list(triggered_tiles),
                    "Step %d: evaluated tile %s (dissimilarity=%.4f)" % (step_idx, tile_key, dissim),
                    step_record=partial_step_rec
                )

            try:
                curr_z_stage = self.stage.get_z()
            except Exception as e:
                logger.error("AutoApproachEngine: failed to read stage Z at step end: %s", e)
                curr_z_stage = None

            micro_err_step = getattr(self.microtome, 'error_state', Error.none)
            stage_err_step = getattr(self.stage, 'error_state', Error.none)
            sem_err_step = getattr(self.sem, 'error_state', Error.none)
            if curr_z_stage is None or curr_z_stage < 0.0 or micro_err_step != Error.none or stage_err_step != Error.none or sem_err_step != Error.none:
                msg = "Stage Z error at end of step %d (Z=%s, microtome=%s, stage=%s, sem=%s)" % (
                    step_idx, str(curr_z_stage), str(micro_err_step), str(stage_err_step), str(sem_err_step)
                )
                logger.error(msg)
                self._save_manifest(ApproachState.ERROR, slices_cut_total, depth_removed_total_um)
                self._notify_progress(ApproachState.ERROR, step_idx, slices_cut_total, depth_removed_total_um, 0, [], msg)
                return ApproachProgress(ApproachState.ERROR, step_idx, slices_cut_total, depth_removed_total_um, self.cfg.max_depth_um, 0, self.cfg.batch_slices, [], self.run_dir, msg)

            step_rec = ApproachStepRecord(
                step_index=step_idx,
                slices_cut_cumulative=slices_cut_total,
                depth_removed_um=depth_removed_total_um,
                z_stage_um=curr_z_stage,
                triggered_tiles=triggered_tiles,
                tile_evaluations=step_evals
            )
            self.step_records.append(step_rec)

            # Check if contact detected on any probe tile
            if triggered_tiles:
                msg = "Contact detected on tile(s): %s at total depth %.2f um (%d slices)" % (
                    ", ".join(triggered_tiles), depth_removed_total_um, slices_cut_total
                )
                logger.info(msg)
                self._save_manifest(ApproachState.CONTACT_DETECTED, slices_cut_total, depth_removed_total_um)
                self._notify_progress(
                    ApproachState.CONTACT_DETECTED, step_idx, slices_cut_total, depth_removed_total_um,
                    0, triggered_tiles, msg, step_record=step_rec
                )
                return ApproachProgress(
                    ApproachState.CONTACT_DETECTED, step_idx, slices_cut_total, depth_removed_total_um,
                    self.cfg.max_depth_um, 0, self.cfg.batch_slices, triggered_tiles, self.run_dir, msg
                )

            # Step completed without contact
            self._save_manifest(ApproachState.EVALUATING, slices_cut_total, depth_removed_total_um)
            self._notify_progress(
                ApproachState.EVALUATING, step_idx, slices_cut_total, depth_removed_total_um,
                0, [], "Step %d evaluated nominally without contact" % step_idx, step_record=step_rec
            )
