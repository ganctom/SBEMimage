# Domain Knowledge: focus-stig-to-ov

## 1. Physical / Optical Dynamics

- **Working Distance (WD)**: The distance from the pole piece to the specimen. Stored in **metres** throughout SBEMimage and the Zeiss SmartSEM API (`AP_WD`). Typical SBEM values are 3–8 mm (0.003–0.008 m).
- **Stigmation (stig_x, stig_y)**: Electrostatic corrector voltages expressed as **percentage** (%) in SBEMimage and the SmartSEM API (`AP_STIG_X`, `AP_STIG_Y`). Typical range ±1%.
- **Overview (OV)**: Low-magnification image of the block face. An `Overview` object is implemented as a subclass of `Grid` with a 1×1 tile, so it inherits the grid-level `wd_stig_xy = [wd_m, stig_x_pct, stig_y_pct]` field. Focus/stig are applied only if `wd_stig_xy[0] > 0`.
- **Tile**: High-magnification image unit within a tile-grid. Each `Tile` stores its own `tile.wd` (float, metres) and `tile.stig_xy` (list `[stig_x, stig_y]`, %).

## 2. Hardware Quirks & Timings

- **No live SEM call in transfer path**: The feature copies values entirely at the config layer (`ovm[ov_index].wd_stig_xy = [wd, sx, sy]`). The SEM driver picks them up at the next OV acquisition via `sem.set_wd()` / `sem.set_stig_xy()` called inside `acquire_ov()` / `acquire_overview()`.
- **OV focus application guard**: Both `acq_func.acquire_ov()` and `Acquisition.acquire_overview()` already gate the focus write with `if ov_wd > 0`. A transferred value of 0 would be silently ignored — the guard must ensure WD is non-zero before writing.
- **Tile WD initialization sentinel**: `tile.wd == 0` means "uninitialized." The acquisition's `__init__` calls `set_wd_stig_xy_for_uninitialized_tiles()` to fill these in from defaults. The feature must check `tile.wd > 0` before reading.

## 3. Mathematical & Algorithmic Principles

### Config-layer data structures

| Field | Owner object | Python attribute | Units |
|---|---|---|---|
| OV WD | `Overview` (via `Grid`) | `ov.wd_stig_xy[0]` | metres |
| OV StigX | `Overview` (via `Grid`) | `ov.wd_stig_xy[1]` | % |
| OV StigY | `Overview` (via `Grid`) | `ov.wd_stig_xy[2]` | % |
| Tile WD | `Tile` | `tile.wd` | metres |
| Tile StigX | `Tile` | `tile.stig_xy[0]` | % |
| Tile StigY | `Tile` | `tile.stig_xy[1]` | % |

### First active tile definition
There is **no existing "first active tile" concept** in the codebase. For this feature, define it as:
> The tile with the **lowest index** `t` such that `gm[g][t].tile_active == True`.

Implemented via:
```python
def _first_active_tile_index(grid):
    for t in range(grid.number_tiles):
        if grid[t].tile_active:
            return t
    return None
```

### AFSS guard logic and unperturbed memory fallback
The key state variable is `Autofocus.afss_active` (bool).
When `af.afss_active` is True and the first active tile of a grid is an autofocus reference tile (`tile.autofocus_active` is True), an AFSS sweep is actively evaluating different focus/stig offsets. To prevent transferring these transient trial values to the overview, the system falls back to the unperturbed baseline values stored in AFSS memory (`af.afss_wd_stig_orig[f'{g}.{t}']`), ensuring the overview remains optically stable. Once AFSS completes (`af.afss_active` returns to False) and best-fit corrections are applied, subsequent transfers copy the converged tile settings.

### AFSS fallback pseudocode
```python
first_t = _first_active_tile_index(gm[grid_index])
if first_t is None:
    return False  # no active tiles
tile = gm[grid_index][first_t]
if tile.autofocus_active and af.afss_active:
    # Use unperturbed settings stored in AFSS memory
    tile_key = f'{grid_index}.{first_t}'
    orig_wd, orig_stig = af.afss_wd_stig_orig[tile_key]
    wd, stig_xy = orig_wd[0], orig_stig
else:
    wd, stig_xy = tile.wd, tile.stig_xy
```

## 4. OV ↔ Grid Association (Open Question)

**As of the research scan, there is NO stored association between a specific OV index and a specific grid index in the SBEMimage config.** This is a design decision that must be resolved with the user before implementation (see OQ-4 in `prd.md`).

Options:
1. **Implicit by index**: OV-N is associated with Grid-N (works only if |OV| == |grid| and they're numbered consistently).
2. **Explicit config field**: Add a new config field `cfg['overviews']['ov_grid_map']` mapping OV index → grid index.
3. **User selects at trigger time**: The manual button UI lets the user choose which grid to source from.

## 5. AFSS Module Cross-Reference

| AFSS concept | Code location | Field/method |
|---|---|---|
| Sweep active | `autofocus.py` | `af.afss_active: bool` |
| Current AFSS grid | `autofocus.py` | `af.afss_grid_ind: Optional[int]` |
| Ref tiles for AFSS | `autofocus.py` | `af.afss_data['ref_tiles']` |
| Tile is AF ref | `grid_manager.py` | `tile.autofocus_active: bool` |
| AF ref tiles of a grid | `grid_manager.py` | `gm[g].autofocus_ref_tiles()` → `List[int]` |
| Series complete + fit done | `acquisition.py` | `process_afss_autofocus()` succeeded |
