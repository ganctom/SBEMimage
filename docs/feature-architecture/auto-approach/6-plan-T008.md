# Implementation Plan - T-008 Approach Configuration & GridManager Reference Tiles [MUTABLE]

## Metadata [MUTABLE]
- **Task ID:** T-008
- **Task Title:** Add `[approach]` Section to `src/default_cfg/default.ini`, Update `CFG_NUMBER_SECTIONS = 13` / `CFG_NUMBER_KEYS = 254` in `src/config_template.py`, and Add `approach_ref_tiles` Support in `src/grid_manager.py`
- **Agent:** `implementation-engineer`
- **PRD:** `1-prd.md`
- **ADL:** `2-adl.md`
- **Tasks:** `5-tasks.md`
- **AC IDs:** `AC-SBEM-AUTO_APPROACH-003`, `AC-SBEM-AUTO_APPROACH-008`
- Status: Completed

## Summary
Implement configuration schema persistence for automated approach and bidirectional reference tile synchronization in `GridManager`:
1. `src/default_cfg/default.ini`: Add `[approach]` section with exactly 7 keys (`mode = 0`, `slice_thickness = 100`, `batch_slices = 5`, `max_depth_um = 20.0`, `probe_tiles = []`, `dwell_time_override = -1.0`, `ssim_mode = 0`).
2. `src/config_template.py`: Coupled constants update: `CFG_NUMBER_SECTIONS = 13` and `CFG_NUMBER_KEYS = 254` (satisfying GEMINI configuration management invariants; `system.cfg` constants unchanged at 8 sections, 56 keys).
3. `src/grid_manager.py`:
   - `Tile`: Add `approach_active: bool = False` flag to `Tile.__init__`, defaulting to `False`.
   - `Grid`: Add `@property def approach_ref_tiles(self) -> List[int]` returning indices of tiles with `approach_active == True`.
   - `GridManager.__init__`: Load `probe_tiles` from `self.cfg['approach']` if present (safe against legacy configs without `[approach]`) and set `approach_active = True` on matching tiles.
   - `GridManager.save_to_cfg()`: Auto-vivify `[approach]` section if missing (`if not self.cfg.has_section('approach'): self.cfg.add_section('approach')`, AR2-T008-001); save `self.approach_ref_tiles` as JSON string into `self.cfg['approach']['probe_tiles']`; and include `approach_active` tiles with non-zero WD when recording `wd_stig_params`.
   - `GridManager`: Add `@property def approach_ref_tiles(self) -> List[str]`, `@approach_ref_tiles.setter def approach_ref_tiles(self, new_ref_tiles: List[str])` with robust bounds and format checking (AR2-T008-004), and `delete_all_approach_ref_tiles(self)`. (Conforming to AD-AUTO_APPROACH-009, no arbitrary preset extraction method is added, AR2-T008-003).
4. Unit tests in `tests/test_auto_approach.py` (§1.4.4):
   - `test_config_counts_and_process_cfg()`: Validate `check_number_of_entries` on default configs, verify `process_cfg` upgrades a legacy config without `[approach]`, and verify round-trip serialization of `AutoApproachConfig`.
   - `test_grid_manager_approach_ref_tiles_sync()`: Validate bidirectional `approach_active` tile toggling, property getter/setter with out-of-bounds/malformed key safety (AR2-T008-004), `save_to_cfg()` persistence with auto-vivification and WD filtering (AR2-T008-001, AR2-T008-002), and parent grid scan parameters inheritance.

## Targets, Tests, Done When [MUTABLE]
- **Targets:** `src/default_cfg/default.ini`, `src/config_template.py`, `src/grid_manager.py`
- **Tests:** `tests/test_auto_approach.py`
- **Done when:** `~/miniforge3/envs/sbem-py37/bin/python agent_test.py tests/test_auto_approach.py` passes with zero errors; `check_number_of_entries()` succeeds asserting `CFG_NUMBER_SECTIONS = 13` and `CFG_NUMBER_KEYS = 254` for `default.ini`, and 8 sections / 56 keys for `system.cfg`; `process_cfg()` migrates legacy configurations cleanly; `GridManager.approach_ref_tiles` properly synchronizes `approach_active` state on `Tile` instances; and `save_to_cfg()` correctly serializes `probe_tiles` and `wd_stig_params`.

