# PRD: feat/focus-stig-to-ov

## 1. System Objective

SBEMimage is a serial block-face SEM (SBEM) acquisition platform designed for months-long uninterrupted runs. During a nominal acquisition, focus and stigmation are handled **automatically** — each tile in each tile-grid can have its own independently stored WD and stig values, found and applied by one of several autofocus methods (AFSS, heuristic, SmartSEM AF, WD gradient, etc.).

The OV (overview image) images the block face at low magnification at regular intervals. It has its own independently stored `wd_stig_xy` settings. If those settings differ significantly from the tile-grid beam conditions, the SEM optics suffer from **hysteresis, beam drift, and other instabilities** that degrade SEM image fidelity — a critical concern for connectomics research where ultimate resolution and contrast are required.

**Goal**: Provide a mechanism to **propagate stored WD (working distance) and stigmation XY values from the first active tile of a tile-grid to the associated OV's internal SBEMimage config**, so the OV images with beam settings consistent with the tile-grid acquisition conditions. This is a **config-layer copy** (no live SmartSEM interaction at transfer time); SBEMimage propagates the updated OV WD/stig to the SEM before the next OV frame is acquired, as it already does for all other OV/tile settings.

### Business Value
- Keeps OV beam settings close to tile-grid beam conditions, minimising optics hysteresis and drift between OV and tile acquisitions.
- Ensures OV images are sharply focused and correctly stigmated, supporting slice-by-slice quality control.
- Reduces operator burden: the OV no longer needs to be manually re-focused when tile focus/stig values evolve over a long acquisition run.

---

## 2. Hard Constraints

- **Target Runtime**: Python 3.7.6 (x86_64 Rosetta / Conda `sbem-py37`).
  - NO walrus operator (`:=`).
  - NO PEP 585 generics (`list[str]`); use `typing.List[str]`.
  - NO PEP 604 unions (`int | None`); use `typing.Optional[int]` or `typing.Union`.
  - NO f-strings with `=` (`f"{var=}"`).
- **Config-layer only**: The transfer path must NOT call `sem_api` write methods. The OV settings are written to the SBEMimage internal config; the SEM driver picks them up at the next OV acquisition.
- **AFSS guard**: Transfer must use unperturbed base values while an AFSS sweep is in progress for the reference tile (see AC-FSO-004).
- **Missing-value guard**: If the first active tile has no stored WD or stig, the OV config must remain unchanged (see AC-FSO-005).
- **Fail-Safe Integrity**: On any exception during transfer, log the error and leave OV config unchanged. Never partially write (update WD but not stig, or vice versa).

---

## 3. In-Scope Boundaries

### Files to Modify
| File | Change |
|---|---|
| `src/overview_manager.py` | `apply_focus_stig_from_grids(grid_manager, autofocus)` method for `OverviewManager` |
| `src/main_controls_dlg_windows.py` | Add manual button in `OVSettingsDlg` and move auto-checkbox logic to `AutofocusSettingsDlg` |
| `gui/overview_settings_dlg.ui` | Add the manual trigger button |
| `gui/autofocus_settings_dlg.ui` | Add the auto-trigger checkbox (under 'Tracking mode') |
| `gui/acq_settings_dlg.ui` | Remove the previously added auto-trigger checkbox |
| `src/acquisition.py` | Add acquisition-time call to `apply_focus_stig_from_grids` when checkbox is set, guarded by AFSS state |
| `src/grid_manager.py` | Expose read-only accessor for first active tile's WD + stig |

### Behavioral Scope
- Per-OV/grid-pair logic: if N OVs each have an associated grid, each OV is updated from its own grid's first active tile.
- Both manual (button) and automatic (acquisition-time checkbox in Autofocus settings) triggers.
- Checkbox supports live toggling during dataset acquisition: immediately updates OV metadata when turned ON without hitting SEM hardware.
- Read stored WD + stig from tile config only (no live SEM measurement).
- Write to OV internal config only (no live SmartSEM write).

---

## 4. Anti-Targets

- Do not refactor legacy PyQt GUI code outside the OV settings tab touch point.
- Do not introduce dependencies unsupported by Python 3.7.6.
- Do not modify the AFSS algorithm or autofocus sweep logic.
- Do not copy any other beam/optics parameters beyond WD and stig XY.
- Do not add live SmartSEM API calls in the transfer path.
- Do not modify the tile-grid focus/stig values as a side effect of this feature.
- Do not implement interpolation or surface fitting — direct config copy only.

---

## 5. Acceptance Criteria

### AC-FSO-001: Successful manual transfer (happy path)
```gherkin
Given  the first active tile of a grid has stored WD = W and stig = (Sx, Sy)
And    the associated OV currently has different WD and stig values
When   the user clicks the "Copy focus/stig to OV" button in the OV settings tab
Then   the OV's internal config WD is updated to W
And    the OV's internal config stig X is updated to Sx
And    the OV's internal config stig Y is updated to Sy
And    no live sem_api write is triggered
And    a log entry is written confirming the transfer
```

