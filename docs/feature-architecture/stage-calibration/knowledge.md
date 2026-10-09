# Domain Knowledge: Microscope Stage Dynamics

This document stores critical context regarding the physical realities of the microscope stage and how it impacts the SBEMimage architecture.

## 1. Stage Precision Limits vs. Real Discrepancies
- **The Core Issue**: The real tile overlaps found after computing coarse offset vectors between tiles in a large tile-grid are often imprecise. 
- **Magnitude**: This discrepancy is frequently at least one magnitude larger than the known physical inaccuracy limits of the microscope stage itself. 
- **Conclusion**: The mathematical calibration model and its extrapolation across large areas are the primary sources of error, rather than purely random mechanical stage inaccuracy.

## 2. Geometric Distortions & Image Edges
- **Lens/Scan Distortion**: Images from the SEM suffer from geometric distortions that grow increasingly severe further from the image center.
- **Mitigation Strategy**: Cross-correlation for calibration shifts should never use the raw full frames. Images must be symmetrically cropped (e.g., retaining only the central 60%) prior to phase cross-correlation to ensure the calibration vectors are untainted by edge distortion.

## 3. Dwell Time Artifacts
- **Scan Dynamics**: Dwell time can impact the magnitude or behavior of geometric distortions. 
- **Testing**: A dwell-time selector is exposed in the calibration dialog specifically to prototype and analyze how scan speeds affect calibration precision. (This may be removed or automated once the distortion relationship is fully mapped).

## 4. Hardware Independence
- The stage calibration model must remain robust regardless of whether the backend is Zeiss, Tescan, or a mock simulator.

## 5. Mechanical Settling Time
- Physical microscope stages (especially ultramicrotome motor drives) exhibit residual mechanical drift immediately after arriving at a target position.
- A mandatory settle time (e.g., 0.6 seconds) must elapse before initiating frame capture to ensure the image buffer is crisp and free from motion blur or trailing displacements.

## 6. Axis Inversion & Angular Quadrants
- Certain microscope stages have motor polarity/axes inverted relative to the standard SEM image raster convention.
- When an axis is inverted, the unconstrained affine matrix extraction yields negative scale factors with rotation angles offset by $\pi$ radians ($180^\circ$).
- Mathematical equivalence: Inverting the sign of the scale factor while shifting both $\theta_x$ and $\theta_y$ by $\pm \pi$ yields the exact identical coordinate transformation matrix while satisfying the downstream requirement for positive scale factors ($s_x, s_y \in [0.1, 10.0]$) and matching physical stage angle expectations.
