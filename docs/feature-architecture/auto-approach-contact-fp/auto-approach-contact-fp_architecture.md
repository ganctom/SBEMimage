# Architecture: fix/auto-approach-contact-fp

## 1. System Context & Pipeline
The Automated Approach (`auto-approach`) algorithm operates cyclically during SEM-microtome approach:
1. **Calibration (Step 0)**:
   - For each designated probe tile, acquire baseline frame $I_0$.
   - Run `calibrate_tile_single_scan(I_0)`:
     - Split into even and odd scan-lines $E[r]$ and $O[r]$ on lattice $y = 2r + 1.5$.
     - Interpolate to symmetric lattice:
       $$\tilde{E}[r] = \frac{1}{4} E[r] + \frac{3}{4} E[r+1],\quad \tilde{O}[r] = \frac{3}{4} O[r] + \frac{1}{4} O[r+1]$$
     - Evaluate odd/even **Pearson correlation** across pyramid levels $l \in [0, 4]$.
     - Select smallest scale $l^*$ where $r(l) \ge 0.97$, capped at $\min(l^*, 4)$.
     - Compute noise dissimilarity: $d_{\text{noise}} = \max(0.0, 1.0 - r(l^*))$.
     - Set cut dissimilarity threshold:
       $$d_{\text{trigger}} = \min(\max(4.0 \cdot d_{\text{noise}},\; 0.270),\; 0.650)$$
     - Compute stage wander clamp:
       $$s_{\text{max}} = \max\left(2,\; \min\left(\left\lceil \frac{15000.0}{\text{effective\_px\_nm}} \right\rceil,\; \lfloor 0.15 \cdot \min(H, W) \rfloor\right)\right)$$
2. **Step Acquisition & Evaluation (Step $k \ge 1$)**:
   - Acquire new frame $I_k$.
   - Call `evaluate_tile_pair(I_{k-1}, I_k, \text{calib})`:
     - Downsample $I_{k-1}$ and $I_k$ to level $l^*$.
     - Subpixel register via `phase_cross_correlation(p_prev, p_curr, upsample_factor=10)`.
     - If $(\Delta y, \Delta x)$ within $s_{\text{max}}$, apply subpixel shift to $I_k$ and crop boundary margins.
     - Evaluate Pearson correlation:
       $$r = \frac{\sum (u - \bar{u})(v - \bar{v})}{\sqrt{\sum (u - \bar{u})^2 \sum (v - \bar{v})^2}}$$
       $$d = \max(0.0, 1.0 - r)$$
     - Declare contact if $d \ge d_{\text{trigger}}$.

## 2. Invariants & Mathematical Guarantees
- **Bounded Metrics**: $r \in [-1.0, 1.0]$, $d \in [0.0, 2.0]$.
- **Zero-Variance Stability**: Flat resin regions with $\sigma_u < 10^{-6}$ or $\sigma_v < 10^{-6}$ return $r = 0.0$ and do not cause division-by-zero crashes.
- **Scale Stability**: Limiting pyramid downsampling to $l^* \le 3$ preserves cut sensitivity while block-averaging eliminates Poisson noise.
- **Wander Support**: $s_{\text{max}}$ accommodates real mechanical drift up to $15\,\mu\text{m}$ between cut cycles without false zero-clamping.
