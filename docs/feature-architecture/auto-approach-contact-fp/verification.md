# Verification Protocol: fix/auto-approach-contact-fp

## 1. Automated Verification Suite
All automated testing is executed under the strict Python 3.7.6 Conda environment:
`~/miniforge3/envs/sbem-py37/bin/python agent_test.py tests/test_auto_approach.py`

### Key Test Categories:
1. **Pearson Metric Invariants (`test_pearson_invariants`)**:
   - Identity: identical images return $r = 1.0$.
   - Inversion: negated images return $r = -1.0$.
   - Flat/Zero variance: zero-variance arrays return $r = 0.0$ without division by zero.
   - Contrast/Brightness invariance: $r(I, a \cdot I + b) = 1.0$ for $a > 0$.
2. **Production Air Approach Runs False-Positive Immunity (`test_production_air_approach_runs_false_positive_immunity`)**:
   - Evaluates all 7 production air runs (`143927`, `144723`, `145034`, `145242`, `145618`, `145806`, `151539`).
   - Asserts 0% False Positive Rate on Step 1 (`contact_detected == False`).
3. **Production Cut Run Sensitivity (`test_production_cut_run_step1_sensitivity`)**:
   - Evaluates run `2026-10-30_171229` on Step 1 (the initial 3 cuts).
   - Asserts `contact_detected == True` on Step 1, verifying that the cut is detected without delay.
4. **Historical Missed-Cut False-Positive Immunity (`test_historical_missed_cuts_false_positive_immunity`)**:
   - Evaluates all labeled missed cuts in `sbem_test_data/missed_cuts/roli-f1` across tiles `t0362`, `t0364`, `t0387`.
   - Asserts 0% False Positive Rate.
5. **Historical Real Cuts Sensitivity (`test_historical_real_cuts_sensitivity`)**:
   - Evaluates benchmark cuts in `roli-f1/t0364`.
   - Asserts 100% True Positive Rate.

## 2. Pre-Flight Syntax Check
Before running pytest:
`~/miniforge3/envs/sbem-py37/bin/python -m py_compile src/auto_approach.py tests/test_auto_approach.py`
