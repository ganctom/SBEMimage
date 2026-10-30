# Implementation Plan - T-011 Fail-Safe Guards & Manifest Persistence [MUTABLE]

## Metadata [MUTABLE]
- **Task ID:** T-011
- **Task Title:** Add Fail-Safe Guards (Nominal-Z Pre-Clear Check, Error Knife-Freeze, Abort `Clear`-After-Stroke-Down, Scan-Rotation Preservation, Beam Blanking, App Exit Prompt) & Structured `meta/approach/<timestamp>/manifest.json` Persistence
- **Agent:** `crosscutting-engineer`
- **PRD:** `1-prd.md`
- **ADL:** `2-adl.md`
- **Tasks:** `5-tasks.md`
- **AC IDs:** `AC-SBEM-AUTO_APPROACH-002`, `AC-SBEM-AUTO_APPROACH-004`, `AC-SBEM-AUTO_APPROACH-005`, `AC-SBEM-AUTO_APPROACH-007`
- Status: Completed

## Summary
Harden the automated approach pipeline with comprehensive fail-safe crosscutting safety guards and complete canonical archive persistence:
1. **Nominal-Z Pre-Clear Verification (`AC-SBEM-AUTO_APPROACH-002`):**
   - Before ANY knife movement or XY stage motion, inspect stage Z readout (`stage.get_z()`).
   - If $Z < 0.0$, $Z > \text{ceiling}$ (`microtome.z_range[1]`), or hardware is in error state (`error_state != Error.none`), abort immediately with terminal state `ERROR` without issuing any `clear_knife()` or motion commands.
2. **Error Knife-Freeze Guarantee (`AC-SBEM-AUTO_APPROACH-002`, `AC-SBEM-AUTO_APPROACH-005`):**
   - Strictly guarantee that when ANY error occurs (stage Z error, cut execution failure, stage XY move failure, comms failure, or SEM grab failure), execution terminates immediately and **zero `clear_knife()` commands are issued** to prevent dragging the knife backward across the sample face when sample height or knife position is uncertain.
3. **Safe Abort `Clear`-After-Stroke-Down (`AC-SBEM-AUTO_APPROACH-002`, `AC-SBEM-AUTO_APPROACH-005`):**
   - Thread-safe abort signaling backed by `threading.Event()`.
   - When operator aborts during a batch cut, allow the active `do_full_approach_cut()` to complete its `.ac2` handshake (guaranteeing Stroke-Down has lowered the sample below cutting plane), and only then execute a verified `clear_knife()`. If the active cut returns an error, enforce Error Knife-Freeze (zero Clear).
   - Abort check during tile acquisition (AR2-T011-002): At the start of Section 5 before probe tile acquisition and inside `for tile_key in self.cfg.probe_tiles:`, check `self._abort_requested`. If abort was signaled, break immediately, skip remaining XY moves / frame grabs, and return `ApproachState.ABORTED` (saving manifest with `ApproachState.ABORTED`), keeping the knife safely in Clear.
4. **Scan-Rotation Preservation (`AC-SBEM-AUTO_APPROACH-004`):**
   - Grid scan rotation is applied only when the parent grid defines a non-zero rotation; scan rotation is NEVER forcibly reset to 0 upon run start, run end, error, or operator abort.
5. **Beam Blanking Guarantee (`AC-SBEM-AUTO_APPROACH-004`):**
   - SEM beam is blanked (`sem.set_beam_blanking(1)`) throughout all cutting, stage motion, and idling intervals; beam is unblanked (`sem.set_beam_blanking(0)`) strictly within `try...finally` surrounding frame grab.
6. **Application Exit Guard (AR2-T011-001):**
   - In `MainControls.closeEvent`, place the automated approach check as a top-level guard clause before `elif not self.busy:` (immediately following the configuration error check at line 2725). If `self.approach_dlg is not None and getattr(self.approach_dlg, 'auto_approach_in_progress', False)`, display explicit modal warning `QMessageBox.warning(self, 'Approach in progress', 'An automated approach run is currently in progress. Please abort or wait for the approach run to complete before closing SBEMimage.', QMessageBox.Ok)` and `event.ignore()` without falling through to generic 'Program busy'.