### AC-FSO-002: Acquisition-time automatic transfer
```gherkin
Given  the auto-transfer checkbox in the Autofocus/Tracking Settings dialog is ON (default state)
And    the first active tile has stored WD = W and stig = (Sx, Sy)
And    AFSS is not active or in-between AFSS sweep-run
When   SBEMimage begins a new acquisition cycle and prepares to image the OV
Then   the OV's internal config WD and stig are updated from the first active tile
       before the OV acquires its frame
And    the OV then images with the updated settings
```

### AC-FSO-008: Live activation/deactivation during ongoing acquisition
```gherkin
Given  an ongoing dataset acquisition is running in the background
When   the user toggles the "Sync OV focus/stig from grids before OV acq." checkbox in Autofocus Settings
Then   the in-memory configuration `sync_focus_stig_from_grids` is immediately updated
And    if toggled ON, the OV WD/Stig metadata is immediately updated in memory from the grid's first active tile
And    no physical WD/Stig command is sent to the SEM microscope
And    no message regarding propagation of WD/Stig values is shown in the Main controls log window or SBEMimage.log
And    a message logging the user action (activation or deactivation) is recorded in SBEMimage.log
And    the next scheduled OV acquisition uses the newly updated OV WD/Stig metadata
```

### AC-FSO-003: Implicit 1:1 mapping with fallback skip
```gherkin
Given  multiple OVs exist (e.g., OV-0, OV-1)
And    Grid-0 exists and is active, but Grid-1 does not exist
When   the focus/stig transfer is triggered (manual or automatic)
Then   OV-0's config is updated from Grid-0's first active tile
And    OV-1's config remains unchanged (no matching grid found)
And    no exception is raised for OV-1
```

### AC-FSO-004: AFSS active guard — transfer unperturbed values
```gherkin
Given  the first active tile of a grid is designated as the autofocus reference tile
And    the autofocus method is AFSS
And    the AFSS sweep is currently in progress (has not finished)
When   a transfer is triggered
Then   the OV config is updated using the unperturbed WD and stig values stored in AFSS memory
```

### AC-FSO-005: AFSS finished — allow transfer
```gherkin
Given  the first active tile is the AFSS reference tile
And    the AFSS sweep has finished successfully
And    the autofocus tracking correction has been applied to tile configs
When   a transfer is triggered
Then   the updated WD and stig values are transferred to OV
```

### AC-FSO-006: Missing values guard
```gherkin
Given  the first active tile of a grid has no stored WD or no stored stig values or thre is no active tile in the grid
When   a transfer is triggered (manual or automatic)
Then   the OV config remains unchanged
And    no exception is raised
```

### AC-FSO-007: Atomic write guard
```gherkin
Given  any exception occurs during the config write
When   the transfer is attempted
Then   either both WD and stig are updated, or neither is updated
And    the exception is caught, logged, and does not propagate to the caller
```

---

## 6. Architectural Discussion & Design

- **Top-Down Specification**: `OverviewManager.apply_focus_stig_from_grid(grid_index: int) -> bool` is the single callable API for both the manual and automatic triggers. Returns `True` if transfer succeeded, `False` if skipped.
- **Deep Interface**: All guard logic (AFSS state, missing values, atomic write) lives inside `OverviewManager`. Callers (GUI button, acquisition loop) see a single method with a bool result — they do not re-implement guards.
- **AFSS State** *(resolved)*: `af.afss_active: bool` in `autofocus.py` indicates a sweep in progress. Per-tile autofocus ref status is `tile.autofocus_active`. See `knowledge.md` §3 for full guard pseudocode.
- **Config Storage** *(resolved)*: Tile WD/stig → `tile.wd` (m) + `tile.stig_xy` ([sx, sy], %). OV WD/stig → `ovm[ov_index].wd_stig_xy = [wd, sx, sy]`, persisted via `ovm.save_to_cfg()`. See `knowledge.md` §3.

---

## 7. Open Questions (resolved by codebase research)

| # | Question | Status | Answer |
|---|---|---|---|
| OQ-1 | Tile WD and stig XY config keys | ✅ Resolved | `tile.wd` (float, m); `tile.stig_xy` ([sx, sy], %) on each `Tile` object in `GridManager` |
| OQ-2 | OV WD and stig setter | ✅ Resolved | `ovm[ov_index].wd_stig_xy = [wd, sx, sy]` — direct attribute assignment. Persisted via `ovm.save_to_cfg()` |
| OQ-3 | "First active tile" determination | ✅ Resolved | No existing method. Define as: lowest index `t` where `gm[g][t].tile_active == True`. New helper needed. |
| OQ-4 | OV ↔ Grid association | ✅ Resolved | **Implicit 1:1 mapping by index** (Option A). OV `N` always sources from Grid `N`. If Grid `N` does not exist or has no active tiles, OV `N` is silently skipped and retains its current settings. |
| OQ-5 | AFSS "sweep in progress" flag | ✅ Resolved | `af.afss_active: bool` in `Autofocus`. Also check `tile.autofocus_active` on the first active tile. |
| OQ-6 | Autofocus reference tile flag | ✅ Resolved | `tile.autofocus_active: bool` per `Tile`; list via `gm[g].autofocus_ref_tiles()` → `List[int]`. |
