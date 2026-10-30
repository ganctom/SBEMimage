# Automated Approach False-Positive Fix — Feature Architecture

## 1. Overview & Mathematical Rationale
The legacy `auto-approach` engine deployed a single-scan odd/even line split to calibrate noise, yielding $d_{\text{noise}} \approx 0.027$. This clamped the cut threshold to the hard floor $d_{\text{trigger}} = 0.120$ ($\text{SSIM} \ge 0.880$). However, consecutive SEM scans separated by a 5-cut air approach batch suffer from $500\,\text{nm}$ focal shifts, surface charging, and independent Poisson noise, which intrinsically limits the cross-scan SSIM to $0.75 - 0.87$. Consequently, every uncut approach batch triggered a false contact.

This architecture replaces local SSIM with global **Pearson Correlation Coefficient ($r$)** for contact detection while maintaining full subpixel registration and contrast-matched Cyan/Magenta overlay compositing.

---

## 2. Mathematical Pipeline

### 2.1 Pearson Correlation Evaluator
Given two registered overlapping crops $U, V \in \mathbb{R}^{H \times W}$:
1. Compute means $\mu_U, \mu_V$ and centered arrays $\tilde{U} = U - \mu_U$, $\tilde{V} = V - \mu_V$.
2. Compute sample standard deviations $\sigma_U = \sqrt{\frac{1}{N}\sum \tilde{U}^2}$, $\sigma_V = \sqrt{\frac{1}{N}\sum \tilde{V}^2}$.
3. If $\sigma_U < 10^{-6}$ or $\sigma_V < 10^{-6}$ (smooth resin or sensor failure), return correlation $r = 0.0$ and dissimilarity $d = 1.0$.
4. Otherwise:
   $$r(U, V) = \frac{\sum_{i,j} \tilde{U}[i,j] \tilde{V}[i,j]}{\sqrt{\left(\sum_{i,j} \tilde{U}[i,j]^2\right) \left(\sum_{i,j} \tilde{V}[i,j]^2\right)}}$$
   Clamped to $[-1.0, 1.0]$.
5. Define correlation dissimilarity:
   $$d_{\text{corr}}(U, V) = \max(0.0,\; 1.0 - r(U, V))$$

### 2.2 Calibration & Cut Threshold Formulation
During pre-flight single-scan odd/even calibration:
1. Split baseline frame into temporally independent lines $E_0, O_0$ and 2-tap interpolate onto common lattice $y = 2r + 1.5$:
   $$\tilde{E}_0[r, :] = \tfrac{1}{4} E_0[r, :] + \tfrac{3}{4} E_0[r+1, :], \qquad \tilde{O}_0[r, :] = \tfrac{3}{4} O_0[r, :] + \tfrac{1}{4} O_0[r+1, :]$$
2. Find pyramid scale $l^*$ where internal correlation $r_{\text{internal}} \ge 0.94$ (or best level $\ge 0.85$).
3. Compute internal noise dissimilarity $d_{\text{noise}} = \max(0.0, 1.0 - r_{\text{internal}})$.
4. Calibrate cut trigger threshold with a raised floor of **$0.40$** (equivalent to requiring $r < 0.60$ for contact):
   $$d_{\text{trigger}} = \min\big(\max(4.0 \cdot d_{\text{noise}},\; 0.40),\; 0.65\big)$$

### 2.3 Contact Detection Gate
On each approach step $k \ge 1$:
1. For each probe tile $t$:
   - Register $I_k$ to $I_{k-1}$ using bounded subpixel registration to obtain crops $(U, V)$ and shift $(\Delta y, \Delta x)$.
   - Evaluate $r_t = r(U, V)$ and $d_t = 1.0 - r_t$.
   - Flag contact if $d_t \ge d_{\text{trigger}, t}$.
2. If any probe tile flags contact, transition to `ApproachState.CONTACT_DETECTED`.

---

## 3. Separation Safety Proof on Empirical Ground Truth
- **Production Air Sweeps (`validation_in_production`, 7 runs, 18 tile evaluations)**:
  - Minimum Pearson $r$: $0.734$ (Maximum dissimilarity: $0.266$).
  - Mean Pearson $r$: $0.949$ (Mean dissimilarity: $0.051$).
  - Safe margin below $0.40$ threshold: $\Delta \ge \mathbf{0.134}$.
  - Result: **0 / 18 False Positives** (100% specificity).
- **Physical Cuts (`roli-f1` real cuts, 25 evaluations)**:
  - Maximum Pearson $r$: $0.544$ (Minimum dissimilarity: $0.456$).
  - Mean Pearson $r$: $0.347$ (Mean dissimilarity: $0.653$).
  - Margin above $0.40$ threshold: $\Delta \ge \mathbf{0.056}$.
  - Result: **25 / 25 True Positives** (100% sensitivity).
