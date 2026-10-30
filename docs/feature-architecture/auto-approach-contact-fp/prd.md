# PRD: fix/auto-approach-contact-fp

## 1. System Objective
Eliminate false-positive contact detections during Automated Approach (`auto-approach`) on Gatan 3View SBEM systems while ensuring immediate, zero-delay sensitivity to initial knife contact.

In production validation on the physical microscope (run `2026-10-30_171229`), Pearson correlation contact gating successfully eliminated false positives in air, but detected physical contact **one batch (3 cuts, $225\,\text{nm}$) late** (triggered on Step 2 instead of Step 1). This slice addresses the root causes:
1. Aligning single-scan odd/even raster self-calibration to evaluate **Pearson correlation** instead of Gradient SSIM, preventing unnecessary downsampling to Level 4 ($16\times$).
2. Adjusting the stage wander clamp $s_{\text{max}}$ to permit physical drift up to $15\,\mu\text{m}$ ($375\,\text{px}$ at $40\,\text{nm}$), preventing valid shifts from being clamped to $(0, 0)$ at lower pyramid levels.
3. Decoupling or capping the evaluation scale at Level 2 ($4\times$) or Level 3 ($8\times$) and tuning the threshold floor from $0.400$ to $0.240$, ensuring a wide separation margin between air drift ($d \le 0.195$) and initial skim cuts ($d \ge 0.263 - 0.411$).

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
  - `calibrate_tile_single_scan()`: Evaluate odd/even raster line split using `evaluate_pearson_r()`. Select scale where odd/even $r \ge 0.94$ (typically Level 2 or 3). Set dissimilarity trigger limit:
    $$d_{\text{trigger}} = \min(\max(4.0 \cdot d_{\text{noise}},\; 0.24),\; 0.65)$$
  - `compute_stage_clamp_px()`: Increase physical wander limit from $5000\,\text{nm}$ to $15000\,\text{nm}$ ($15\,\mu\text{m}$) so that physical stage drift (observed up to $11\,\mu\text{m}$) is not clamped to $(0, 0)$ at Level 2 or 3.
  - `register_and_crop()` / `evaluate_tile_pair()`: Support robust registration and evaluation at the calibrated level (capped at Level 3 max).
- `tests/test_auto_approach.py`:
  - New test `test_production_cut_run_step1_sensitivity()` asserting run `2026-10-30_171229` triggers `contact_detected == True` on Step 1 (first 3 cuts, $0.225\,\mu\text{m}$).
  - Regression tests for all 7 production air runs (`143927` through `151539`) asserting ZERO false positives.
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
- **Separation Safety**:
  - Air drift across all 7 production runs at Level 2/3: $d_{\text{drift}} \le 0.195 < 0.240$ (Safe by margin $\ge 0.045$).
  - Initial partial cut on Step 1 of `171229`: $d_{\text{cut}} \in [0.263, 0.411] \ge 0.240$ (Detected on Step 1).
  - Deep cut on Step 2 of `171229`: $d_{\text{cut}} \ge 0.485 \ge 0.240$ (Detected).
  - Real cuts in `roli-f1`: $d_{\text{cut}} \in [0.46, 0.97] \ge 0.240$ (Reliably detected).
