# Architecture: fix/auto-approach-contact-fp

## 1. System Context & Pipeline
The Automated Approach (`auto-approach`) algorithm operates cyclically during SEM-microtome approach:

1. **Preprocessing Pipeline**:
   - Every input approach frame $I$ (baseline or subsequent step) passes through:
     $$\tilde{I} = \text{CLAHE}\Big(\text{Gaussian}(I,\, \sigma=1.0),\, \text{clipLimit}=2.0,\, \text{tileGridSize}=(8, 8)\Big)$$
   - Gaussian smoothing suppresses Poisson shot noise without blurring 25 nm cellular edges.
   - CLAHE equalizes local contrast across $8\times8$ contextual tiles, stripping macro-illumination/stain gradients and enhancing ultrastructure boundaries.

2. **Calibration (Step 0)**:
   - For each designated probe tile, acquire baseline frame $I_0$ and compute preprocessed $\tilde{I}_0$.
   - Run `calibrate_tile_single_scan(I_0, pixel_size_nm, ssim_mode, tile_key)`:
     - Split raw baseline frame $I_0$ into even and odd scan-lines $E[r]$ and $O[r]$ on lattice $y = 2r + 1.5$.
     - Interpolate to symmetric line lattice:
       $$\tilde{E}[r] = \frac{1}{4} E[r] + \frac{3}{4} E[r+1],\quad \tilde{O}[r] = \frac{3}{4} O[r] + \frac{1}{4} O[r+1]$$
     - Decompose image variance into detector noise variance and specimen structural variance:
       $$\sigma_{\text{noise}}^2 = \frac{1}{2} \text{Var}(\tilde{E} - \tilde{O})$$
       $$\sigma_{\text{total}}^2 = \text{Var}(I_0)$$
       $$\sigma_{\text{struct}}^2 = \max\Big(0.0,\, \sigma_{\text{total}}^2 - \sigma_{\text{noise}}^2\Big)$$
     - Compute the dimensionless **structural contrast ratio**:
       $$\gamma_{\text{struct}} = \frac{\sigma_{\text{struct}}}{\sigma_{\text{total}} + \epsilon} \in [0.0, 1.0]$$
     - Evaluate odd/even noise dissimilarity on preprocessed scan-lines:
       $$d_{\text{noise}} = \max\Big(0.0,\, 1.0 - \text{Pearson}(\tilde{E}_{\text{prep}},\, \tilde{O}_{\text{prep}})\Big)$$
     - Derive the **tile-specific dynamic cut dissimilarity threshold**:
       $$d_{\text{trigger}}(\text{tile}) = \text{clamp}\Big(0.35 + 7.5 \cdot (0.75 - \gamma_{\text{struct}}),\; 0.300,\; 0.660\Big)$$
       - High structural contrast tiles ($\gamma \ge 0.75$, e.g. Tile 0.146): $d_{\text{trigger}} = 0.300 - 0.350$ (Air $d \le 0.282$, Cut $d \ge 0.867$).
       - Medium structural contrast tiles ($\gamma \approx 0.74$, e.g. Tile 0.161): $d_{\text{trigger}} \approx 0.400 - 0.500$ (Air $d \le 0.361$, 25 nm Cut $d = 0.752$).
       - Low structural contrast / peripheral tiles ($\gamma \le 0.71$, e.g. Tile 0.162): $d_{\text{trigger}} = 0.550 - 0.650$ (Air $d \le 0.569$, Cut $d = 0.902$).
     - Compute stage wander clamp:
       $$s_{\text{max}} = \max\left(2,\; \min\left(\left\lceil \frac{15000.0}{\text{pixel\_size\_nm}} \right\rceil,\; \lfloor 0.15 \cdot \min(H, W) \rfloor\right)\right)$$

3. **Step Acquisition & Evaluation (Step $k \ge 1$)**:
   - Acquire new frame $I_k$ and compute $\tilde{I}_k$.
   - Call `evaluate_tile_pair(\tilde{I}_{k-1}, \tilde{I}_k, \text{calib})`:
     - Extract **10% center crop** from both frames:
       $$C_{\text{prev}} = \tilde{I}_{k-1}[0.10H:0.90H,\; 0.10W:0.90W],\quad C_{\text{curr}} = \tilde{I}_k[0.10H:0.90H,\; 0.10W:0.90W]$$
     - Compute subpixel shift on center crops:
       $$(\Delta y, \Delta x) = \text{phase\_cross\_correlation}(C_{\text{prev}},\, C_{\text{curr}},\, \text{upsample\_factor}=10)$$
     - Clamp to $(\Delta y, \Delta x) = (0, 0)$ if $|\Delta y| > s_{\text{max}}$ or $|\Delta x| > s_{\text{max}}$.
     - Apply $(\Delta y, \Delta x)$ shift to full preprocessed $\tilde{I}_k$ via nearest/linear interpolation.
     - Crop common overlapping valid window (margin $c_y = \lceil |\Delta y| \rceil + 1, c_x = \lceil |\Delta x| \rceil + 1$).
     - Evaluate Pearson correlation:
       $$r = \frac{\sum (u - \bar{u})(v - \bar{v})}{\sqrt{\sum (u - \bar{u})^2 \sum (v - \bar{v})^2}}$$
       $$d = \max(0.0, 1.0 - r)$$
     - Declare contact if $d \ge d_{\text{trigger}}$.

## 2. Invariants & Mathematical Guarantees
- **Bounded Metrics**: $r \in [-1.0, 1.0]$, $d \in [0.0, 2.0]$.
- **Zero-Variance Stability**: Flat resin regions with $\sigma_u < 10^{-6}$ or $\sigma_v < 10^{-6}$ return $r = 0.0$ and do not cause division-by-zero crashes.
- **Scale Stability**: Limiting pyramid downsampling to $l^* \le 3$ preserves cut sensitivity while block-averaging eliminates Poisson noise.
- **Wander Support**: $s_{\text{max}}$ accommodates real mechanical drift up to $15\,\mu\text{m}$ between cut cycles without false zero-clamping.
