# Implementation Plan - T-001 Implement GridManager.get_first_active_tile_wd_stig(grid_index) [MUTABLE]

## Metadata [MUTABLE]
- **Task ID:** T-001
- **Task Title:** Implement `GridManager.get_first_active_tile_wd_stig(grid_index)`
- **Agent:** 08-implementation-engineer
- **PRD:** `prd.md`
- **ADL:** `focus-stig-to-ov_architecture.md`
- **Tasks:** `tasks.md`
- Status: Completed
- **AC IDs:** AC-FSO-003, AC-FSO-006

## Summary
Implement a method on `GridManager` to retrieve the WD, Stig X, and Stig Y from the first active tile of a specified grid index, returning `None` if the grid does not exist, has no active tiles, or has uninitialized focus parameters (`wd <= 0`).

## Targets, Tests, Done When [MUTABLE]
- **Targets:** `src/grid_manager.py`
- **Tests:** `tests/test_focus_stig_to_ov.py`
- **Done when:** `~/miniforge3/envs/sbem-py37/bin/python -m pytest tests/test_focus_stig_to_ov.py -k test_get_first_active_tile` passes cleanly on Python 3.7.6.

## Steps [MUTABLE]
- [x] T-001.1 Create `tests/test_focus_stig_to_ov.py` with unit tests for `get_first_active_tile_wd_stig`.
- [x] T-001.2 Add `get_first_active_tile_wd_stig(self, grid_index: int) -> Optional[Tuple[float, Tuple[float, float]]]` in `src/grid_manager.py`.
- [x] T-001.3 Run pre-flight syntax check and test execution to verify all tests pass.

## File Permissions
- CREATE: `tests/test_focus_stig_to_ov.py`
- MODIFY: `src/grid_manager.py`

## Types / methods / interfaces
- `GridManager.get_first_active_tile_index(self, grid_index: int) -> Optional[int]`: Returns the lowest integer index `t` such that tile `t` is active in grid `grid_index`, or `None`.
- `GridManager.get_first_active_tile_wd_stig(self, grid_index: int) -> Optional[Tuple[float, Tuple[float, float]]]`: Returns `(wd, (stig_x, stig_y))` if grid exists, has active tile, and `wd > 0`. Otherwise returns `None`.

## Data / contracts
- WD is in metres (`float`).
- Stig is a 2-tuple or list of floats `(stig_x, stig_y)` in %.
- If `grid_index < 0` or `grid_index >= self.number_grids` or grid is inactive: returns `None`.
- If no active tile exists: returns `None`.
- If `tile.wd <= 0`: returns `None`.

## Side-effects / risks
- Strictly additive read method on `GridManager`. No state mutations or config saves.
- Python 3.7.6 typing constraints (`typing.Optional`, `typing.Tuple`).

## Verification steps
- Syntax check: `~/miniforge3/envs/sbem-py37/bin/python -m py_compile src/grid_manager.py`
- Unit tests: `~/miniforge3/envs/sbem-py37/bin/python -m pytest tests/test_focus_stig_to_ov.py -k test_get_first_active_tile`
