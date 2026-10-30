# Implementation Plan - T-006 Unit Test Plan & Doubles Specification [MUTABLE]

## Metadata [MUTABLE]
- **Task ID:** T-006
- **Task Title:** Unit Test Plan & Doubles Specification in `verification.md`
- **Agent:** `unit-test-planner`
- **PRD:** `1-prd.md`
- **ADL:** `2-adl.md`
- **Tasks:** `5-tasks.md`
- **AC IDs:** `AC-SBEM-AUTO_APPROACH-001`, `AC-SBEM-AUTO_APPROACH-002`, `AC-SBEM-AUTO_APPROACH-003`, `AC-SBEM-AUTO_APPROACH-004`, `AC-SBEM-AUTO_APPROACH-005`, `AC-SBEM-AUTO_APPROACH-006`, `AC-SBEM-AUTO_APPROACH-007`, `AC-SBEM-AUTO_APPROACH-008`
- Status: Completed

## Summary
Define the comprehensive unit and hardware-mocked integration test architecture for `tests/test_auto_approach.py` in `verification.md` §1.4. Specifies deterministic test doubles, synthetic SEM image generators, exact test assertions, and 1:1 AC traceability mapped to owning implementation tasks (T-005, T-007, T-008, T-009, T-010, T-011).

## Targets, Tests, Done When [MUTABLE]
- **Targets:** `docs/feature-architecture/auto-approach/verification.md`
- **Tests:** `tests/test_auto_approach.py`
- **Done when:** `verification.md` contains the complete Unit Test Plan & Doubles Specification with every planned test function, its fixtures, assertions, and AC mapping; `5-tasks.md` updated with T-006 marked completed.

## Steps [MUTABLE]
- [x] T-006.1 **[unit-test-planner]** Define deterministic test fixtures and doubles (`Microtome_Mock`, SEM stub, Stage stub, GridManager double, synthetic tile generator) in `verification.md` §1.4.1.
- [x] T-006.2 **[unit-test-planner]** Detail algorithmic test suite for T-005 (`calibrate_tile_single_scan`, odd/even row centroid coincidence, bounded `phase_cross_correlation`, dual SSIM modes, Cyan/Magenta compositor) in `verification.md` §1.4.2.
- [x] T-006.3 **[unit-test-planner]** Detail microtome handshake & safety test suite for T-007 (`near_knife`, `clear_knife`, `do_full_approach_cut`, `.ack`/`.ac2`/`.err` handling) in `verification.md` §1.4.3.
- [x] T-006.4 **[unit-test-planner]** Detail configuration & grid reference test suite for T-008 (`CFG_NUMBER_SECTIONS=13`, `CFG_NUMBER_KEYS=254`, `process_cfg()` round-trip, `approach_ref_tiles`) in `verification.md` §1.4.4.
- [x] T-006.5 **[unit-test-planner]** Detail GUI controller test suite for T-009 (`ApproachDlg` non-modal trigger, dwell override, tab index) and T-010 (`Viewport` Approach tab canvas, wheel scrubbing, overlay cache) in `verification.md` §1.4.5.
- [x] T-006.6 **[unit-test-planner]** Detail cross-cutting safety guard test suite for T-011 (initial nominal-Z check, error freeze, abort Clear-after-stroke-down, scan-rotation preservation, beam blanking, `manifest.json`) in `verification.md` §1.4.6.
- [x] T-006.7 **[unit-test-planner]** Update `5-tasks.md` marking T-006 complete in the Dependencies graph.

## File Permissions
- MODIFY: `docs/feature-architecture/auto-approach/verification.md`
- MODIFY: `docs/feature-architecture/auto-approach/5-tasks.md`

## Types / methods / interfaces
- `verification.md` Section 1.4: Unit Test Plan & Doubles Specification
- Planned test signatures in `tests/test_auto_approach.py`:
  - `test_config_counts_and_process_cfg()`
  - `test_single_scan_odd_even_centroid_coincidence()`
  - `test_single_scan_calibration_pyramid_selection()`
  - `test_preflight_rejection_blank_saturated_noise()`
  - `test_bounded_registration_stage_jitter_and_100pct_shave()`
  - `test_dual_ssim_modes_cut_detection_and_dose_drift_invariance()`
  - `test_cyan_magenta_overlay_invariants()`
  - `test_microtome_near_clear_handshake_verification()`
  - `test_microtome_do_full_approach_cut_ac2_verification()`
  - `test_grid_manager_approach_ref_tiles_sync()`
  - `test_engine_initial_nominal_z_gate()`
  - `test_engine_nominal_batch_run_and_max_depth_stop()`
  - `test_engine_error_knife_freeze_invariant()`
  - `test_engine_user_abort_clear_after_stroke_down_invariant()`
  - `test_engine_scan_rotation_preservation_invariant()`
  - `test_engine_beam_blanking_transitions()`
  - `test_engine_manifest_json_persistence()`
  - `test_approach_dlg_controller_and_progress_trigger()`

## Data / contracts
- Cites `AutoApproachConfig`, `TileCalibrationProfile`, `TileStepEvaluation`, `ApproachStepRecord`, `ApproachProgress`, and `ProgressCallback` from `4-data-model.md`.

## Side-effects / risks
- None; documentation/planning only. No production or test code written during T-006.

## Verification steps
- Review `verification.md` §1.4 to ensure 100% coverage of AC-001..AC-008.
- Run `python3 ~/.gemini/config/skills/sdd-w-adversarial-review/scripts/sdlc_status_sync.py` to confirm slice consistency.
