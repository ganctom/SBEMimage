# Implementation Plan - Task T-FP-022: Asynchronous Stage Movement Between Approach Reference Tiles

## 1. Metadata
- **Task ID**: `T-FP-022`
- **Parent AC**: `AC-AA-FP-018` (and `AC-SBEM-AUTO_APPROACH-011`)
- **Phase**: Phase 3: Stage Concurrency & Settling Optimization
- **Primary Agent**: `implementation-engineer`
- **Reviewer**: `software-architect`

## 2. File Whitelists
- **MODIFY**:
  - `src/auto_approach.py`
  - `tests/test_auto_approach.py`
  - `docs/auto_approach_help.md`
  - `docs/feature-architecture/auto-approach-contact-fp/tasks.md`
- **FORBIDDEN**:
  - `dm/*`, `src/microtome_control*`, `src/sem_control*`, `magc/*`

## 3. Objective & Requirements
During automated sample approach with 2+ reference tiles:
1. Immediately upon completing SEM frame acquisition of tile $i$, trigger the stage movement to tile $i+1$ asynchronously in a background worker thread.
2. Simultaneously on the engine thread, execute tile $i$'s image processing pipeline (validation, phase cross-correlation, SSIM/Pearson dissimilarity evaluation, overlay generation, and live Viewport notification).
3. Prior to acquiring tile $i+1$, join the background stage move thread, verify hardware status (`move_ok`, `stage.error_state == Error.none`), and ensure stage settling requirements are satisfied.
4. For non-overlapped moves (e.g. moving to Tile 0 at step start without background processing), maintain the stage driver settling pause (`stage_move_wait_interval`).
5. Ensure zero stage movement occurs during microtome cutting arm sweeps.
6. Support clean error and abort handling (joining in-flight move threads before shutdown and blanking the beam).

## 4. Detailed Implementation Checklist
- [ ] In `src/auto_approach.py`:
  - Implement an asynchronous stage move manager/helper in `AutoApproachEngine` (e.g., using a background thread and completion event / state container) to dispatch `stage.move_to_xy(tile_coords)` and capture errors/exceptions.
  - In `run()` Step 0 (baseline calibration):
    - Dispatch async move to tile $i+1$ immediately after tile $i$ SEM frame acquisition completes (and beam is blanked).
    - Execute `calibrate_tile_single_scan()` and baseline processing for tile $i$.
    - Await and verify completion of async move to tile $i+1$ before configuring SEM optics and triggering frame grab.
  - In `run()` Step $k$ ($k \ge 1$ cutting steps):
    - Move to tile 0 after knife cut finishes and retracts (with standard `stage_move_wait_interval` settling).
    - For each tile $i$ in `self.cfg.probe_tiles`:
      - After frame grab of tile $i$ completes (beam blanked), dispatch async move to tile $i+1$ if $i < N - 1$.
      - Execute image processing on tile $i$ (validation, registration, dissimilarity evaluation, overlay save, progress callback).
      - Before acquiring tile $i+1$, join and verify the async stage move to tile $i+1$.
    - Ensure abort during async move joins the thread and safely parks/halts.
- [ ] In `tests/test_auto_approach.py`:
  - Unit test verifying stage move to tile $i+1$ overlaps with image processing of tile $i$.
  - Unit test verifying stage error in async move halts engine with `ApproachState.ERROR`.
  - Unit test verifying user abort during async move joins cleanly and stops approach.
  - Unit test verifying single-tile setup operates synchronously without regressions.
- [ ] In `docs/auto_approach_help.md`:
  - Document asynchronous stage movement and drift suppression in section 3 & 4.
- [ ] In `docs/feature-architecture/auto-approach-contact-fp/tasks.md`:
  - Record task status and completion criteria.

## 5. Verification & Pass Criteria
- Syntax: `python -m py_compile src/auto_approach.py tests/test_auto_approach.py` (Zero errors under Python 3.7.6).
- Tests: `python -m pytest tests/test_auto_approach.py` passes 100% with zero regressions across air runs and benchmarks.
