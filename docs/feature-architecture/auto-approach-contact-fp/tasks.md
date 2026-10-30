# Tasks: fix/auto-approach-contact-fp

| Task ID | Phase | Description | In-Scope Files | Parent AC | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **T-FP-001** | Phase 1: Spec & Design | Document system boundaries, physics, mathematical formulations, PRD, and granular acceptance criteria. | `docs/feature-architecture/auto-approach-contact-fp/*` | `AC-AA-FP-001` | **COMPLETED** |
| **T-FP-002** | Phase 2: TDD Test Suite | Implement unit and regression tests asserting Pearson correlation evaluation, floor calibration ($d \ge 0.40$), and zero false positives across both production and historical missed-cut datasets. | `tests/test_auto_approach.py` | `AC-AA-FP-002`, `AC-AA-FP-003`, `AC-AA-FP-004`, `AC-AA-FP-005` | **COMPLETED** |
| **T-FP-003** | Phase 3: Engine Implementation | Implement `evaluate_pearson_r()`, update `calibrate_tile_single_scan()`, and integrate Pearson correlation into `evaluate_tile_pair()` in `src/auto_approach.py`. | `src/auto_approach.py` | `AC-AA-FP-002`, `AC-AA-FP-003`, `AC-AA-FP-006` | **COMPLETED** |
| **T-FP-004** | Phase 4: Production & Roli-F1 Verification | Run comprehensive verification against all 7 production runs (`validation_in_production`) and 3 `roli-f1` benchmark tiles asserting zero false positives and 100% cut sensitivity. | `tests/test_auto_approach.py` | `AC-AA-FP-003`, `AC-AA-FP-004`, `AC-AA-FP-006` | **COMPLETED** |
| **T-FP-005** | Phase 5: Documentation & Release Review | Update user manual `docs/auto_approach_help.md` and feature architecture ledger for release candidate. | `docs/auto_approach_help.md` | `AC-AA-FP-007` | **COMPLETED** |

---

### Granular Acceptance Criteria Mapping

- **`AC-AA-FP-001` (Specification Rigor)**: PRD, domain physics, and mathematical architecture accurately specify Pearson correlation contact gating, failure modes, and hard constraints (Python 3.7.6, fail-safe knife state).
- **`AC-AA-FP-002` (Pearson Metric Invariants)**: `evaluate_pearson_r()` returns values strictly bounded in $[-1.0, 1.0]$, handles zero-variance flat resin gracefully without division by zero, and is invariant to linear brightness/contrast scaling.
- **`AC-AA-FP-003` (Production False-Positive Immunity)**: When evaluating Step 1 across all 7 production validation runs (`2026-10-30_143927`, `144723`, `145034`, `145242`, `145618`, `145806`, `151539`), `contact_detected` must evaluate to `False` for every single probe tile and for the overall step (0% False Positive Rate).
- **`AC-AA-FP-004` (Historical Missed-Cuts False-Positive Immunity)**: On all labeled missed-cut transitions in `sbem_test_data/missed_cuts/roli-f1` (where the knife swept across the block but removed zero tissue), `contact_detected` must evaluate to `False` (0% False Positive Rate on missed cuts).
- **`AC-AA-FP-005` (Pre-Flight Safety Integrity)**: Production run `2026-10-30_142037` must continue to correctly trigger `ApproachState.PREFLIGHT_FAILED` on unusable/featureless surfaces without attempting any physical cuts.
- **`AC-AA-FP-006` (Physical Cut True-Positive Sensitivity)**: Real physical cuts in `sbem_test_data/missed_cuts/roli-f1` must evaluate to `contact_detected == True` with 100% sensitivity.
- **`AC-AA-FP-007` (Zero Regressions)**: All existing and new tests pass cleanly via `~/miniforge3/envs/sbem-py37/bin/python agent_test.py tests/test_auto_approach.py` with zero regressions.