7. **Canonical Manifest & Archive Persistence (`AC-SBEM-AUTO_APPROACH-007`, AR2-T011-003):**
   - Format `manifest.json` under `<base_dir>/meta/approach/<timestamp>/` storing `timestamp`, `terminal_state`, `total_slices_cut`, `total_depth_removed_um`, `config`, `calibrations`, and `steps` list.
   - Convert all image paths to relative paths with null safety and Windows separator normalization (`os.path.relpath(path, self.run_dir).replace('\\', '/') if path else None`), ensuring archival portability across Windows microscope hosts and POSIX analysis environments.

## User-Facing Changes
- In `MainControls`: Attempting to close the application while an automated approach run is actively executing shows a modal safety warning: *"An automated approach run is currently in progress. Please abort or wait for the approach run to complete before closing SBEMimage."*
- Full run logs and serialized metrics are saved to `meta/approach/<timestamp>/manifest.json` on disk with normalized relative paths, replayable in Viewport.

## File Whitelist (AR2-T011-004, AR2-T011-005)
- MODIFY: `src/auto_approach.py`
- MODIFY: `src/main_controls.py`
- MODIFY: `docs/feature-architecture/auto-approach/verification.md`
- MODIFY: `tests/test_auto_approach.py`
- MODIFY: `docs/feature-architecture/auto-approach/5-tasks.md`
- MODIFY: `docs/feature-architecture/auto-approach/6-plan-T011.md`

## Steps [MUTABLE]
- [x] T-011.1 **[crosscutting-engineer]** Harden `AutoApproachEngine` in `src/auto_approach.py`:
  - Upgrade `self._abort_event = threading.Event()` with property `_abort_requested` querying `self._abort_event.is_set()` for thread-safe signaling.
  - In Section 5, add explicit abort checks before and during `for tile_key in self.cfg.probe_tiles:`, immediately halting tile acquisition and returning `ApproachState.ABORTED` with knife remaining in Clear (AR2-T011-002).
  - Audit and guarantee Nominal-Z pre-clear verification before any knife or stage move.
  - Audit all error branches ensuring zero `clear_knife()` calls on any error (cut failure, Z move failure, XY failure, SEM failure).
  - Verify abort logic executes `clear_knife()` strictly after `.ac2` verified cut completion.
  - Verify beam blanking (`set_beam_blanking(1)` during cutting/motion, `0` only inside `try...finally` frame acquisition).
  - Ensure scan rotation is never reset to 0.
  - In `_save_manifest`: store normalized POSIX relative paths (`os.path.relpath(path, self.run_dir).replace('\\', '/') if path else None`) with null safety for `overlay_image_path` on Step 0 (AR2-T011-003).
- [x] T-011.2 **[crosscutting-engineer]** Update `MainControls.closeEvent` in `src/main_controls.py` (AR2-T011-001):
  - Place top-level guard clause before `elif not self.busy:` (immediately after configuration error check at line 2725).
  - If `self.approach_dlg is not None and getattr(self.approach_dlg, 'auto_approach_in_progress', False)`: display `QMessageBox.warning(self, 'Approach in progress', 'An automated approach run is currently in progress. Please abort or wait for the approach run to complete before closing SBEMimage.', QMessageBox.Ok)` and `event.ignore(); return`.
