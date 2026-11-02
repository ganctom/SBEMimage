# Implementation Plan - Task T-FP-017: Live Viewport Approach UI Refresh on Tile Evaluation

## 1. Metadata
- **Task ID**: `T-FP-017`
- **Parent AC**: `AC-AA-FP-016` (and `AC-SBEM-AUTO_APPROACH-009`)
- **Phase**: Phase 3: Engine & Viewport Live Event Synchronization
- **Primary Agent**: `implementation-engineer`
- **Reviewer**: `software-architect`

## 2. File Whitelists
- **MODIFY**:
  - `src/auto_approach.py`
  - `src/viewport.py`
  - `tests/test_auto_approach.py`
- **CREATE**:
  - `tests/test_viewport_approach.py`
- **FORBIDDEN**:
  - `dm/*`, `src/microtome_control*`, `src/sem_control*`, `gui/*`, `magc/*`

## 3. Objective & Requirements
During Automated Approach, as each individual reference tile finishes SEM acquisition and dissimilarity evaluation within a cutting step (or baseline step 0), the engine must immediately emit progress notification with partial step records so Viewport Approach Tab canvas, controls, and status indicators refresh in real time without waiting for remaining tiles in the step batch.

## 4. Detailed Implementation Checklist
- [ ] In `src/auto_approach.py` (`AutoApproachEngine.run_approach`):
  - In baseline calibration loop (`step 0`), after each `baseline_evals[tile_key]` is populated, dispatch `self._notify_progress()` with current partial evaluations.
  - In batch evaluation loop (`step_idx >= 1`), after each `step_evals[tile_key]` is populated, dispatch `self._notify_progress()` with current partial evaluations.
- [ ] In `src/viewport.py` (`Viewport.ap_update_live_step`):
  - Support incremental updates: if `step_record.step_index` matches the current active step in `self.ap_steps`, update/merge `tile_evaluations` in-place rather than appending duplicates.
  - Refresh `ap_tile_rects`, step info label, and trigger `self.ap_draw()`.
- [ ] In `tests/test_auto_approach.py` / `tests/test_viewport_approach.py`:
  - Add test verifying that progress callback is called $N$ times per step for $N$ reference tiles.
  - Add test verifying `ap_update_live_step` correctly merges partial evaluations and updates Viewport canvas state.

## 5. Verification & Pass Criteria
- Syntax: `python -m py_compile src/auto_approach.py src/viewport.py` (Zero errors under Python 3.7.6).
- Tests: `python agent_test.py tests/test_auto_approach.py` passes 100% with zero regressions.
