# focus-stig-to-ov — Clarifications [IMMUTABLE]

## Metadata [IMMUTABLE]
- **PRD:** `prd.md`
- **Slice folder:** `docs/feature-architecture/focus-stig-to-ov/`

## Mandatory Questions [IMMUTABLE]
<!-- Ask and log answers before PRD edits. Record outcomes in the Log below. -->
1. Feature context: Greenfield, Brownfield, or Migration?
2. Platform context: Existing stack or New stack?
3. Tech decision posture: Fixed, Bounded, or Open (and ADL link if not Fixed)?
4. Existing consumers and compatibility expectation: must keep, best-effort, or break allowed?
5. Migration/rollout needs: cutover, phased, feature flag, and rollback plan?
6. Stack constraints (Platform Context: Existing): mandated stack/tools and standards?
7. Versioning/contract stability: no public changes or versioned change?
8. Data migration required or none?

---

## Log [LOG]

### CL-FSO-001: Feature direction and core problem
- **Q:** What is the core problem this feature solves?
- **A:** Today, the user must manually re-focus and re-stigmate the OV (overview) camera each time SBEMimage needs to image at OV magnification. The feature should **copy stored WD (working distance) + stig XY values from the first active tile of a tile-grid** to the OV's internal SBEMimage settings, so the OV images with the same beam settings as the first tile of its associated grid.
- **Outcome:** Updated feature objective in `prd.md` §1. Direction is tile-grid → OV (not OV → tile).

### CL-FSO-002: Feature context
- **Q:** Greenfield, Brownfield, or Migration?
- **A:** Brownfield — extending an existing codebase with new functionality.
- **Outcome:** No new architectural patterns required; extend existing OV and grid-manager modules.

### CL-FSO-003: Parameters transferred
- **Q:** Which beam/optics parameters are transferred?
- **A:** Both **WD (working distance / focus)** and **stigmation XY** together.
- **Outcome:** Both fields must be read from grid tile config and written to OV config.

### CL-FSO-004: Source of values
- **Q:** Are values live-measured or read from stored config?
- **A:** Read from **stored SBEMimage tile config** (values saved from a previous manual focus session at tile position). No live SmartSEM measurement triggered by this feature.
- **Outcome:** No sem_api calls in the transfer path; pure config-layer copy.

### CL-FSO-005: Write target
- **Q:** When values are "applied to the OV", does that mean a live SmartSEM write or just updating internal config?
- **A:** **Only update the internal SBEMimage config/state** for the OV. No live SmartSEM write at transfer time. The SEM will use the updated OV config when the OV next needs to image.
- **Outcome:** Feature is a config-layer operation only. No sem_api in critical path.

### CL-FSO-006: Multiple OVs / multiple grids
- **Q:** Which OV gets updated when multiple OVs and grids exist?
- **A:** **Per-OV assignment**: each OV gets the WD+stig values from the first active tile of its associated tile-grid.
- **Outcome:** The mapping OV ↔ grid must be respected. Logic must iterate over all (OV, associated_grid) pairs.

### CL-FSO-007: AFSS guard condition
- **Q:** What if the first tile is an autofocus reference tile and AFSS is active?
- **A:** Do NOT transfer values if the first tile is selected as an AFSS reference tile AND the AFSS run is currently active (sweep in progress). Only apply new focus/stig if the AFSS run has **finished successfully** (the sweep is complete and whatever correction logic—global fit, average, etc.—has been applied).
- **Outcome:** Feature must inspect AFSS state before transferring. Guard condition documented as AC-FSO-004.

### CL-FSO-008: Missing values guard
- **Q:** What if the first active tile has no stored WD/stig?
- **A:** Skip silently — leave OV WD+stig unchanged.
- **Outcome:** Guard condition: if tile WD or stig is None/unset, log a warning and return without modifying OV config.

### CL-FSO-009: UI entry points
- **Q:** What are the UI entry points?
- **A:** **Both**:
  1. Manual button in the **OV settings tab** (`main_controls_dlg_windows.py`) — label TBD.
  2. Acquisition-time **checkbox** in the grid acquisition dialog — "Apply focus/stig from first tile before OV acquisition".
- **Outcome:** Two UI touch points; see `prd.md` §3.

### CL-FSO-010: Hardware interface investigation
- **Q:** How does SBEMimage communicate focus/stig values to the SEM?
- **A:** Needs investigation — the research agent will identify the sem_api getter/setter methods.
- **Outcome:** Blocked until codebase research is complete. Will update `knowledge.md`.

### CL-FSO-011: Primary files / entry points
- **Q:** Which files are the main entry points?
- **A:** `src/overview_manager.py` and/or `src/main_controls_dlg_windows.py` (OV-related controls).
- **Outcome:** Also likely `src/acquisition.py` / `src/acq_func.py` for the acquisition-time trigger.

### CL-FSO-012: Acceptance criteria
- **Q:** Provide or draft acceptance criteria?
- **A:** Draft from conversation for user review.
- **Outcome:** Draft ACs written in `prd.md` §5; user to review and correct.
