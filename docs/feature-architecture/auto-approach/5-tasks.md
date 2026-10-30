# Tasks - Automated Sample Approach (`auto-approach`)

## Conventions
- Thin index only for tasks in this slice (`docs/feature-architecture/auto-approach/`).
- Every task maps to one or more PRD acceptance criteria IDs (`AC-SBEM-AUTO_APPROACH-001`..`008`).
- Detailed `CREATE:` / `MODIFY:` whitelists, step checklists, and pass criteria live in per-task `6-plan-TXXX.md` files generated **only after** human **Go** approval.
- Completion is tracked in the `Dependencies` graph (`[x]`).
- **Tests ship with code:** every implementation task (T-005, T-007, T-008, T-009, T-010, T-011) implements the tests assigned to it by the T-006 Unit Test Plan in `tests/test_auto_approach.py` (listed as `MODIFY:` and on the plan's `**Tests:**` line) and must be green before AR-3. T-012 runs the full suite as a final regression gate.

## Dependencies

| Done | Task  | Depends on          | Phase | Agent                     |
|:----:|:-----:|:-------------------:|:-----:|:--------------------------|
| [x]  | T-001 | -                   | 1     | `spec-owner`              |
| [x]  | T-002 | T-001               | 1     | `software-architect`      |
| [x]  | T-003 | T-002               | 1     | `contracts-designer`      |
| [x]  | T-004 | T-001, T-002, T-003 | 1     | `acceptance-test-planner` |
| [x]  | T-005 | T-003, T-004, T-006 | 2     | `implementation-engineer` |
| [x]  | T-006 | T-003, T-004        | 2     | `unit-test-planner`       |
| [x]  | T-007 | T-003, T-004, T-006 | 2     | `implementation-engineer` |
| [x]  | T-008 | T-003, T-004, T-006 | 2     | `implementation-engineer` |
| [x]  | T-009 | T-005, T-007, T-008 | 3     | `implementation-engineer` |
| [x]  | T-010 | T-005, T-008, T-009 | 3     | `implementation-engineer` |
| [x]  | T-011 | T-009, T-010        | 3     | `crosscutting-engineer`   |
| [x]  | T-012 | T-006, T-011        | 4     | `commit-optimizer`        |
| [x]  | T-013 | T-012               | 4     | `implementation-engineer` |

## Task List (Index Only)

- **T-001** Clarification Interview (`3-clarifications.md`) & PRD Specification (`1-prd.md`) (maps: `AC-SBEM-AUTO_APPROACH-001`..`008`) - **Agent: `spec-owner`** - *Status: Ready* - Plan: `6-plan-T001.md`
- **T-002** Architecture Decision Log (`2-adl.md`), Mathematical Pipeline (`auto-approach_architecture.md`), and Domain Physics (`knowledge.md`) (maps: `AC-SBEM-AUTO_APPROACH-001`..`008`) - **Agent: `software-architect`** - *Status: Ready* - Plan: `6-plan-T002.md`
- **T-003** Python 3.7.6 Typed Data Contracts, `[approach]` Schema, and On-Disk Manifest Model (`4-data-model.md`) (maps: `AC-SBEM-AUTO_APPROACH-001`..`008`) - **Agent: `contracts-designer`** - *Status: Ready* - Plan: `6-plan-T003.md`
- **T-004** Acceptance & Verification Protocol (`verification.md`) Across Unit, Simulation, and Microscope Runs (maps: `AC-SBEM-AUTO_APPROACH-001`..`008`) - **Agent: `acceptance-test-planner`** - *Status: Ready* - Plan: `6-plan-T004.md`
- **T-005** Implement Qt-Free `AutoApproachEngine`, Single-Scan Odd/Even Pyramidal Self-Calibration, Bounded Registration, Dual SSIM Modes, and Cyan/Magenta Compositor in `src/auto_approach.py` (maps: `AC-SBEM-AUTO_APPROACH-001`, `AC-SBEM-AUTO_APPROACH-002`, `AC-SBEM-AUTO_APPROACH-005`, `AC-SBEM-AUTO_APPROACH-007`) - **Agent: `implementation-engineer`** - *Status: Completed* - Plan: `6-plan-T005.md`
- **T-006** Unit Test Plan (plan only, no test code): per-task test lists, deterministic doubles (`Microtome_Mock`, SEM/Stage fakes, synthetic images), and AC traceability for T-005, T-007, T-008, T-009, T-010, T-011, recorded in `verification.md` §Unit Test Plan (Calibration, Surface Cut Detection, Dose Drift, Jitter, Cyan/Magenta, Non-Destructive Error/Abort Invariants, Scan-Rotation Preservation & Config Invariant) (maps: `AC-SBEM-AUTO_APPROACH-001`..`008`) - **Agent: `unit-test-planner`** - *Status: Completed* - Plan: `6-plan-T006.md`
- **T-007** Harden Gatan 3View `near_knife()`, `clear_knife()`, and `do_full_approach_cut()` `.ack`/`.ac2`/`.err` Handshake Verification in `src/microtome_control_gatan.py`, `src/microtome_control.py`, and `src/microtome_control_mock.py` (`dm/*.s` Unmodified) (maps: `AC-SBEM-AUTO_APPROACH-002`, `AC-SBEM-AUTO_APPROACH-004`, `AC-SBEM-AUTO_APPROACH-005`) - **Agent: `implementation-engineer`** - *Status: Completed* - Plan: `6-plan-T007.md`
- **T-008** Add `[approach]` Section to `src/default_cfg/default.ini`, Update `CFG_NUMBER_SECTIONS = 13` / `CFG_NUMBER_KEYS = 254` in `src/config_template.py`, and Add `approach_ref_tiles` Support in `src/grid_manager.py` (maps: `AC-SBEM-AUTO_APPROACH-003`, `AC-SBEM-AUTO_APPROACH-008`) - **Agent: `implementation-engineer`** - *Status: Completed* - Plan: `6-plan-T008.md`
- **T-009** Upgrade `ApproachDlg` (`gui/approach_dlg.ui`, `src/main_controls_dlg_windows.py`, `src/main_controls.py`) to Non-Modal Tabbed Dialog (`Manual` & `Automated` Tabs, Live-Synced `Reference tiles:` Input, Dwell Override, SSIM Mode Selector, `RESTRICT GUI`) (maps: `AC-SBEM-AUTO_APPROACH-003`, `AC-SBEM-AUTO_APPROACH-006`) - **Agent: `implementation-engineer`** - *Status: Completed* - Plan: `6-plan-T009.md`
- **T-010** Add 4th `Approach` Tab (`tab_ap`) to `gui/viewport.ui` & `src/viewport.py` (Auto-Tiled Cyan/Magenta Grid, Mouse-Wheel Series Scrubbing, Step Slider, Raw Toggle, Double-Click Zoom, Archived Run Loader & Viewport Right-Click Ref Badge) (maps: `AC-SBEM-AUTO_APPROACH-003`, `AC-SBEM-AUTO_APPROACH-007`) - **Agent: `implementation-engineer`** - *Status: Completed* - Plan: `6-plan-T010.md`
- **T-011** Add Fail-Safe Guards (Nominal-Z Pre-Clear Check, Error Knife-Freeze, Abort `Clear`-After-Stroke-Down, Scan-Rotation Preservation, Beam Blanking, App Exit Prompt) & Structured `meta/approach/<timestamp>/manifest.json` Persistence (maps: `AC-SBEM-AUTO_APPROACH-002`, `AC-SBEM-AUTO_APPROACH-004`, `AC-SBEM-AUTO_APPROACH-005`, `AC-SBEM-AUTO_APPROACH-007`) - **Agent: `crosscutting-engineer`** - *Status: Completed* - Plan: `6-plan-T011.md`
- **T-012** Write User Documentation (`docs/auto_approach_help.md`), Run Dialectical Refactoring & Code Review Gate, and Prepare Clean Release Commit (maps: `AC-SBEM-AUTO_APPROACH-001`..`008`) - **Agent: `commit-optimizer`** - *Status: Completed* - Plan: `6-plan-T012.md`
- **T-013** Production Hardening: Immediate Abort on Reference Tile Acquisition without acquiring remaining probe tiles (maps: `AC-SBEM-AUTO_APPROACH-005`) - **Agent: `implementation-engineer`** - *Status: Completed*