## Steps [MUTABLE]
- [x] T-008.1 **[implementation-engineer]** Append `[approach]` section with 7 keys (`mode`, `slice_thickness`, `batch_slices`, `max_depth_um`, `probe_tiles`, `dwell_time_override`, `ssim_mode`) to `src/default_cfg/default.ini`.
- [x] T-008.2 **[implementation-engineer]** Update configuration entry count constants in `src/config_template.py`: set `CFG_NUMBER_SECTIONS = 13` and `CFG_NUMBER_KEYS = 254`.
- [x] T-008.3 **[implementation-engineer]** Update `Tile.__init__` in `src/grid_manager.py` to accept `approach_active=False` and set `self.approach_active = approach_active`.
- [x] T-008.4 **[implementation-engineer]** Add `@property def approach_ref_tiles(self) -> List[int]` to `Grid` class in `src/grid_manager.py` returning list of tile indices in grid where `approach_active == True`.
- [x] T-008.5 **[implementation-engineer]** In `GridManager.__init__` (`src/grid_manager.py`), load `self._approach_ref_tiles` from `self.cfg['approach']['probe_tiles']` (safely guarding against missing section/key), and set `self.__grids[g][t].approach_active = True` for matching tiles.
- [x] T-008.6 **[implementation-engineer]** In `GridManager.save_to_cfg` (`src/grid_manager.py`), ensure `self.cfg.has_section('approach')` is verified (creating it via `self.cfg.add_section('approach')` if missing, AR2-T008-001), write `self.cfg['approach']['probe_tiles'] = json.dumps(self.approach_ref_tiles)`, and ensure tiles with `approach_active == True` and non-zero WD are included in `wd_stig_params`.
- [x] T-008.7 **[implementation-engineer]** Add approach reference tile management methods to `GridManager` (`src/grid_manager.py`):
  - `delete_all_approach_ref_tiles(self)`: Clears `approach_active` across all grids and tiles.
  - `@property def approach_ref_tiles(self) -> List[str]`: Collects list of `'g.t'` keys where `approach_active == True`.
  - `@approach_ref_tiles.setter def approach_ref_tiles(self, new_ref_tiles: List[str])`: Clears previous selection via `delete_all_approach_ref_tiles()`, parses each key safely with `try/except (ValueError, TypeError, AttributeError)`, validates grid index `0 <= g < self.number_grids` and tile index `0 <= t < self.__grids[g].number_tiles`, and sets `self.__grids[g][t].approach_active = True` while ignoring invalid/out-of-bounds keys without crashing (AR2-T008-004). (No `get_first_and_last_active_tiles` method is added per AD-AUTO_APPROACH-009, AR2-T008-003).
- [x] T-008.8 **[implementation-engineer]** Add unit tests in `tests/test_auto_approach.py` (§1.4.4):
  - `test_config_counts_and_process_cfg()` asserting `check_number_of_entries` on `default.ini` (13 sections, 254 keys) and `system.cfg` (8 sections, 56 keys), legacy config migration via `process_cfg`, and `AutoApproachConfig` round-trip.
  - `test_grid_manager_approach_ref_tiles_sync()` asserting:
    - `Tile.approach_active` updates `GridManager.approach_ref_tiles`;
    - `approach_ref_tiles` setter updates `Tile` states and safely handles malformed/out-of-bounds keys (`'0.999'`, `'invalid'`, `'99.0'`) without crashing (AR2-T008-004);
    - `GridManager.save_to_cfg()` creates missing `[approach]` section if omitted, serializes `probe_tiles`, includes `approach_active` tiles with non-zero WD in `wd_stig_params`, and excludes tiles with `wd=0` (AR2-T008-001, AR2-T008-002);
    - Grid scan parameter resolution (frame size, pixel size, rotation, WD/stig).
- [x] T-008.9 **[implementation-engineer]** Run bytecode pre-flight check (`~/miniforge3/envs/sbem-py37/bin/python -m py_compile src/config_template.py src/grid_manager.py tests/test_auto_approach.py`) and verify green test suite via `~/miniforge3/envs/sbem-py37/bin/python agent_test.py tests/test_auto_approach.py`.
- [x] T-008.10 **[implementation-engineer]** Update `docs/feature-architecture/auto-approach/5-tasks.md` to mark `[x]` in the `Dependencies` table, update line 36 to `*Status: Completed*`, and set `Status: Completed` in `6-plan-T008.md:11`.

## File Permissions
- MODIFY: `src/default_cfg/default.ini`
- MODIFY: `src/config_template.py`
- MODIFY: `src/grid_manager.py`
- MODIFY: `tests/test_auto_approach.py`
- MODIFY: `docs/feature-architecture/auto-approach/5-tasks.md`
- MODIFY: `docs/feature-architecture/auto-approach/6-plan-T008.md`

## Types / methods / interfaces
- `src/grid_manager.py`:
  - `Tile.__init__(..., approach_active: bool = False)`
  - `Grid.approach_ref_tiles -> List[int]`
  - `GridManager.delete_all_approach_ref_tiles() -> None`
  - `GridManager.approach_ref_tiles -> List[str]` (getter and setter)
- `src/config_template.py`:
  - `CFG_NUMBER_SECTIONS = 13`
  - `CFG_NUMBER_KEYS = 254`

## Data / contracts
- Configuration Management Coupling:
  - `[approach]` section in `src/default_cfg/default.ini`:
    - `mode = 0`
    - `slice_thickness = 100`
    - `batch_slices = 5`
    - `max_depth_um = 20.0`
    - `probe_tiles = []`
    - `dwell_time_override = -1.0`
    - `ssim_mode = 0`
  - Entry count validation: `check_number_of_entries(default_cfg, False)` must return `True` for 13 sections, 254 keys.
  - Backward compatibility: `process_cfg()` called on any legacy config file lacking `[approach]` must populate the default section and keys without raising exceptions.
- Reference tile key convention: `'g.t'` where `g` is grid index (int >= 0) and `t` is tile index in grid (int >= 0).
- Auto-vivification on save: `save_to_cfg()` checks `if not self.cfg.has_section('approach'): self.cfg.add_section('approach')` before assigning `probe_tiles`.
- Safe tile key validation: `approach_ref_tiles.setter` validates formatting and grid/tile index bounds (`0 <= g < self.number_grids and 0 <= t < self.__grids[g].number_tiles`), ignoring invalid keys without throwing exceptions.
- Python 3.7.6 compatibility: zero walrus operator `:=`, zero PEP 585 generics (`typing.List` only), zero PEP 604 unions.

## Side-effects / risks
- Modifying `default.ini` without matching `CFG_NUMBER_SECTIONS` / `CFG_NUMBER_KEYS` would cause startup crashes during `process_cfg()`. Both files are modified and tested simultaneously.
- Legacy session configurations must parse cleanly without requiring existing users to manually edit `.ini` files.
