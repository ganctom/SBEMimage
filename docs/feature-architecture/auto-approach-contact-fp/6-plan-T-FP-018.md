# Implementation Plan - Task T-FP-018: Subpixel Registered Tile Series Display in Approach Tab

## 1. Metadata
- **Task ID**: `T-FP-018`
- **Parent AC**: `AC-AA-FP-017` (and `AC-SBEM-AUTO_APPROACH-010`)
- **Phase**: Phase 3: Viewport Series Registration & Alignment Rendering
- **Primary Agent**: `implementation-engineer`
- **Reviewer**: `software-architect`

## 2. File Whitelists
- **MODIFY**:
  - `src/viewport.py`
  - `tests/test_viewport_approach.py`
- **FORBIDDEN**:
  - `dm/*`, `src/microtome_control*`, `src/sem_control*`, `src/auto_approach.py`, `magc/*`

## 3. Objective & Requirements
When the operator scrolls through approach cutting steps using the mouse wheel or step slider in the Approach Tab, every image series (across both Raw and Cyan/Magenta modes) must be presented in a translationally registered form anchored to the baseline (Step 0) coordinate frame. This eliminates mechanical stage drift, beam wander, and jumpiness, isolating genuine physical cut changes.

## 4. Detailed Implementation Checklist
- [ ] In `src/viewport.py`:
  - Implement helper `ap_get_cumulative_shift(tile_key, step_idx)`:
    - Sums `shift_yx_px` vectors from Step 1 up to `step_idx` for the given `tile_key` to obtain global displacement relative to Step 0:
      $$\Delta y_{\text{cum}} = \sum_{j=1}^{\text{step}} \Delta y_j,\quad \Delta x_{\text{cum}} = \sum_{j=1}^{\text{step}} \Delta x_j$$
  - In `ap_draw()`:
    - When rendering Raw images (`self.ap_raw_mode == True` or `step_idx == 0`):
      - If `step_idx == 0`: render baseline directly.
      - If `step_idx > 0`: shift raw pixel frame by $(-\Delta y_{\text{cum}}, -\Delta x_{\text{cum}})$ via fast subpixel translation / QTransform or `scipy.ndimage.shift`, caching rendered aligned pixmaps to ensure 60fps wheel scrubbing performance.
    - When rendering Cyan/Magenta overlays (`self.ap_raw_mode == False`):
      - Shift the overlay pixmap by the cumulative shift of Step $k-1$ (the previous reference frame) so the overlay remains anchored to the exact same Step 0 global spatial coordinates.
- [ ] In `tests/test_viewport_approach.py`:
  - Unit test verifying `ap_get_cumulative_shift` accumulates pairwise step shifts correctly.
  - Unit test verifying that scrubbing through steps applies shift offsets to pixmaps without crashing or memory leaks.

## 5. Verification & Pass Criteria
- Syntax: `python -m py_compile src/viewport.py` (Zero errors under Python 3.7.6).
- Tests: `python agent_test.py tests/test_viewport_approach.py` passes cleanly.
