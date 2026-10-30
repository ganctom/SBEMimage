# Implementation Plan - T-005 Qt-Free Core Engine, Single-Scan Self-Calibration, Bounded Registration, Dual SSIM, and Cyan/Magenta Compositor [MUTABLE]

## Metadata [MUTABLE]
- **Task ID:** T-005
- **Task Title:** Implement Qt-Free Core Engine, Single-Scan Odd/Even Pyramidal Self-Calibration, Bounded Registration, Dual SSIM Modes, and Cyan/Magenta Compositor in `src/auto_approach.py`
- **Agent:** `implementation-engineer`
- **PRD:** `1-prd.md`
- **ADL:** `2-adl.md`
- **Tasks:** `5-tasks.md`
- **AC IDs:** `AC-SBEM-AUTO_APPROACH-001`, `AC-SBEM-AUTO_APPROACH-002`, `AC-SBEM-AUTO_APPROACH-005`, `AC-SBEM-AUTO_APPROACH-007`
- Status: Completed

## Summary
Implement the pure-Python (Qt-free) algorithmic core and complete state-machine hardware engine in `src/auto_approach.py` using NumPy, SciPy, OpenCV, and scikit-image under strict Python 3.7.6 constraints. Implements odd/even raster scan-line pyramid self-calibration on lattice $y = 2r + 1.5$, stage-jitter bounded subpixel registration, dual SSIM modes (`Normalized SSIM` and `Gradient SSIM`), contrast-matched Cyan/Magenta overlay rendering, `AutoApproachEngine` with non-destructive knife safety & on-disk run archive persistence, and comprehensive unit tests in `tests/test_auto_approach.py`.

## Targets, Tests, Done When [MUTABLE]
- **Targets:** `src/auto_approach.py`
- **Tests:** `tests/test_auto_approach.py`
- **Done when:** `~/miniforge3/envs/sbem-py37/bin/python agent_test.py tests/test_auto_approach.py` passes with zero errors; centroid coincidence, pyramid selection, pre-flight rejection (including None/empty), bounded jitter registration, 100% shave safety, dose-drift invariance, Cyan/Magenta compositing, and mock-based `AutoApproachEngine` tests (nominal-Z gate, batch capping, error knife-freeze, abort Clear-after-stroke-down, scan rotation preservation, callback exception isolation, and manifest persistence) are green.

