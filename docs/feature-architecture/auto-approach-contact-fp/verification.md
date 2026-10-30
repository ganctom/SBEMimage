# Verification Routine: fix/auto-approach-contact-fp

## 1. Automated Test Commands
Run using the Python 3.7.6 Conda environment:
```bash
# Pre-flight syntax validation
~/miniforge3/envs/sbem-py37/bin/python -m py_compile src/auto_approach.py
flake8 src/auto_approach.py --select=E9,F63,F7,F82

# Unit test execution with token-optimized test runner
~/miniforge3/envs/sbem-py37/bin/python agent_test.py tests/test_auto_approach.py
```

## 2. Granular Acceptance Test Matrix

| Acceptance Criterion | Verification Method | Pass Criteria |
| :--- | :--- | :--- |
| **`AC-AA-FP-002`** (Pearson Metric Invariants) | Unit tests in `test_auto_approach.py` | - Synthetic identical pairs yield $r = 1.0, d = 0.0$<br>- Independent Gaussian noise yields $r \approx 0.0, d \approx 1.0$<br>- Flat zero-variance arrays yield $r = 0.0, d = 1.0$ without exception<br>- Linear affine intensity scaling $V = a U + b$ ($a > 0$) yields $r = 1.0, d = 0.0$ |
| **`AC-AA-FP-003`** (Production FP Immunity) | Regression test iterating all 7 production runs in `validation_in_production/` | Step 1 evaluation on all 7 runs (`143927`, `144723`, `145034`, `145242`, `145618`, `145806`, `151539`) yields `contact_detected == False` on every tile ($0 / 18$ false positives) |
| **`AC-AA-FP-004`** (Historical Missed-Cut FP Immunity) | Regression test on `roli-f1` (`t0362`, `t0364`) | All labeled missed-cut transitions yield `contact_detected == False` ($0\%$ False Positive Rate) |
| **`AC-AA-FP-005`** (Pre-Flight Safety Integrity) | Replay test on run `2026-10-30_142037` | Engine halts with `ApproachState.PREFLIGHT_FAILED` before cutting any slices |
| **`AC-AA-FP-006`** (Cut Sensitivity) | Regression test on `roli-f1` real cut transitions | Real physical cuts yield `contact_detected == True` ($100\%$ True Positive Rate) |
| **`AC-AA-FP-007`** (Zero Regressions) | Full test suite execution | `agent_test.py tests/test_auto_approach.py` passes with $0$ failures |
