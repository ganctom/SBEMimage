# Implementation Plan - T-009 Non-Modal Tabbed ApproachDlg [MUTABLE]

## Metadata [MUTABLE]
- **Task ID:** T-009
- **Task Title:** Upgrade `ApproachDlg` (`gui/approach_dlg.ui`, `src/main_controls_dlg_windows.py`, `src/main_controls.py`) to Non-Modal Tabbed Dialog (`Manual` & `Automated` Tabs, Live-Synced `Reference tiles:` Input, Dwell Override, SSIM Mode Selector, `RESTRICT GUI`)
- **Agent:** `implementation-engineer`
- **PRD:** `1-prd.md`
- **ADL:** `2-adl.md`
- **Tasks:** `5-tasks.md`
- **AC IDs:** `AC-SBEM-AUTO_APPROACH-003`, `AC-SBEM-AUTO_APPROACH-006`
- Status: Completed

## Summary
Upgrade the SBEMimage approach interface to a non-modal tabbed dialog supporting both existing manual slice removal and automated touch-detection approach:
1. `gui/approach_dlg.ui`:
   - Set dialog modality to non-modal (`Qt::NonModal`).
   - Cross-platform UI loading: Loaded via `os.path.join(os.path.dirname(os.path.dirname(__file__)), 'gui', 'approach_dlg.ui')` (AR2-T009-007).
   - Introduce `QTabWidget` (`tabWidget`) containing two tabs:
     - Tab 0 (`tab_manual`, labeled "Manual"): Preserves all existing controls for blind slice removal (`spinBox_numberSlices`, `spinBox_thickness`, `progressBar_approach`, `label_statusApproach`, `pushButton_startApproach`, `pushButton_abortApproach`).
     - Tab 1 (`tab_automated`, labeled "Automated"): Provides controls for automated self-calibrating approach:
       - `lineEdit_refTiles`: Comma-separated probe tile indices (`g.t`), live-synced with `GridManager.approach_ref_tiles` per AD-AUTO_APPROACH-009 (no preset or clear buttons).
       - `spinBox_autoThickness`: Cutting thickness in nm (5–200, default 100 nm).
       - `spinBox_batchSlices`: Batch cuts per iteration (1–50, default 5 slices).
       - `doubleSpinBox_maxDepth`: Maximum approach depth in µm (0.1–500.0, default 20.0 µm).
       - `comboBox_dwellTimeOverride`: Dwell time override dropdown per PRD §2 (AR2-T009-002), populated with "Inherit from grid" (-1.0) and discrete SmartSEM dwell times from `self.sem.DWELL_TIME` (or `[0.05, 0.1, 0.2, 0.4, 0.8, 1.6, 3.2, 6.4, 12.8]` µs).
       - `comboBox_ssimMode`: SSIM Mode selector (index 0: "Normalized SSIM", index 1: "Gradient SSIM").
       - `progressBar_autoApproach`: Progress indicator (0–100%).
       - `label_statusAutoApproach`: Multi-field status label ("Step 0 / ~20 | Slices: 0 | Depth: 0.0 µm").
       - `pushButton_startAutoApproach`: Starts automated approach run.
       - `pushButton_abortAutoApproach`: Aborts active automated run (initially disabled).
   - Bottom `QDialogButtonBox` (`buttonBox`) with `Close` standard button.
