# Implementation Plan - Task T-FP-021: Stable Multi-Tile Grid Allocation Across Live Approach Steps

## 1. Metadata
- **Task ID**: `T-FP-021`
- **Parent AC**: `AC-AA-FP-016` (and `AC-SBEM-AUTO_APPROACH-009`)
- **Phase**: Phase 3: Viewport Multi-Tile Layout Stability
- **Primary Agent**: `implementation-engineer`
- **Reviewer**: `software-architect`

## 2. File Whitelists
- **MODIFY**:
  - `src/viewport.py`
  - `src/main_controls.py`
  - `src/main_controls_dlg_windows.py`
  - `docs/feature-architecture/auto-approach-contact-fp/tasks.md`
  - `tests/test_viewport_approach.py`
- **FORBIDDEN**:
  - `dm/*`, `src/microtome_control*`, `src/sem_control*`, `magc/*`

## 3. Objective & Requirements
When automated approach starts, the Viewport Approach Tab must immediately allocate a fixed multi-tile grid layout for all intended reference tiles. As individual tiles finish acquisition and evaluation within a step, the canvas must not collapse to a single tile or re-flow between 1, 2, 3... tiles. For any tile pending evaluation in the current step, it must display the latest available image from the prior step (or a waiting placeholder) with a "Waiting..." badge.

## 4. Detailed Implementation Checklist
- [ ] In `src/viewport.py`:
  - Implement `ap_get_all_probe_tiles(self)`: returns canonically sorted list (e.g. `0.0, 0.1, 0.2`) combining `gm.approach_ref_tiles`, `ap_configured_tiles`, `ap_calibrations`, and tiles across all steps in `ap_steps`.
  - Implement `ap_start_live_run(self, ref_tiles)`: sets `ap_configured_tiles`, resets run state cleanly, and immediately triggers `ap_draw()` to display the initial multi-tile grid structure.
  - In `ap_draw()`:
    - Base grid dimensions (`cols`, `rows`, `cell_w`, `cell_h`) on all probe tiles (`self.ap_get_all_probe_tiles()`), NOT just the currently finished tiles in `current_step_record`.
    - For pending tiles not yet evaluated in `current_step_record`:
      - Retrieve latest available image from previous steps ($k-1$ down to 0) if available, and render with registered shift.
      - If no prior image exists (Step 0 before first scan), render dark placeholder with "Waiting for acquisition...".
      - Render header badge with "Tile {key} | Step {step_idx} | Waiting...".
- [ ] In `src/main_controls_dlg_windows.py` & `src/main_controls.py`:
  - When starting auto approach, transmit `('START APPROACH RUN', list(ref_tiles))` to notify Viewport immediately.
- [ ] In `tests/test_viewport_approach.py`:
  - Test verifying `ap_draw()` keeps fixed grid layout when only a subset of tiles has completed in the current step.
  - Test verifying pending tiles display previous step image or waiting placeholder.
  - Test verifying `ap_start_live_run` allocates the grid immediately upon start.

## 5. Verification & Pass Criteria
- Syntax: `python -m py_compile src/viewport.py src/main_controls.py src/main_controls_dlg_windows.py` (Zero errors under Python 3.7.6).
- Tests: `python -m pytest tests/test_viewport_approach.py` passes 100% with zero regressions.
