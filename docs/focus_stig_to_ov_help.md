# Focus and Stigmation Transfer to Overviews (focus-stig-to-ov)

SBEMimage supports propagating working distance (focus) and stigmation ($X$ and $Y$) from high-magnification acquisition tile grids to their corresponding Overview (OV) images. This ensures that overview images remain sharp and in focus throughout long multi-day serial sectioning runs without requiring manual adjustment.

---

## Background & Mechanism

During serial block-face imaging, specimen surface height changes over time due to cutting, thermal drift, and stage settling. While active tile grids typically have autofocus routines or updated focus/stigmation settings, overview images historically maintained static working distance and stigmation values set during initial setup.

With this feature:
- Each Overview ($N$) inherits the stored working distance and stigmation $(X, Y)$ from the **first active tile** of its corresponding Tile Grid ($N$) via an implicit 1:1 mapping by index (OV 0 from Grid 0, OV 1 from Grid 1, etc.).
- The focus and stigmation settings are applied at the software configuration layer (`ov.wd_stig_xy`). The hardware microscope values are updated automatically when the overview is subsequently acquired.
- If Grid $N$ does not exist, is inactive, has no active tiles, has uninitialized working distance ($WD \le 0$), or if an autofocus/stigmation sweep (AFSS) is currently in progress on its reference tile, Overview $N$ is skipped and retains its existing settings.

---

## Operating Modes

### 1. Automated Pre-Overview Acquisition Sync (Default: ON)

During continuous serial acquisition, focus and stigmation can be synced automatically before overview images are recorded on each slice.

- **Location**: **Main Controls** $\rightarrow$ **Acquisition Settings** dialog.
- **Control**: **"Sync OV focus/stig from grids"** checkbox.
- **Behavior**:
  - When checked (enabled by default), `Acquisition.acquire_all_overviews()` invokes `apply_focus_stig_from_grids()` immediately prior to imaging overviews on each slice.
  - If any error occurs during sync, it is caught safely and logged without interrupting the acquisition sequence.

### 2. Manual On-Demand Transfer

You can manually pull the current focus and stigmation settings from the matching grid into the overview at any time during setup or inspection.

- **Location**: **Main Controls** $\rightarrow$ **Overview Setup** dialog (`OVSettingsDlg`).
- **Control**: **"Copy focus/stig from grid"** button (`pushButton_copyFocusStigFromGrid`).
- **Behavior**:
  - Clicking this button immediately inspects the matching grid and updates the focus and stigmation settings for the active overview.
  - A confirmation dialog displays the newly assigned Working Distance (in mm) and Stigmation $X/Y$ percentages.
  - If no matching active grid or valid tile focus values exist, an informative warning dialog explains why the transfer was skipped.

---

## Safety Guards

1. **AFSS Sweep Protection**:
   If Autofocus Slice-by-Slice (AFSS) is actively running (`af.afss_active == True`) and the first active tile is also configured as an autofocus reference tile, the transfer is suppressed to avoid copying transient or uncalibrated calibration values. Once AFSS completes and calibrated focus is locked in, subsequent transfers proceed normally.

2. **Non-Positive Value Filter**:
   Tiles with uninitialized or corrupted focus values ($WD \le 0.0$ or stigmation out of range) are rejected. The target overview retains its existing working distance and stigmation.

3. **Missing Grid / Tile Handling**:
   If an overview has no corresponding grid (e.g. Overview 2 defined but only Grids 0 and 1 exist), or if the grid has no active tiles enabled, the overview is cleanly skipped without warning popups or acquisition aborts.
