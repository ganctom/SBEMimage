# Domain Knowledge: auto-approach-contact-fp

This document records physical insights, hardware constraints, electron optics dynamics, and empirical findings governing the Automated Approach false-positive fix.

## 1. Physical & SEM Imaging Dynamics
- **Poisson Shot Noise vs. Scale**:
  - At full resolution ($1\times$), single-pixel shot noise has low SNR, causing pixel-to-pixel Pearson correlation of uncut frames to drop to $\sim 0.18$.
  - At $2\times$ downsampling ($2\times 2$ block averaging), noise variance is reduced by $4\times$ ($+6\,\text{dB}$ SNR), while preserving cellular membranes, organelle boundaries, and fine tissue features.
  - At $16\times$ downsampling ($l=4$), structural edges are obliterated, and high-frequency noise is replaced by low-frequency charging and illumination gradients.
- **Edge Distortions in SEM**:
  - Deflector non-linearities and aperture vignetting produce edge gradients near frame boundaries.
  - Cropping out the outer 15% from all four borders retains the high-fidelity central 70% ($49\%$ area), eliminating edge boundary artifacts during Fourier phase correlation.

## 2. Hardware Quirks & Stage Drift
- **Inter-Scan Stage Wander**:
  - During air approach, between Step $k-1$ and Step $k$ (5 cuts in air), the physical stage advances $500\,\text{nm}$ in $Z$ and experiences $0.5 - 2.0\,\mu\text{m}$ ($10 - 50$ px at $40\,\text{nm}$ pixel size) of mechanical drift in XY.
  - In production run `151539`, stage drift reached $(-184, -132)$ pixels.
  - Phase correlation at $2\times$ downsampling with a 15% edge crop accurately locks onto this physical drift ($0.2\,\text{px}$ subpixel precision), matching OpenCV template matching exactly.
- **Quantization Breakdown at $16\times$ Downsampling**:
  - At $16\times$, 1 px at level 4 equals $16\text{ px}$ at full resolution.
  - Subpixel refinement at $10\times$ yields $0.1 \times 16 = 1.6\text{ px}$ full-res quantization.
  - Subpixel drift $< 1.5\text{ px}$ is rounded to zero, producing false misalignment.

## 3. Mathematical & Algorithmic Principles
- **2x Center-Crop Registration**:
  $$P(I)[i, j] = \frac{1}{4} \sum_{u=0}^1 \sum_{v=0}^1 I[2i+u, 2j+v]$$
  $$C(P) = P[\lfloor 0.15 H_{2x} \rfloor : \lceil 0.85 H_{2x} \rceil,\; \lfloor 0.15 W_{2x} \rfloor : \lceil 0.85 W_{2x} \rceil]$$
  $$(\Delta y_{2x}, \Delta x_{2x}) = \text{phase\_cross\_correlation}(C(P_{\text{prev}}), C(P_{\text{curr}}), \text{upsample\_factor}=10)$$
  $$(\Delta y_{\text{full}}, \Delta x_{\text{full}}) = (2 \cdot \Delta y_{2x},\; 2 \cdot \Delta x_{2x})$$
- **Similarity Metric Comparison (Cuts vs. Missed Cuts on `roli-f1`)**:
  - Local SSIM ($2\times$): Missed cuts $0.465 - 0.624$; Real cuts $0.013 - 0.441$. Separation gap is only $\approx \mathbf{0.02}$.
  - Global Pearson $r$ ($2\times$): Missed cuts $0.743 - 0.849$; Real cuts $0.036 - 0.544$. Separation gap is $\mathbf{0.20}$ ($10\times$ wider margin).
  - Normalized $L_1$ Residual: Missed cuts $0.438 - 0.560$; Real cuts $0.727 - 1.092$. Separation gap is $\mathbf{0.17}$.
