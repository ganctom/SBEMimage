# Tasks: fix/auto-approach-contact-fp

| Task ID | Phase | Description | In-Scope Files | Parent AC | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **T-FP-001** | Phase 1: Spec & Design | Document system boundaries, physics, mathematical formulations, PRD, and granular acceptance criteria. | `docs/feature-architecture/auto-approach-contact-fp/*` | `AC-AA-FP-001` | **COMPLETED** |
| **T-FP-002** | Phase 2: TDD Test Suite | Implement unit and regression tests asserting Pearson correlation evaluation, floor calibration ($d \ge 0.40$), and zero false positives across both production and historical missed-cut datasets. | `tests/test_auto_approach.py` | `AC-AA-FP-002`, `AC-AA-FP-003`, `AC-AA-FP-004`, `AC-AA-FP-005` | **COMPLETED** |
| **T-FP-003** | Phase 3: Engine Implementation | Implement `evaluate_pearson_r()`, update `calibrate_tile_single_scan()`, and integrate Pearson correlation into `evaluate_tile_pair()` in `src/auto_approach.py`. | `src/auto_approach.py` | `AC-AA-FP-002`, `AC-AA-FP-003`, `AC-AA-FP-006` | **COMPLETED** |
| **T-FP-004** | Phase 4: Production & Roli-F1 Verification | Run comprehensive verification against all 7 production runs (`validation_in_production`) and 3 `roli-f1` benchmark tiles asserting zero false positives and 100% cut sensitivity. | `tests/test_auto_approach.py` | `AC-AA-FP-003`, `AC-AA-FP-004`, `AC-AA-FP-006` | **COMPLETED** |
| **T-FP-005** | Phase 5: Documentation & Release Review | Update user manual `docs/auto_approach_help.md` and feature architecture ledger for release candidate. | `docs/auto_approach_help.md` | `AC-AA-FP-007` | **COMPLETED** |
| **T-FP-006** | Slice 2: Spec & Physics Refinement | Update PRD, architecture, and domain knowledge with findings from run `2026-10-30_171229`, formulating the Pearson odd/even self-calibration metric, wander clamp expansion ($15\,\mu\text{m}$), and floor tuning ($0.270$). | `docs/feature-architecture/auto-approach-contact-fp/*` | `AC-AA-FP-008` | **COMPLETED** |
| **T-FP-007** | Slice 2: TDD Test Suite Expansion | Add test `test_production_cut_run_step1_sensitivity()` for run `2026-10-30_171229` Step 1 contact detection while asserting existing air run FP immunity under the new calibration logic. | `tests/test_auto_approach.py` | `AC-AA-FP-008`, `AC-AA-FP-009` | **COMPLETED** |
| **T-FP-008** | Slice 2: Engine Calibration & Registration Implementation | Update `calibrate_tile_single_scan()` to evaluate Pearson correlation on odd/even raster lines ($r \ge 0.97$), set floor to $0.270$, and increase wander clamp limit in `compute_stage_clamp_px()` to $15000\,\text{nm}$. | `src/auto_approach.py` | `AC-AA-FP-008`, `AC-AA-FP-009` | **COMPLETED** |
| **T-FP-009** | Slice 2: Verification Suite | Execute token-optimized test suite asserting run `171229` triggers on Step 1, all 7 air runs maintain 0% FP, and `roli-f1` tests pass cleanly. | `tests/test_auto_approach.py` | `AC-AA-FP-008`, `AC-AA-FP-009`, `AC-AA-FP-010` | **COMPLETED** |
| **T-FP-010** | Slice 2: Release & USB Deployment | Update user docs and code review, create descriptive squash commit, and push to `usb` remote. | `docs/*`, `git` | `AC-AA-FP-010` | **COMPLETED** |

---

### Granular Acceptance Criteria Mapping

- **`AC-AA-FP-008` (Immediate Step 1 Cut Sensitivity)**: In production run `2026-10-30_171229`, Step 1 (the initial batch of 3 cuts) must trigger `contact_detected == True` on at least one probe tile, preventing the delayed cut detection observed previously.
- **`AC-AA-FP-009` (Air Approach Zero False Positive Rate)**: Across all 7 production air runs (`143927`, `144723`, `145034`, `145242`, `145618`, `145806`, `151539`), `contact_detected` must evaluate to `False` on Step 1 (0% FP).
- **`AC-AA-FP-010` (Full Regression Suite Clean)**: All tests in `tests/test_auto_approach.py` pass cleanly under Python 3.7.6 with zero regressions.