2. `src/main_controls_dlg_windows.py`:
   - Upgrade `ApproachDlg`:
     - Update `__init__` signature to accept optional hardware/system dependencies: `def __init__(self, microtome, main_controls_trigger, sem=None, stage=None, grid_manager=None, cfg=None, base_dir=None):`.
     - Set window modality `self.setWindowModality(Qt.NonModal)`.
     - Retain backward compatibility: if `sem`, `stage`, `grid_manager`, `cfg` are omitted, disable the `Automated` tab and operate strictly in legacy `Manual` mode.
     - Isolate `Trigger` queue instance: Initialize `self.auto_progress_trigger = utils.Trigger()` and explicitly assign an isolated instance `self.auto_progress_trigger.queue = Queue()` to prevent poisoning the class-level `Trigger.queue` shared with `MainControls.trigger` (AR2-T009-001).
     - When `cfg` and `grid_manager` are provided, initialize `Automated` tab inputs from `self.cfg['approach']` and `self.grid_manager.approach_ref_tiles`, and restore active tab from `int(self.cfg['approach']['mode'])` (AR2-T009-003). Wire `tabWidget.currentChanged` to persist `self.cfg['approach']['mode'] = str(self.tabWidget.currentIndex())`.
     - Wire `lineEdit_refTiles.editingFinished` to update `self.grid_manager.approach_ref_tiles` safely.
     - Provide `sync_ref_tiles_from_grid_manager()` method for live external synchronization when tiles are toggled from Viewport right-click.
     - Enforce mutual exclusion across manual and automated modes (AR2-T009-005):
       - When manual `start_approach()` runs: disable `self.tabWidget`, `self.pushButton_startAutoApproach`, and Close button; emit `main_controls_trigger.transmit('STATUS BUSY APPROACH')` and `main_controls_trigger.transmit('RESTRICT GUI')`.
       - When manual `finish_approach()` completes: emit `main_controls_trigger.transmit('STATUS IDLE')` and `main_controls_trigger.transmit('UNRESTRICT GUI')`; re-enable `self.tabWidget`, inputs, and Close button.
     - Implement automated execution lifecycle:
       - `start_auto_approach()`: Validate probe tiles exist; save current UI parameters to `self.cfg['approach']` including `mode = '1'` (AR2-T009-003); disable conflicting inputs, `tabWidget`, `pushButton_startApproach`, and Close button; emit `main_controls_trigger.transmit('STATUS BUSY APPROACH')` and `main_controls_trigger.transmit('RESTRICT GUI')`; construct `AutoApproachConfig` and `AutoApproachEngine`; start worker thread via `utils.run_log_thread(self.auto_approach_thread)`.
       - `auto_approach_thread()`: Execute `self.auto_engine.run()`. Engine communicates progress exclusively via `progress_callback` posting `(progress, step_record)` to `self.auto_progress_trigger.queue` and emitting `self.auto_progress_trigger.signal.emit()`.
       - `update_auto_approach_progress()`: Main thread slot reading from `auto_progress_trigger.queue`; updates `progressBar_autoApproach` and `label_statusAutoApproach`.
       - `abort_auto_approach()`: Calls `self.auto_engine.request_abort()`, disables `pushButton_abortAutoApproach`.
       - `finish_auto_approach()`: Main thread slot called upon worker completion; transmits `'STATUS IDLE'` and `'UNRESTRICT GUI'`; re-enables inputs and `tabWidget`; displays completion dialog box reporting status, total slices cut, and depth removed.
     - Override both `closeEvent(self, event)` and `reject(self)` (AR2-T009-004): ignore window close and Esc key rejection if `self.approach_in_progress` or `self.auto_approach_in_progress` is active.
3. `src/main_controls.py`:
   - In `MainControls.__init__`, initialize `self.approach_dlg = None`.
   - Update `open_approach_dlg()`:
     - Check if `self.approach_dlg` exists and is visible; if so, raise and activate window.
     - Otherwise instantiate `ApproachDlg(self.microtome, self.trigger, sem=self.sem, stage=self.stage, grid_manager=self.gm, cfg=self.cfg, base_dir=self.cfg['acq']['base_dir'])`, store on `self.approach_dlg`, and call `self.approach_dlg.show()`.
