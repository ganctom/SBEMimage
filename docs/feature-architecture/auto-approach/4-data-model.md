# Auto-Approach - Data Model & Contracts [IMMUTABLE]

## Metadata [IMMUTABLE]
- **PRD:** `1-prd.md`
- **ADL:** `2-adl.md`
- **Slice:** `docs/feature-architecture/auto-approach/`

## Python 3.7.6 Typing Invariant
All modules MUST use `typing.List`, `typing.Optional`, `typing.Tuple`, `typing.Dict`, and `typing.NamedTuple` (zero PEP 585/604 syntax).

---

## 1. Domain Enumerations & Constants

```python
class ApproachState:
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


class SSIMMode:
    NORMALIZED = 0  # Z-score normalized whole-tile SSIM at calibrated pyramid scale
    GRADIENT = 1    # Spatial-gradient magnitude whole-tile SSIM at calibrated pyramid scale
```

---

## 2. Configuration Contract (`[approach]` in `default.ini`)

```python
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple


class AutoApproachConfig(NamedTuple):
    mode: int                          # Last-used ApproachDlg tab index: 0 = Manual, 1 = Automated (default 0)
    slice_thickness_nm: int            # Cut thickness per slice (nm), range [5, 200], default 100
    batch_slices: int                  # Slices per batch in Near before imaging, range [1, 100], default 5
    max_depth_um: float                # Hard Z-travel safety ceiling (um), range [0.5, 200.0], default 20.0
    probe_tiles: List[str]             # Validated 'g.t' keys, e.g. ['0.0', '0.4']
    dwell_time_override_us: float      # -1.0 = inherit parent grid dwell_time; >0 = explicit us override
    ssim_mode: int                     # SSIMMode.NORMALIZED (0) or SSIMMode.GRADIENT (1)
```

### `[approach]` key ↔ `AutoApproachConfig` field mapping (1:1, 7 keys ↔ 7 fields)

| `default.ini` key | Field | Parse / serialize |
|---|---|---|
| `mode` | `mode` | `int` ↔ `str(int)`; mirrors `ApproachDlg` `QTabWidget.currentIndex()` |
| `slice_thickness` | `slice_thickness_nm` | `int` (nm) |
| `batch_slices` | `batch_slices` | `int` |
| `max_depth_um` | `max_depth_um` | `float` |
| `probe_tiles` | `probe_tiles` | `json.loads` ↔ `json.dumps` of `List[str]` |
| `dwell_time_override` | `dwell_time_override_us` | `float` (µs; `-1.0` = inherit) |
| `ssim_mode` | `ssim_mode` | `int` (`SSIMMode`) |

Round-trip invariant: `from_cfg(to_cfg(c)) == c` for every valid `AutoApproachConfig`.

### `default.ini` Section Schema (`CFG_NUMBER_SECTIONS = 13`, `CFG_NUMBER_KEYS = 254`)
```ini
[approach]
mode = 0
slice_thickness = 100
batch_slices = 5
max_depth_um = 20.0
probe_tiles = []
dwell_time_override = -1.0
ssim_mode = 0
```

---

## 3. Per-Tile Single-Scan Calibration Contract

```python
class TileCalibrationProfile(NamedTuple):
    tile_key: str                      # 'g.t'
    valid: bool                        # True iff non-blank, non-saturated, and internal SNR converged
    pyramid_level: int                 # Selected 2x pyramid scale l* in [0, L_max]
    internal_ssim: float               # Odd/even raster scan-line SSIM at scale l*
    noise_dissimilarity: float         # d_noise = 1.0 - internal_ssim
    cut_dissimilarity_limit: float     # Self-calibrated cut trigger boundary d_trigger > d_noise
    max_shift_px: int                  # Physical stage-wander clamp at pyramid scale l*
    failure_reason: Optional[str]      # Populated when valid is False (pre-flight abort message)
```

---

## 4. Per-Step Evaluation & Series Manifest Contracts

```python
class TileStepEvaluation(NamedTuple):
    tile_key: str
    step_index: int                    # 0 = baseline, >= 1 = after batch k
    raw_image_path: str                # Saved grayscale frame in meta/approach/<timestamp>/
    overlay_image_path: Optional[str]  # Saved contrast-matched Cyan/Magenta PNG (None for step 0)
    shift_yx_px: Tuple[float, float]   # Bounded subpixel shift (dy, dx) at pyramid scale l*
    cross_ssim: float                  # Registered SSIM(I_{k-1}, I_k) at scale l* (1.0 at step 0)
    dissimilarity: float               # 1.0 - cross_ssim (0.0 at step 0)
    contact_detected: bool             # True iff dissimilarity >= cut_dissimilarity_limit


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
```

---

## 5. On-Disk Archive Schema (`<base_dir>/meta/approach/<YYYY-MM-DD_HHMMSS>/`)
- `manifest.json`: Run config, per-tile `TileCalibrationProfile`s, ordered `ApproachStepRecord` list, final terminal state, and total depth removed — consumed directly by the Viewport `Approach` tab (`ap_`) for both live updates and historical run loading.
- `raw/step_000_g0000_t0000.tif`: Raw acquired probe frames (`step_000` = single baseline scan).
- `overlays/step_001_g0000_t0000_cm.png`: Contrast-matched Cyan/Magenta composite images for fast mouse-wheel series scrubbing in the Viewport `Approach` tab.


---

## 6. Engine Interface & Qt-Free Progress Contract (`src/auto_approach.py`)

`AutoApproachEngine` MUST NOT import PyQt5 or inherit `QObject` (AD-AUTO_APPROACH-001). Progress is reported through a plain Python callback; the GUI bridges it to Qt.

```python
ProgressCallback = Callable[[ApproachProgress, Optional[ApproachStepRecord]], None]


class AutoApproachEngine(object):
    def __init__(self,
                 sem,                       # SEM / SEM_Mock instance
                 microtome,                 # Microtome_3View / Microtome_Mock instance
                 stage,                     # Stage instance
                 grid_manager,              # GridManager instance
                 cfg: AutoApproachConfig,
                 base_dir: str,
                 progress_callback: Optional[ProgressCallback] = None) -> None: ...

    def run(self) -> ApproachProgress:
        """Blocking. Executes the full state machine (architecture §3) and returns the
        terminal ApproachProgress (state in {CONTACT_DETECTED, SAFETY_LIMIT_REACHED,
        PREFLIGHT_FAILED, ABORTED, ERROR}). Intended to run on a worker thread.
        Never raises for hardware/SEM errors: they map to state ERROR (knife frozen)."""

    def request_abort(self) -> None:
        """Thread-safe (backed by threading.Event). Prevents scheduling further cuts;
        the abort sequence of AD-AUTO_APPROACH-008 §3 runs on the worker thread."""
```

**Callback semantics:**
- Called **on the engine's worker thread** after every state transition (`step_record = None`) and after every completed step evaluation, including step 0 baseline (`step_record` populated, artifacts already written to `run_dir`).
- Callback exceptions are caught and logged by the engine; they never alter the run state or knife handling.
- `progress_callback = None` is valid (headless tests, scripted runs).

**GUI bridge (T-009):** `ApproachDlg` passes a callback that only does `self.progress_trigger.queue.put((progress, step_record))` and `self.progress_trigger.signal.emit()` (existing `utils.Trigger` pattern already used by `ApproachDlg`). The Qt slot drains the queue on the main thread, updates the dialog, and forwards to the Viewport `Approach` tab (`ap_` refresh). No Qt object is touched from the worker thread.