- [x] T-011.3 **[crosscutting-engineer]** Add comprehensive verification unit tests in `tests/test_auto_approach.py` matching `verification.md §1.4.6` (AR2-T011-004):
  - `test_engine_initial_nominal_z_gate`: asserts zero knife/stage moves if $Z < 0$ or $Z > \text{ceiling}$ or hardware in error state; commands and verifies `clear_knife()` before XY moves when Z is nominal.
  - `test_engine_nominal_batch_run_and_max_depth_stop`: asserts nominal 5-slice batch execution and capped final batch slice count when `max_depth_um` is reached without contact, terminating in `SAFETY_LIMIT_REACHED`.
  - `test_engine_error_knife_freeze_invariant`: asserts zero `clear_knife()` calls when cut, Z, or grab throws or returns False across all failure points.
  - `test_engine_user_abort_clear_after_stroke_down_invariant`: asserts active cut finishes `.ac2` before `clear_knife()`; error during abort prevents `clear_knife()`; abort during probe tile grab cleanly halts acquisition (AR2-T011-002).
  - `test_engine_scan_rotation_preservation_invariant`: asserts scan rotation is applied only for rotated grids and is never reset to 0 on any terminal state.
  - `test_engine_beam_blanking_transitions`: asserts beam blanked during batch cuts/motion and unblanked only during `acquire_frame()`.
  - `test_engine_manifest_json_persistence`: asserts `manifest.json` schema matches `4-data-model.md §5` with normalized relative paths (AR2-T011-003).
  - `test_main_controls_app_exit_guard_during_approach`: asserts `MainControls.closeEvent` blocks exit with modal warning when approach run is active (AR2-T011-001).
  - Update `docs/feature-architecture/auto-approach/verification.md` §1.4.6/§1.4.7 to record `test_main_controls_app_exit_guard_during_approach`.
- [x] T-011.4 **[crosscutting-engineer]** Run bytecode pre-flight check (`python -m py_compile src/auto_approach.py src/main_controls.py tests/test_auto_approach.py`) and test suite via `python agent_test.py tests/test_auto_approach.py`.
- [x] T-011.5 **[crosscutting-engineer]** Update `docs/feature-architecture/auto-approach/5-tasks.md` and set `Status: Completed` in `6-plan-T011.md:11`.

## Types / methods / interfaces
- `src/auto_approach.py`:
  - `AutoApproachEngine._abort_event: threading.Event`
  - `AutoApproachEngine.request_abort(self) -> None`
  - `AutoApproachEngine._abort_requested: bool` (property querying `_abort_event.is_set()`)
  - `AutoApproachEngine._save_manifest(self, terminal_state: str, total_slices: int, total_depth_um: float) -> None`
- `src/main_controls.py`:
  - `MainControls.closeEvent(self, event: QCloseEvent) -> None`

## Data / contracts
- Manifest Schema (`meta/approach/<timestamp>/manifest.json`):
  ```json
  {
    "timestamp": "YYYY-MM-DD HH:MM:SS",
    "terminal_state": "CONTACT_DETECTED | SAFETY_LIMIT_REACHED | PREFLIGHT_FAILED | ABORTED | ERROR",
    "total_slices_cut": 10,
    "total_depth_removed_um": 1.0,
    "config": { ... },
    "calibrations": { "0.0": { ... } },
    "steps": [
      {
        "step_index": 0,
        "slices_cut_cumulative": 0,
        "depth_removed_um": 0.0,
        "z_stage_um": 10.0,
        "triggered_tiles": [],
        "tile_evaluations": {
          "0.0": {
            "step_index": 0,
            "raw_image_path": "raw/step_000_g0000_t0000.tif",
            "overlay_image_path": null,
            "shift_yx_px": [0.0, 0.0],
            "cross_ssim": 1.0,
            "dissimilarity": 0.0,
            "contact_detected": false
          }
        }
      }
    ]
  }
  ```

## Side-effects / risks
- Potential deadlock if abort requested during blocking cut: Gatan 3View cuts complete in ~1-2 seconds; abort handler allows the single current cut to complete its handshake so hardware state remains known and synchronized before issuing Clear.
- Exit interception blocking user in hung state: Operator can always click Abort first; once idle, normal exit flow proceeds.