4. Unit tests in `tests/test_auto_approach.py` (§1.4.5):
   - Add `test_approach_dlg_controller_and_progress_trigger()`:
     - Verify non-modal instantiation (`windowModality() == Qt.NonModal`).
     - Verify input population from `cfg['approach']` and bidirectional `approach_ref_tiles` synchronization.
     - Verify pre-flight guard blocking start when no probe tiles are configured.
     - Verify discrete dwell time dropdown selection mapping (AR2-T009-002).
     - Verify `mode` config persistence on tab switch (AR2-T009-003).
     - Verify `reject()` and `closeEvent()` block dialog dismissal while running (AR2-T009-004).
     - Verify mutual exclusion: manual run disables automated tab, automated run disables manual tab (AR2-T009-005).
     - Verify `'RESTRICT GUI'` and `'STATUS BUSY APPROACH'` emitted on Start; verify `'UNRESTRICT GUI'` and `'STATUS IDLE'` emitted on Finish.
     - Verify isolated `auto_progress_trigger.queue` prevents corruption of `MainControls.trigger.queue` (AR2-T009-001).
     - Verify thread-safe `progress_callback` puts `(progress, step_record)` onto `auto_progress_trigger.queue` and slot updates GUI on main thread without cross-thread widget access.
     - Verify abort invocation calls `engine.request_abort()`.
     - Verify `MainControls.open_approach_dlg()` instantiates non-modally, forwards dependencies, and raises existing dialog on subsequent calls (AR2-T009-006).

## Targets, Tests, Done When [MUTABLE]
- **Targets:** `gui/approach_dlg.ui`, `src/main_controls_dlg_windows.py`, `src/main_controls.py`
- **Tests:** `tests/test_auto_approach.py`
- **Done when:** `~/miniforge3/envs/sbem-py37/bin/python agent_test.py tests/test_auto_approach.py` passes with zero errors; `ApproachDlg` functions as a non-modal tabbed dialog; probe tiles sync bidirectionally with `GridManager.approach_ref_tiles`; worker thread drives `AutoApproachEngine` without freezing or touching Qt from secondary threads; GUI emits `RESTRICT GUI` / `UNRESTRICT GUI`; and legacy manual mode remains 100% operational.

## Steps [MUTABLE]
- [x] T-009.1 **[implementation-engineer]** Update `gui/approach_dlg.ui` to non-modal modality (`Qt::NonModal`), add `QTabWidget` with `Manual` and `Automated` tabs, preserving legacy manual controls on Tab 0, and adding probe tiles, batch cuts, slice thickness, max depth, dwell time override dropdown (`comboBox_dwellTimeOverride`, AR2-T009-002), SSIM mode selector, progress bar, status label, start button, and abort button on Tab 1.
- [x] T-009.2 **[implementation-engineer]** Upgrade `ApproachDlg.__init__` in `src/main_controls_dlg_windows.py`:
  - Resolve UI path via `os.path.join(os.path.dirname(os.path.dirname(__file__)), 'gui', 'approach_dlg.ui')` (AR2-T009-007).
  - Configure `self.setWindowModality(Qt.NonModal)`.
  - Accept optional `sem`, `stage`, `grid_manager`, `cfg`, `base_dir` parameters; if omitted, disable `tab_automated`.
  - Isolate trigger queue via `self.auto_progress_trigger = utils.Trigger()` and `self.auto_progress_trigger.queue = Queue()` (AR2-T009-001).
  - Populate fields from `cfg['approach']` including `mode` tab restoration (`self.tabWidget.setCurrentIndex(int(self.cfg['approach']['mode']))`, AR2-T009-003) and dwell time dropdown options (`self.sem.DWELL_TIME`, AR2-T009-002).
  - Bind signal slots (`tabWidget.currentChanged`, `editingFinished`, `clicked`).
