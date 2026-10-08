# Implementation Plan - T-002 Implement OverviewManager.apply_focus_stig_from_grids(gm) [MUTABLE]

## Metadata [MUTABLE]
- **Task ID:** T-002
- **Task Title:** Implement `OverviewManager.apply_focus_stig_from_grids(gm)`
- **Agent:** 08-implementation-engineer
- **PRD:** `prd.md`
- **ADL:** `focus-stig-to-ov_architecture.md`
- **Tasks:** `tasks.md`
- Status: Completed
- **AC IDs:** AC-FSO-003, AC-FSO-004, AC-FSO-005, AC-FSO-007

## Summary
Implement the core focus/stig propagation method on `OverviewManager` that applies 1:1 implicit mapping from each grid's first active tile to the corresponding overview, safely guarded by the AFSS sweep state and atomic error handling.

## Targets, Tests, Done When [MUTABLE]
- **Targets:** `src/overview_manager.py`
- **Tests:** `tests/test_focus_stig_to_ov.py`
- **Done when:** `~/miniforge3/envs/sbem-py37/bin/python -m pytest tests/test_focus_stig_to_ov.py` passes cleanly on all T-001 and T-002 test cases.

## Steps [MUTABLE]
- [x] T-002.1 Add unit tests for `apply_focus_stig_from_grids` in `tests/test_focus_stig_to_ov.py` covering 1:1 mapping, AFSS active block, and missing grid fallback.
- [x] T-002.2 Implement `apply_focus_stig_from_grids(self, gm, autofocus=None) -> bool` on `OverviewManager` with AFSS guard, atomic per-OV updates, and config saving.
- [x] T-002.3 Verify all tests pass with pytest.

## File Permissions
- MODIFY: `src/overview_manager.py`
- MODIFY: `tests/test_focus_stig_to_ov.py`

## Types / methods / interfaces
- `OverviewManager.apply_focus_stig_from_grids(self, gm: GridManager, autofocus: Optional[Autofocus] = None) -> bool`

## Data / contracts
- For each active OV `ov_index` in `0 <= ov_index < self.number_ov`:
  - Check if grid `ov_index` exists in `gm` and `gm[ov_index].active`. If not, skip `ov_index`.
  - Fetch first active tile `first_t = gm.get_first_active_tile_index(ov_index)`. If `None`, skip.
  - If `autofocus is not None` and getattr(autofocus, 'afss_active', False):
    - If `gm[ov_index][first_t].autofocus_active`: skip `ov_index` (guard block).
  - Fetch `res = gm.get_first_active_tile_wd_stig(ov_index)`. If `None`, skip.
  - Set `self[ov_index].wd_stig_xy = [wd, sx, sy]`.
- Call `self.save_to_cfg()`.
- Return `True` if at least one OV was updated, `False` otherwise.

## Side-effects / risks
- Safe atomic try/except prevents unhandled exceptions from propagating.
- Follows Python 3.7.6 typing conventions.

## Verification steps
- Syntax check: `~/miniforge3/envs/sbem-py37/bin/python -m py_compile src/overview_manager.py`
- Pytest: `~/miniforge3/envs/sbem-py37/bin/python -m pytest tests/test_focus_stig_to_ov.py`
