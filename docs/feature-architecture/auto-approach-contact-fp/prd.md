# PRD: fix/auto-approach-contact-fp

## 1. System Objective
Eliminate false-positive contact detections during Automated Approach (`auto-approach`) on Gatan 3View SBEM systems. When the diamond knife sweeps through air during approach (advancing $500\,\text{nm}$ in $Z$ per 5-slice batch), the current engine falsely declares contact on Step 1 because the single-scan calibration sets a cut dissimilarity floor of $0.120$ (equivalent to requiring $\text{SSIM} \ge 0.880$). Two separate SEM acquisitions taken 5 cuts apart naturally experience an SSIM ceiling of $0.75 - 0.87$ due to focus shifts, beam charging, and uncorrelated Poisson noise. This feature implements **Strategy 1: Global Pearson Correlation Metric Replacement**, establishing a wide, robust separation margin ($\ge 0.17 - 0.20$) that safely classifies all uncut surfaces as non-contact while reliably capturing physical knife cuts.

## 2. Hard Constraints
- **Target Runtime**: STRICTLY Python 3.7.6 (x86_64 Rosetta / Conda `sbem-py37`).
  - NO walrus operator (`:=`).
  - NO PEP 585 generics (`list[str]`); use `typing.List[str]`.
  - NO PEP 604 unions (`int | None`); use `typing.Optional[int]` or `typing.Union`.
  - NO f-strings with `=` (`f"{var=}"`).
- **Zero GUI Contamination**: `src/auto_approach.py` must remain completely free of PyQt5 or QObject imports.
- **Fail-Safe Integrity**: State restoration on abort, safe knife retraction, and Z nominal ceiling checks must remain unmodified.
- **Configuration Invariants**: Do not alter section or key counts in `src/default_cfg/default.ini` or `system.cfg` without updating `src/config_template.py`.
- **Backward Compatibility**: `manifest.json` schema and `TileEvaluationRecord` fields must remain backward-compatible with Viewport Approach tab rendering.

## 3. In-Scope Boundaries
- `src/auto_approach.py`:
  - Pearson correlation evaluator `evaluate_pearson_r(prev_crop, curr_crop)`.
  - Threshold calibration in `calibrate_tile_single_scan()` (updating minimum dissimilarity floor to $0.40$).
  - Pair evaluation in `evaluate_tile_pair()` using Pearson correlation for contact classification.
- `tests/test_auto_approach.py`:
  - Unit tests for Pearson correlation, self-calibration, and cut detection.
  - Regression tests for all 7 production runs (`validation_in_production`) asserting ZERO false positives on air cuts.
  - Regression tests for all labeled missed cuts in `roli-f1` asserting ZERO false positives.
  - Regression tests for all labeled real cuts in `roli-f1` asserting 100% sensitivity.
- `docs/feature-architecture/auto-approach-contact-fp/`:
  - Full architecture documentation suite (`prd.md`, `knowledge.md`, `auto-approach-contact-fp_architecture.md`, `verification.md`, `tasks.md`).

## 4. Anti-Targets
- Do not refactor PyQt GUI code in `src/main_controls_dlg_windows.py` or `src/viewport.py`.
- Do not modify Digital Micrograph scripts in `dm/`.
- Do not modify or index `magc/`.
- Do not introduce dependencies unsupported by Python 3.7.6.

## 5. Architectural Discussion & Design
- **Metric Formulation**:
  $$r(U, V) = \frac{\sum (U - \mu_U)(V - \mu_V)}{\max(\sqrt{\sum (U - \mu_U)^2 \sum (V - \mu_V)^2},\; 10^{-6})}$$
  $$d_{\text{corr}} = \max(0.0,\; 1.0 - r(U, V))$$
- **Self-Calibrated Trigger Limit**:
  $$d_{\text{trigger}} = \min(\max(4.0 \cdot d_{\text{noise\_corr}},\; 0.40),\; 0.65)$$
- **Separation Safety**:
  - Uncut frames in production: $r \in [0.75, 0.98] \implies d_{\text{corr}} \in [0.02, 0.25] < 0.40$ (Safe by $\Delta \ge 0.15$).
  - Real cuts in `roli-f1`: $r \in [0.03, 0.54] \implies d_{\text{corr}} \in [0.46, 0.97] \ge 0.40$ (Reliably detected).