- [x] T-009.3 **[implementation-engineer]** Implement bidirectional probe tile sync in `ApproachDlg` (`src/main_controls_dlg_windows.py`): parse comma-separated tile keys on edit to update `self.grid_manager.approach_ref_tiles` and `self.cfg['approach']['probe_tiles']`, and provide `sync_ref_tiles_from_grid_manager()` for live updates from external components (e.g. Viewport).
- [x] T-009.4 **[implementation-engineer]** Implement execution lifecycle and mutual exclusion in `ApproachDlg` (`src/main_controls_dlg_windows.py`):
  - Manual execution (`start_approach` / `finish_approach`): disable/re-enable `self.tabWidget` and `pushButton_startAutoApproach`; emit `RESTRICT GUI` on start and `UNRESTRICT GUI` on finish (AR2-T009-005).
  - Automated execution:
    - `start_auto_approach(self)`: Validate probe tile presence, persist settings to `cfg['approach']` including `mode = '1'` (AR2-T009-003), lock `tabWidget`, `pushButton_startApproach`, and inputs, transmit `'STATUS BUSY APPROACH'` and `'RESTRICT GUI'`, construct `AutoApproachConfig` and `AutoApproachEngine`, launch worker thread via `utils.run_log_thread(self.auto_approach_thread)`.
    - `auto_approach_thread(self)`: Run `self.auto_engine.run()`. Engine callback posts `(progress, step_record)` to `self.auto_progress_trigger.queue` and emits signal.
    - `update_auto_approach_progress(self)`: Pop from queue on main thread, update progress bar percentage and multi-field status label.
    - `abort_auto_approach(self)`: Request engine abort via `self.auto_engine.request_abort()`, disable abort button.
    - `finish_auto_approach(self)`: Transmit `'STATUS IDLE'` and `'UNRESTRICT GUI'`, unlock UI, report summary in modal message box.
  - Guards: Override both `closeEvent(self, event)` and `reject(self)` to block dismissal while manual or automated approach is running (AR2-T009-004).
- [x] T-009.5 **[implementation-engineer]** Update `MainControls` in `src/main_controls.py`: initialize `self.approach_dlg = None` in `__init__`, and update `open_approach_dlg()` to instantiate/show `ApproachDlg` non-modally and bring to front if already open.
- [x] T-009.6 **[implementation-engineer]** Add unit tests in `tests/test_auto_approach.py` (§1.4.5) in method `test_approach_dlg_controller_and_progress_trigger()`:
  - Non-modal instantiation, UI path loading, and input loading from `cfg['approach']`.
  - Mode persistence on tab change (AR2-T009-003).
  - Dwell time override dropdown discrete values (AR2-T009-002).
  - Bidirectional reference tile synchronization between `lineEdit_refTiles` and `GridManager.approach_ref_tiles`.
  - Pre-flight guard preventing start with empty probe tiles.
  - Mutual exclusion between manual and automated modes (AR2-T009-005).
  - Window rejection/closing block via `reject()` and `closeEvent()` while running (AR2-T009-004).
  - `RESTRICT GUI` / `UNRESTRICT GUI` and status transmission.
  - Thread-safe isolated trigger queue preventing class-level `Trigger.queue` corruption (AR2-T009-001).
  - Progress trigger queue dispatch and status label updates on main thread.
  - Clean abort signaling to `AutoApproachEngine`.
  - Controller test for `MainControls.open_approach_dlg()` non-modal singleton lifecycle (AR2-T009-006).
- [x] T-009.7 **[implementation-engineer]** Run bytecode pre-flight check (`~/miniforge3/envs/sbem-py37/bin/python -m py_compile src/main_controls_dlg_windows.py src/main_controls.py tests/test_auto_approach.py`) and verify green test suite via `~/miniforge3/envs/sbem-py37/bin/python agent_test.py tests/test_auto_approach.py`.
- [x] T-009.8 **[implementation-engineer]** Update `docs/feature-architecture/auto-approach/5-tasks.md` to mark `[x]` for T-009, update status to `*Status: Completed*`, and set `Status: Completed` in `6-plan-T009.md:11`.

## File Permissions
- MODIFY: `gui/approach_dlg.ui`
- MODIFY: `src/main_controls_dlg_windows.py`
- MODIFY: `src/main_controls.py`
- MODIFY: `tests/test_auto_approach.py`
- MODIFY: `docs/feature-architecture/auto-approach/5-tasks.md`
- MODIFY: `docs/feature-architecture/auto-approach/6-plan-T009.md`