## Steps [MUTABLE]
- [x] T-005.1 **[implementation-engineer]** Define typed domain enumerations, contracts, and data structures in `src/auto_approach.py` matching `4-data-model.md` (`ApproachState`, `SSIMMode`, `AutoApproachConfig` with `from_cfg()` / `to_cfg()`, `TileCalibrationProfile`, `TileStepEvaluation`, `ApproachStepRecord`, `ApproachProgress`, `ProgressCallback`).
- [x] T-005.2 **[implementation-engineer]** Implement bounded-shift subpixel registration `register_and_crop(prev_img, curr_img, pixel_size_nm, pyramid_level)` extracting shifts from `phase_cross_correlation(..., upsample_factor=10)[0]` on uniform `np.float64` arrays, clamped to $s_{\max} = \max(2, \min(\lceil 5.0\,\mu\text{m} / (\text{px\_nm} \cdot 2^{l^*}) \rceil, \lfloor 0.15 \cdot \min(H, W) \rfloor))$ with zero-shift correlation-collapse fallback.
- [x] T-005.3 **[implementation-engineer]** Implement dual SSIM evaluators `evaluate_ssim(prev_crop, curr_crop, ssim_mode, prev_std=None)` (Mode 0: z-score with smooth-resin guard $\max(\sigma_V, 0.25 \cdot \sigma_U)$; Mode 1: Sobel gradient normalized by 99th percentile) and `evaluate_tile_pair(prev_img, curr_img, calib_profile, ssim_mode, pixel_size_nm)` returning `(cross_ssim, dissimilarity, contact_detected, shift_yx_px)` per 1-prd.md:89.
- [x] T-005.4 **[implementation-engineer]** Implement pre-flight tile validator `validate_tile_frame(img: Optional[np.ndarray]) -> Tuple[bool, Optional[str]]` (handling None/empty/blank/saturated/flat images) and single-scan odd/even raster scan-line self-calibration `calibrate_tile_single_scan(img, pixel_size_nm, ssim_mode, tile_key='')` on lattice $y = 2r + 1.5$ ($\tilde{E}_0[r] = \frac{1}{4}E_0[r] + \frac{3}{4}E_0[r+1]$, $\tilde{O}_0[r] = \frac{3}{4}O_0[r] + \frac{1}{4}O_0[r+1]$), $2\times$ block-averaging pyramid downsampling, and automatic optimal scale $l^*$, noise floor $d_{\text{noise}}$, and trigger threshold $d_{\text{trigger}}$ selection.
- [x] T-005.5 **[implementation-engineer]** Implement contrast-matched Cyan/Magenta overlay compositor `compose_cyan_magenta_overlay(prev_img, curr_img, shift_yx, pyramid_level=0, scale_to_width=1024)` with robust scale floor bounding `curr_img` dispersion against `prev_img` ($\text{scale}_{\text{curr}} = \max(\text{iqr}_{\text{curr}}, 0.25 \cdot \text{scale}_{\text{prev}}, 1.0)$) to prevent divide-by-zero or false magenta on smooth resin, $2^{l^*}$ shift scaling, and RGB array output (using `cv2.cvtColor(..., cv2.COLOR_RGB2BGR)` when persisting to disk).
- [x] T-005.6 **[implementation-engineer]** Implement full `AutoApproachEngine(sem, microtome, stage, grid_manager, cfg, base_dir, progress_callback=None)`:
  - Nominal-Z pre-flight check ($Z \ge 0$, no `Error.mismatch_z`, within `microtome.z_range`; checking both `microtome.error_state` and `stage.error_state`);
  - Verified initial `clear_knife()` before XY stage motion;
  - Beam blanking during all Z/cutting/XY intervals;
  - Batch cutting in `Near` with `.ac2` checks and final batch capped at `max_depth_um`;
  - Verified `clear_knife()` after nominal batch cuts;
  - Error knife-freeze: zero `clear_knife()` calls if any hardware call returns `False` or sets `error_state != Error.none`;
  - User `request_abort()`: halt scheduling further cuts, wait for active cut `.ac2` deactivation, then verify `clear_knife()`;
  - Scan-rotation preservation (never call `set_scan_rotation(0)`);
  - On-disk run archive persistence (`raw/step_000_*.tif`, `overlays/step_001_*_cm.png`, and `manifest.json` written before `progress_callback`);
  - Callback exception isolation wrapping `progress_callback(progress, step_record)` in try/except.
- [x] T-005.7 **[implementation-engineer]** Implement unit test suite in `tests/test_auto_approach.py` covering:
  - Centroid coincidence ($< 10^{-9}\,\text{px}$) and equal variance $\frac{5}{8}$;
  - Pyramid scale selection across noise levels;
  - Pre-flight rejection of None, blank, saturated, and featureless noise frames;
  - Bounded jitter recovery and 100% shave correlation-collapse safety;
  - Dual SSIM modes and dose-drift invariance;
  - Smooth-resin `prev_std` clamping;
  - Cyan/Magenta overlay channel invariants, shifted $l^* \ge 1$ scaling, and robust IQR scale flooring;
  - Mock-based `AutoApproachEngine` tests covering AC-001 (contact stop, scan rotation preserved), AC-002 (nominal-Z gate, zero knife move on non-nominal Z, initial Clear), AC-005 (max depth cap/stop, zero `clear_knife()` on error, abort Clear-after-stroke-down), and callback exception isolation.
- [x] T-005.8 **[implementation-engineer]** Run bytecode pre-flight check (`~/miniforge3/envs/sbem-py37/bin/python -m py_compile src/auto_approach.py tests/test_auto_approach.py`) and verify green test suite via `~/miniforge3/envs/sbem-py37/bin/python agent_test.py tests/test_auto_approach.py`.
- [x] T-005.9 **[implementation-engineer]** Update `docs/feature-architecture/auto-approach/5-tasks.md` to mark T-005 complete in Dependencies graph.

## File Permissions
- CREATE: `src/auto_approach.py`
- CREATE: `tests/test_auto_approach.py`
- MODIFY: `docs/feature-architecture/auto-approach/5-tasks.md`
- MODIFY: `.gitignore`

