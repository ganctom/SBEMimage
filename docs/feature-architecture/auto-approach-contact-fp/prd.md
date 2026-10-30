# PRD: fix/auto-approach-contact-fp

## 1. System Objective
Eliminate false-positive contact detections during Automated Approach (`auto-approach`) on Gatan 3View SBEM systems while ensuring immediate, zero-delay sensitivity to initial knife contact down to 25 nm sectioning.

In production validation on the physical microscope (run `2026-10-30_171229`), Pearson correlation contact gating successfully eliminated false positives in air, but detected physical contact **one batch late** (triggered on Step 2 instead of Step 1). In run `2026-10-30_181342`, consecutive 150 nm cuts failed detection entirely due to low-frequency background persistence at pyramid Level 3 ($8\times$).

Slice 3 addresses these root causes via:
1. Preprocessing input frames with **Gaussian filtering ($\sigma = 1.0$)** to suppress single-pixel electron shot noise followed by **CLAHE (`clipLimit=2.0`, `tileGridSize=(8, 8)`)** to remove illumination shading and amplify local ultrastructure contrast.
2. Enhancing translational registration by computing subpixel phase correlation on a **10% center crop** of the image field, eliminating peripheral scan flyback transients, beam deflection distortions, and knife border artifacts.
3. Evaluating Pearson correlation at full resolution ($l^* = 0$), where odd/even raster lines achieve $r \ge 0.99$ after preprocessing, preserving true ultrastructural dissimilarity ($d \ge 0.31 - 0.77$) while maintaining zero false positives in air ($d \le 0.25 < 0.27$).

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
  - `preprocess_approach_frame()`: Implement Gaussian denoising ($\sigma = 1.0$) followed by CLAHE (`clipLimit=2.0`, `tileGridSize=(8, 8)`).
  - `calibrate_tile_single_scan()`: Evaluate odd/even raster line split on raw and preprocessed frames. Calculate structural contrast ratio $\gamma_{\text{struct}} = \sigma_{\text{struct}} / (\sigma_{\text{total}} + \epsilon)$. Set tile-specific cut dissimilarity threshold:
    $$d_{\text{trigger}}(\text{tile}) = \text{clamp}\Big(0.35 + 7.5 \cdot (0.75 - \gamma_{\text{struct}}),\; 0.300,\; 0.660\Big)$$
  - `register_and_crop()`: Perform subpixel translational registration via `phase_cross_correlation` on a central 10% cropped window ($[0.10H:0.90H, 0.10W:0.90W]$) to eliminate perimeter flyback transients and distortions. Clamp shifts exceeding $15\,\mu\text{m}$ ($s_{\text{max}}$).
  - `evaluate_tile_pair()`: Preprocess input frames with `preprocess_approach_frame()`, execute center-crop registration, and evaluate Pearson dissimilarity $d = \max(0.0, 1.0 - r)$ against $d_{\text{trigger}}(\text{tile})$.
- `tests/test_auto_approach.py`:
  - New test `test_preprocess_approach_frame()` asserting Gaussian+CLAHE contracts.
  - New test `test_register_and_crop_center10()` asserting 10% boundary exclusion and wander clamp.
  - Integration test `test_production_run_181342_step1_sensitivity()` asserting 25 nm ultra-thin cut detection on Step 1.
  - Integration test `test_production_cut_run_step1_sensitivity()` asserting run `171229` Step 1 detection.
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