## Types / methods / interfaces
- `src/main_controls_dlg_windows.py`:
  - `ApproachDlg.__init__(self, microtome, main_controls_trigger, sem=None, stage=None, grid_manager=None, cfg=None, base_dir=None)`
  - `ApproachDlg.sync_ref_tiles_from_grid_manager(self) -> None`
  - `ApproachDlg.update_ref_tiles_from_text(self) -> None`
  - `ApproachDlg.start_auto_approach(self) -> None`
  - `ApproachDlg.auto_approach_thread(self) -> None`
  - `ApproachDlg.auto_approach_progress_callback(self, progress: ApproachProgress, step_record: Optional[ApproachStepRecord]) -> None`
  - `ApproachDlg.update_auto_approach_progress(self) -> None`
  - `ApproachDlg.abort_auto_approach(self) -> None`
  - `ApproachDlg.finish_auto_approach(self) -> None`
  - `ApproachDlg.closeEvent(self, event: QCloseEvent) -> None`
  - `ApproachDlg.reject(self) -> None`
- `src/main_controls.py`:
  - `MainControls.approach_dlg: Optional[ApproachDlg]`
  - `MainControls.open_approach_dlg(self) -> None`

## Data / contracts
- Modality: Non-modal (`Qt.NonModal`), single instance per session.
- Live Reference Tile Format: comma-separated tile keys in `lineEdit_refTiles` (e.g. `'0.0, 0.2'`), parsed into `List[str]`. Out-of-bounds keys are filtered out by `GridManager.approach_ref_tiles.setter`.
- Config Mapping:
  - `cfg['approach']['mode']` <-> `str(tabWidget.currentIndex())` (AR2-T009-003)
  - `cfg['approach']['slice_thickness']` <-> `str(spinBox_autoThickness.value())`
  - `cfg['approach']['batch_slices']` <-> `str(spinBox_batchSlices.value())`
  - `cfg['approach']['max_depth_um']` <-> `str(doubleSpinBox_maxDepth.value())`
  - `cfg['approach']['dwell_time_override']` <-> `str(comboBox_dwellTimeOverride.currentData())` (AR2-T009-002)
  - `cfg['approach']['ssim_mode']` <-> `str(comboBox_ssimMode.currentIndex())`
  - `cfg['approach']['probe_tiles']` <-> `json.dumps(self.grid_manager.approach_ref_tiles)`
- GUI Locking Invariant: When either manual or automated approach is running:
  - Transmit `'STATUS BUSY APPROACH'` and `'RESTRICT GUI'`.
  - Disable tab bar switching, inputs, and Close button.
  - Enable only the matching `Abort` button.
  - On finish/abort, transmit `'STATUS IDLE'` and `'UNRESTRICT GUI'` and re-enable inputs.
- Thread Safety Invariant: `AutoApproachEngine` runs on a background worker thread. Secondary thread MUST NOT access or modify Qt widgets. All UI updates pass through isolated `self.auto_progress_trigger.queue` (not shared class attribute, AR2-T009-001) and Qt signal/slot mechanism.
- Backward Compatibility: When instantiated with legacy arguments `ApproachDlg(self.microtome, self.trigger)`, the dialog disables the `Automated` tab and provides 100% existing functionality for `Manual` blind slicing.

## Side-effects / risks
- Class-level queue poisoning: Resolved by explicitly assigning `self.auto_progress_trigger.queue = Queue()` on instance initialization (AR2-T009-001).
- Unhandled SmartSEM dwell times: Resolved by using `comboBox_dwellTimeOverride` populated from `self.sem.DWELL_TIME` (AR2-T009-002).
- Modal bypass via Esc key: Resolved by overriding `reject(self)` to ignore dismissal during active runs (AR2-T009-004).
- Conflicting simultaneous runs: Resolved by disabling `tabWidget` and opposite start buttons during runs (AR2-T009-005).
