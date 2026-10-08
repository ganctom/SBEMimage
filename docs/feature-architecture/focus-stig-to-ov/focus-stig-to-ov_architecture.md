# Architecture: focus-stig-to-ov (ADL)

## 1. Architectural Style & Core Invariants
- **Config-Layer Propagation**: Values are moved strictly within SBEMimage's internal state (`GridManager` -> `OverviewManager`).
- **Hardware-Deferred**: No immediate SmartSEM commands (`sem_api`) are dispatched during transfer. The SEM driver applies the state naturally during the next OV acquisition loop.
- **Fail-Safe Integrity**: Transfer is atomic per-OV. A failure while fetching WD or Stigmation must abort the transfer for that OV, leaving the existing settings untouched. Errors must be logged and caught to prevent crashing the acquisition loop.

## 2. Module Routing Table
To prevent duplicate implementations and respect existing boundaries, modifications must be strictly routed:

| Sub-Domain | Target Module | Responsibility |
|---|---|---|
| **Data Source** | `src/grid_manager.py` | Expose read accessor for the first active tile of a given grid index. Must handle out-of-bounds or empty grids safely. |
| **Data Sink & Core Logic** | `src/overview_manager.py` | Expose the single atomic transfer API. Houses the iteration logic over OVs, missing-grid fallbacks, and the AFSS guard check. |
| **Manual Trigger UI** | `src/main_controls_dlg_windows.py` & `gui/overview_settings_dlg.ui` | Bind a UI button in the OV Settings Tab (`OVSettingsDlg`) to invoke the transfer API manually. |
| **Automated Trigger UI & Logic** | `gui/autofocus_settings_dlg.ui`, `src/main_controls_dlg_windows.py`, `src/acquisition.py` | Checkbox in `AutofocusSettingsDlg` (ON by default) to set opt-in flag. Live-toggle updates in-memory config and OV metadata without SEM calls. Inject pre-OV hook in `acquisition.py`. |

## 3. Data Flow & Guard Checks
1. **Trigger**: Fired by manual user interaction, live toggle in Autofocus Settings, or the automated acquisition hook.
2. **Iteration**: Loop through all active OVs (`OV-N`).
3. **Guard Check 1 (Mapping)**: Check if `Grid-N` exists and is active. If not, silently skip `OV-N`.
4. **Guard Check 2 (Source)**: Ask `GridManager` for `Grid-N`'s first active tile. If `None` or `wd == 0`, skip `OV-N`.
5. **Guard Check 3 (AFSS Memory Fallback)**: If `Autofocus.afss_active == True` and the source tile is an AFSS reference tile, pull unperturbed base focus and stigmation from `afss_wd_stig_orig` instead of intermediate sweep values.
6. **Target Update**: Assign `[wd, stig_x, stig_y]` to the `wd_stig_xy` attribute of `OV-N`. Persist config via `save_to_cfg()`. No noisy transfer log messages emitted to GUI or disk logs.
