# Asynchronous Mirror Drive Copying Architecture

## 1. Overview & Problem Statement

During Serial Block-Face SEM (SBEM) acquisitions, acquired tile images and metadata can be mirrored to a secondary storage location (typically a network-attached storage or institutional file server) for real-time redundancy and off-site backup.

### The Legacy Limitation
In the original implementation, file copying to the mirror drive occurred synchronously inside the critical acquisition loop:
```python
# Legacy synchronous copy inside tile loop:
start_time = time()
self.mirror_files([save_path])
mirror_duration = time() - start_time
```
Whenever the network experienced latency spikes, bandwidth throttling, or SMB/NFS filesystem lock contention, the acquisition thread was directly blocked. This produced several issues:
- **Acquisition Stalls**: Total slice acquisition times increased by 10%–50% purely waiting on network I/O.
- **Beam Dwell / Drift Risk**: Pausing execution during acquisition cycles can introduce stage drift or unintended beam exposure.
- **Wasted Duty Cycle**: The microscope stage motor movement to the next tile coordinate was delayed until network file transfer completed, despite stage motion and disk copying being completely independent hardware tasks.

---

## 2. Architecture & Concurrency Model

The redesigned mirroring subsystem offloads network I/O to an asynchronous, bounded worker thread that overlaps file transfers with subsequent microscope operations.

```
[Main Acquisition Thread]
         |
    Acquire Tile
         |
    Enqueue (save_path) ---> [_mirror_queue (maxsize=50)]
         |                                  |
    Move Stage to Next Tile                 v
    (Motor travel time ~1.5s)     [_mirror_worker Thread]
         |                                  |
    Acquire Next Tile             Copy File to Mirror Drive (SMB/NFS)
```

### 2.1 Component Details
1. **Worker Thread (`_mirror_worker`)**:
   A dedicated daemon thread (`threading.Thread(name='MirrorWorker', daemon=True)`) running a continuous dequeue loop.
2. **Bounded Queue (`_mirror_queue`)**:
   A thread-safe `queue.Queue(maxsize=50)` storing tuple payloads `(file_list, timed)`. The bounded buffer exerts backpressure if mirror storage hangs, preventing infinite memory accumulation.
3. **Overlapped Execution**:
   Enqueuing takes $< 0.1\text{ ms}$. The physical file copy proceeds in the background while the acquisition thread executes stage motor translation (`stage.move_to_xy`), settling delays, and next-tile beam preparation.

---

## 3. Synchronization & Lifecycle Management

### 3.1 Worker Startup & Teardown
- **Initialization**: Triggered in `run_acquisition` if `self.use_mirror_drive` is active via `start_mirror_worker()`.
- **Termination**: `stop_mirror_worker()` flushes all remaining items via `flush_mirror_queue()`, puts a `None` sentinel value into the queue to exit the loop, and joins the worker thread with a 60-second safety timeout.
- **Guaranteed Cleanup**: Encapsulated in a `try ... finally: self.stop_mirror_worker()` block inside `run_acquisition()` ensuring thread termination even in the event of unexpected exceptions or user aborts.

### 3.2 Inter-Grid Flush
At the completion of each grid, average duration metrics are displayed in the user interface and log:
```python
if self.use_mirror_drive:
    self.flush_mirror_queue()
```
`flush_mirror_queue()` invokes `_mirror_queue.join()`, ensuring all pending tile copies from the grid are completed before calculating `mean(self.tile_mirror_durations)`.

### 3.3 Thread-Safe Performance Tracking
Durations for individual file copies are recorded for warning alerts (copies exceeding 1.5 seconds):
```python
with self._mirror_lock:
    self.tile_mirror_durations.append(mirror_duration)
```
Protected via `self._mirror_lock = threading.Lock()` to prevent race conditions between worker recording and main thread metrics aggregation.

### 3.4 Synchronous Session Logs Copy
Session-level summaries (`main_log`, `incident_log`, `metadata`) must be copied only after the entire stack run finishes and the worker thread is cleanly shut down. These are handled synchronously via `_do_mirror_copy()` directly on the main thread after `stop_mirror_worker()` has joined.
