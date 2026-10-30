# Domain Knowledge: auto-approach-contact-fp

This document records physical insights, hardware constraints, electron optics dynamics, and empirical findings governing the Automated Approach false-positive fix and cut sensitivity.

## 1. Physical & SEM Imaging Dynamics
- **Poisson Shot Noise vs. Metric Scale**:
  - At full resolution ($1\times$), single-pixel shot noise has low SNR, causing pixel-to-pixel Pearson correlation of uncut frames to drop to $\sim 0.18 - 0.40$.
  - At $2\times$ downsampling ($2\times 2$ block averaging), noise variance is reduced by $4\times$ ($+6\,\text{dB}$ SNR).
  - Odd/even raster scan-line self-calibration evaluates SNR without requiring a second scan. When evaluating **Gradient SSIM** (Sobel 2nd-order differences), high-frequency beam noise is magnified, requiring $16\times$ downsampling (Level 4) before internal SSIM reaches $\ge 0.94$.
  - When evaluating **Pearson correlation** on the odd/even lines, linear averaging filters noise much earlier, achieving internal $r \ge 0.94$ ($d_{\text{noise}} \le 0.05$) at **Level 2 ($4\times$) or Level 3 ($8\times$)**.
- **Oversmoothing vs. Cut Sensitivity**:
  - At Level 4 ($16\times$ downsampling), a $3072 \times 4096$ frame becomes $192 \times 256$. Fine knife cuts, shallow resin shaving, and partial sample contact are blurred into low-frequency illumination gradients, artificially elevating Pearson $r$ to $0.76 - 0.83$ ($d \approx 0.165 - 0.238$).
  - At Level 2 ($4\times$) or Level 3 ($8\times$), the surface cut is resolved, yielding $d \in [0.263, 0.411]$ on Step 1, clearly distinguishable from baseline noise ($d_{\text{noise}} \approx 0.05$).

## 2. Hardware Quirks & Stage Drift Dynamics
- **Physical Mechanical Wander**:
  - Between cutting cycles, the microtome arm and stage move continuously. Physical mechanical translation can reach up to $10 - 12\,\mu\text{m}$ ($250 - 300\,\text{px}$ at $40\,\text{nm}$ pixel size), as observed in production run `171229` ($\Delta y \approx 274\,\text{px}, \Delta x \approx 235\,\text{px}$).
  - The previous clamp in `compute_stage_clamp_px()` had a hardcoded $5000\,\text{nm}$ ($5\,\mu\text{m}$) wander ceiling. At Level 2, $5\,\mu\text{m}$ equals only $31\,\text{px}$ ($124\,\text{px}$ full resolution), causing valid physical drift of $11\,\mu\text{m}$ to exceed `s_max` and get zeroed to $(0, 0)$.
  - Expanding the physical wander ceiling to $15000\,\text{nm}$ ($15\,\mu\text{m}$) allows phase cross correlation to accurately register physical stage movement up to $375\,\text{px}$ (or $15\%$ of image dimension).

## 3. Mathematical & Algorithmic Principles
- **Multi-Scale Contrast Matrix (Production Validation Data)**:
  - **Air Runs (No Cut, Stage Drift & Charging Only)**:
    - Level 4 ($16\times$): $d \le 0.106$
    - Level 3 ($8\times$): $d \le 0.169$ (max across all runs/tiles; typical $\le 0.108$)
    - Level 2 ($4\times$): $d \le 0.195$ (typical $\le 0.158$)
  - **Production Cut Run 171229 (Real Knife Contact)**:
    - Step 1 (first 3 cuts, shallow/initial cut):
      - Tile `0.146`: Level 2 $d = 0.2627$; Level 3 $d = 0.2063$; Level 4 $d = 0.1653$
      - Tile `0.161`: Level 2 $d = 0.3042$; Level 3 $d = 0.2606$; Level 4 $d = 0.2156$
      - Tile `0.162`: Level 2 $d = 0.4113$; Level 3 $d = 0.3194$; Level 4 $d = 0.2379$
    - Step 2 (cuts 4..6, deep cut):
      - Tile `0.146`: Level 2 $d = 0.5564$; Level 3 $d = 0.5159$; Level 4 $d = 0.4858$
- **Trigger Threshold Calibration**:
  $$d_{\text{trigger}} = \min(\max(4.0 \cdot d_{\text{noise}},\; 0.270),\; 0.650)$$
  - With floor $0.270$, all air runs across Levels 2-4 remain safely below threshold (max observed air dissimilarity $0.2620 < 0.270$).
  - On Step 1 of `171229`, Tiles `0.161` ($d = 0.2731$) and `0.162` ($d = 0.3008$) both cross $0.270$, triggering immediate contact detection on Step 1.
