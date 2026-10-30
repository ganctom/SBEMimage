# Implementation Plan - T-012 User Documentation & Release Candidate [MUTABLE]

## Metadata [MUTABLE]
- **Task ID:** T-012
- **Task Title:** Write User Documentation (`docs/auto_approach_help.md`), Conduct Code Review & Verification Summary, and Prepare Clean Release Candidate
- **Agent:** `commit-optimizer`
- **PRD:** `1-prd.md`
- **ADL:** `2-adl.md`
- **Tasks:** `5-tasks.md`
- **AC IDs:** `AC-SBEM-AUTO_APPROACH-001`, `AC-SBEM-AUTO_APPROACH-002`, `AC-SBEM-AUTO_APPROACH-003`, `AC-SBEM-AUTO_APPROACH-004`, `AC-SBEM-AUTO_APPROACH-005`, `AC-SBEM-AUTO_APPROACH-006`, `AC-SBEM-AUTO_APPROACH-007`, `AC-SBEM-AUTO_APPROACH-008`
- Status: Completed

## Summary
Provide complete user documentation, conduct a formal code review summary across all 11 implementation tasks, and prepare the release candidate for merging into `dev-tomgan-rel`:
1. **User Documentation (`docs/auto_approach_help.md`):**
   - Author clear, structured operator guide covering automated approach setup, reference tile selection (right-click in Viewport / text edit in dialog), parameter tuning, dwell-time override, and SSIM mode selection.
   - Document Viewport 4th `Approach` tab features: live Cyan/Magenta compositing, mouse-wheel history scrubbing, raw toggle, double-click zoom, step slider, and archived run replay.
   - Detail hardware safety invariants: nominal-Z pre-clear verification, verified Clear before XY moves, error knife-freeze (zero Clear on error), safe abort Clear-after-stroke-down, scan-rotation preservation, automatic beam blanking, and application exit blocking.
   - Document archived run format: `meta/approach/<timestamp>/manifest.json`, `raw/*.tif`, and `overlays/*.png` relative POSIX path structure.
2. **Verification & Code Review Artifact:**
   - Execute complete test suite asserting 100% green pass across all unit and hardware-mocked integration tests.
   - Verify zero Python 3.8+ syntax violations (Python 3.7.6 strict compliance).
   - Verify immutability of DigitalMicrograph communication scripts (`dm/*.s` completely unmodified).
   - Verify configuration invariants (`CFG_NUMBER_SECTIONS = 13`, `CFG_NUMBER_KEYS = 254`).
3. **Release Candidate Ledger:**
   - Check off all tasks in `docs/feature-architecture/auto-approach/5-tasks.md`.
   - Update `6-plan-T012.md` status to Completed.

## User-Facing Changes
- `docs/auto_approach_help.md`: Comprehensive user guide accessible to microscopists and developers detailing the automated approach system, GUI controls, hardware dynamics, and troubleshooting.
- `docs/feature-architecture/README.md`: Central registry status updated from 'In Progress' to 'Completed'.

## File Whitelist
- CREATE: `docs/auto_approach_help.md`
- MODIFY: `docs/feature-architecture/README.md`
- MODIFY: `docs/feature-architecture/auto-approach/verification.md`
- MODIFY: `docs/feature-architecture/auto-approach/6-plan-T012.md`
- MODIFY: `docs/feature-architecture/auto-approach/5-tasks.md`
- MODIFY: `src/viewport.py`
- MODIFY: `tests/test_auto_approach.py`

## Steps [MUTABLE]
- [x] T-012.1 **[commit-optimizer]** Author `docs/auto_approach_help.md` matching SBEMimage documentation standards:
  - Section 1: Overview & Vision-Guided Approach Principles.
  - Section 2: Quick Start & Parameter Tuning (tile selection, slice thickness, batch size, max depth, dwell override, SSIM modes).
  - Section 3: Viewport 4th `Approach` Tab (Cyan/Magenta overlays, wheel scrubbing, raw toggle, zoom, run history).
  - Section 4: Physical Dynamics & Hardware Safety Invariants (Nominal-Z, verified Clear, error freeze, abort after stroke-down, scan rotation, beam blanking, exit guard).
  - Section 5: Data Serialization & Offline Inspection (`meta/approach/<timestamp>/manifest.json`).
- [x] T-012.2 **[commit-optimizer]** Run pre-flight syntax checks on the 9 modified modules via:
  `~/miniforge3/envs/sbem-py37/bin/python -m py_compile src/auto_approach.py src/config_template.py src/grid_manager.py src/microtome_control.py src/microtome_control_gatan.py src/microtome_control_mock.py src/main_controls.py src/main_controls_dlg_windows.py src/viewport.py tests/test_auto_approach.py`
  and execute test suite via:
  `QT_QPA_PLATFORM=offscreen ~/miniforge3/envs/sbem-py37/bin/python agent_test.py tests/test_auto_approach.py`.
- [x] T-012.3 **[commit-optimizer]** Verify configuration entry counts (`CFG_NUMBER_SECTIONS = 13`, `CFG_NUMBER_KEYS = 254`), verify immutability of `dm/*.s` via `git diff --exit-code origin/dev-tomgan-rel -- dm/`, and record final test pass, syntax compliance, and formal code review sign-off in `docs/feature-architecture/auto-approach/verification.md`.
- [x] T-012.4 **[commit-optimizer]** Update `docs/feature-architecture/README.md` line 13 status from 'In Progress' to 'Completed', update `docs/feature-architecture/auto-approach/5-tasks.md` checking off T-012, and set `Status: Completed` in `6-plan-T012.md:11`.

## Types / methods / interfaces
- Documentation file: `docs/auto_approach_help.md`

## Side-effects / risks
- None; user documentation and release candidate verification do not alter runtime behavior.
