# Implementation Plan - T-006 Wire Live Activation & AFSS Memory Fallback [MUTABLE]

## Metadata [MUTABLE]
- **Task ID:** T-006
- **Task Title:** Wire Live Activation, Configuration Update, and AFSS Memory Fallback
- **Agent:** 08-implementation-engineer
- **PRD:** `prd.md`
- **ADL:** `focus-stig-to-ov_architecture.md`
- **Tasks:** `tasks.md`
- Status: Completed
- **AC IDs:** AC-FSO-004, AC-FSO-008

## Summary
Wire the checkbox in AutofocusSettingsDlg to update configuration live and propagate OV settings in memory without sending commands to the SEM. When AFSS is active on an autofocus reference tile, retrieve unperturbed settings from AFSS memory. Suppress transfer log messages while logging user activation/deactivation.

## Targets, Tests, Done When [MUTABLE]
- **Targets:** `src/main_controls_dlg_windows.py`, `src/main_controls.py`, `src/overview_manager.py`
- **Tests:** `tests/test_focus_stig_to_ov.py`
- **Done when:** `~/miniforge3/envs/sbem-py37/bin/pytest tests/test_focus_stig_to_ov.py` passes cleanly on Python 3.7.6.

## Steps [MUTABLE]
- [x] T-006.1 Wire checkbox state signal to update config in memory and trigger `apply_focus_stig_from_grids`.
- [x] T-006.2 Pass `ovm` and `cfg` to `AutofocusSettingsDlg` in `src/main_controls.py`.
- [x] T-006.3 Implement fallback to `afss_wd_stig_orig` during active AFSS sweeps on reference tiles in `src/overview_manager.py`.
- [x] T-006.4 Suppress focus/stig transfer log messages from GUI and disk logs, retaining only user action logging.
- [x] T-006.5 Add unit and integration tests covering live toggle, AFSS unperturbed memory transfer, and quiet log behavior.
