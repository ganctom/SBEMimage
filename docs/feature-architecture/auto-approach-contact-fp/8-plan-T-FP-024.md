# Implementation Plan: Hierarchical Multi-Scale Registration Engine (T-FP-024)

## 1. Problem Statement & Motivation
In production run `2026-11-02_143319`, knife contact removed a full-face $50\,\text{nm}$ slice. Because the high-frequency surface texture decorrelated, full-resolution Phase Cross Correlation (PCC) generated noise peaks that exceeded the physical stage wander clamp ($s_{\text{max}} = 460\,\text{px} \approx 15\,\mu\text{m}$). Consequently, `register_and_crop()` clamped the estimated shift to `(0.0, 0.0)`. In the Viewport, the raw images therefore displayed the uncompensated $\sim 13\,\mu\text{m}$ ($\approx 350\,\text{px}$) physical stage displacement without registration.

SIFT was evaluated as an alternative, but produced very low inlier counts ($2 - 10$ inliers out of $\sim 35,000$ keypoints) and added significant latency ($\approx 2.9\,\text{s}$ per tile).

## 2. Mathematical Design: Hierarchical Multi-Scale Normalized Matching
Replace full-resolution direct Phase Cross Correlation with a **hierarchical multi-scale template matching** approach:

1. **Level 1 (Coarse, 4x downsample / $1024 \times 768$)**:
   - Extract the central 50% template from previous frame $d_0$.
   - Search the entire downsampled current frame $d_1$ using `cv2.matchTemplate(..., cv2.TM_CCOEFF_NORMED)`.
   - Locates gross anatomical structures and cellular boundaries even across heavy physical shaves ($\text{corr} > 0.40 - 0.65$, taking $< 10\,\text{ms}$).
2. **Level 2 (Intermediate, 2x downsample / $2048 \times 1536$)**:
   - Extract template from $d_{0, 2}$ and refine the peak within a tight local window ($\pm 16\,\text{px}$) around the coarse peak.
3. **Level 3 (Fine, Full Resolution / $4096 \times 3072$)**:
   - Extract full-resolution template and search within $\pm 8\,\text{px}$ of the Level 2 peak.
   - Parabolic subpixel interpolation on the $3 \times 3$ correlation peak yields subpixel accuracy down to $< 0.1\,\text{px}$.
4. **Physical Safety Bound & Fallback**:
   - The shift clamp in `compute_stage_clamp_px()` is updated to **40% of the shorter side of the image**:
     $$s_{\text{max}} = \lfloor 0.40 \cdot \min(H, W) \rfloor$$
     For a $4096 \times 3072$ tile, $s_{\text{max}} = \lfloor 0.40 \cdot 3072 \rfloor = 1228\,\text{px}$ ($\approx 46\,\mu\text{m}$ at $37.8\,\text{nm/px}$).
   - This removes the arbitrary fixed $15\,\mu\text{m}$ limit and scales proportionally with magnification, field-of-view, and tile resolution.
   - If correlation peak is below confidence threshold ($r < 0.20$) or exceeds the 40% clamp, falls back to `(0.0, 0.0)`.

## 3. In-Scope Files
- `src/auto_approach.py`: update `register_and_crop()` to implement hierarchical multi-scale registration.
- `tests/test_auto_approach.py`: add regression test for run `2026-11-02_143319` asserting recovery of $(\approx -352, -358)$ shift, and verify zero false positives across all 7 production air runs.

## 4. Execution Tasks
- [ ] Implement `hierarchical_template_register()` in `src/auto_approach.py`
- [ ] Connect into `register_and_crop()`
- [ ] Add unit test in `tests/test_auto_approach.py`
- [ ] Verify test suite (10/10 viewport, 47/47 auto approach)
- [ ] Deploy to USB drive `/Volumes/NO NAME/tg_sbemimage`