## Types / methods / interfaces
- `src/auto_approach.py`:
  - `class ApproachState: ...`
  - `class SSIMMode: ...`
  - `class AutoApproachConfig(NamedTuple):`
    - `from_cfg(d: Dict[str, Any]) -> 'AutoApproachConfig'`
    - `to_cfg() -> Dict[str, str]`
  - `class TileCalibrationProfile(NamedTuple): ...`
  - `class TileStepEvaluation(NamedTuple): ...`
  - `class ApproachStepRecord(NamedTuple): ...`
  - `class ApproachProgress(NamedTuple): ...`
  - `validate_tile_frame(img: Optional[np.ndarray]) -> Tuple[bool, Optional[str]]`
  - `calibrate_tile_single_scan(img: Optional[np.ndarray], pixel_size_nm: float, ssim_mode: int, tile_key: str = '') -> TileCalibrationProfile`
  - `register_and_crop(prev_img: np.ndarray, curr_img: np.ndarray, pixel_size_nm: float, pyramid_level: int) -> Tuple[np.ndarray, np.ndarray, Tuple[float, float]]`
  - `evaluate_ssim(prev_crop: np.ndarray, curr_crop: np.ndarray, ssim_mode: int, prev_std: Optional[float] = None) -> float`
  - `evaluate_tile_pair(prev_img: np.ndarray, curr_img: np.ndarray, calib_profile: TileCalibrationProfile, ssim_mode: int, pixel_size_nm: float) -> Tuple[float, float, bool, Tuple[float, float]]`
  - `compose_cyan_magenta_overlay(prev_img: np.ndarray, curr_img: np.ndarray, shift_yx: Tuple[float, float], pyramid_level: int = 0, scale_to_width: int = 1024) -> np.ndarray`
  - `class AutoApproachEngine(object):`
    - `def __init__(self, sem, microtome, stage, grid_manager, cfg: AutoApproachConfig, base_dir: str, progress_callback: Optional[ProgressCallback] = None) -> None`
    - `def run(self) -> ApproachProgress`
    - `def request_abort(self) -> None`

## Data / contracts
- Strictly Python 3.7.6 typing (`typing.NamedTuple`, `typing.List`, `typing.Optional`, `typing.Tuple`, `typing.Callable`, `typing.Dict`).
- Zero imports of `PyQt5` or `QObject` inside `src/auto_approach.py` (AD-AUTO_APPROACH-001).
- Single-scan odd/even row vertical interpolation on lattice $y = 2r + 1.5$ yielding exact centroid coincidence and variance $\frac{5}{8}$ (architecture §2.1).
- Import conventions: top-level intra-src imports (`from utils import Error`, not `from src.utils`; `Trigger` inherits `QObject` and belongs strictly in `ApproachDlg`, never in `src/auto_approach.py`).
- Hardware compatibility & real API call contracts:
  - Treat microtome knife/cut calls as failed iff `(ret is False) or (microtome.error_state != Error.none)`.
  - Read sample Z via `stage.get_z()` (or `microtome.get_stage_z()`); read travel limits from `microtome.z_range`; step Z via `stage.move_to_z(target_z, safe_mode=True)` (never `stage.z_position` or `set_stage_z`).
  - Move XY stage via `stage.move_to_xy(tile.sx_sy)`.
  - Tile acquisition: `sem.apply_frame_settings(grid.frame_size_selector, grid.pixel_size, dwell_time)`, `sem.set_scan_rotation(grid.rotation)` (plus non-zero `wd`/`stig_xy`), and `sem.acquire_frame(raw_path) -> bool` followed by `cv2.imread(raw_path, cv2.IMREAD_GRAYSCALE)`.
  - Test doubles in `tests/test_auto_approach.py` implement these exact signatures (`MockSEM.acquire_frame(save_path_filename, extra_delay=0) -> bool` writes `.tif` to disk; `MockStage.get_z()`, `move_to_z()`, `move_to_xy()`).
  - Resolve probe tiles from `cfg.probe_tiles` via `grid_manager[g][t]`.
  - Extract shift from `skimage.registration.phase_cross_correlation(...)[0]` on float64 arrays.
  - Convert RGB to BGR (`cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR)`) before `cv2.imwrite`.

## Side-effects / risks
- High-noise fast scanning (`0.1 µs`) mitigated by automatic pyramid scale selection $l^* \in [0, L_{\max}]$.
- Correlation collapse on 100% shaved block face mitigated by bounded jitter clamp $s_{\max} = \max(2, \min(...))$ and zero-shift fallback.
- Flat shaved resin median/IQR collapse mitigated by `scale_curr = max(iqr_curr, 0.25 * scale_prev, 1.0)`.

## Verification steps
- Syntax check: `~/miniforge3/envs/sbem-py37/bin/python -m py_compile src/auto_approach.py tests/test_auto_approach.py`
- Run pytest suite: `~/miniforge3/envs/sbem-py37/bin/python agent_test.py tests/test_auto_approach.py`
