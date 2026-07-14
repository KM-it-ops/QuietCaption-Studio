# Queue Runtime Snapshot and Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze every queue's output and model inputs at start, hold service-owned model-use leases for the queue lifetime, and make Generate truthfully reflect local production readiness.

**Architecture:** Add a Qt-independent immutable `ModelRuntime` plus idempotent `ModelUseLease` in `model_service.py`. `MainWindow` acquires all required runtimes before mutating queue/UI state, stores one immutable `QueueRuntimeSnapshot`, and releases leases on every terminal path. `NewJobView` owns only the button-state conjunction (files, readiness, idle); `MainWindow` supplies readiness from the same service resolver used at queue start.

**Tech Stack:** Python 3.11+, frozen dataclasses, `threading.RLock`, PySide6, pytest/pytest-qt.

## Global Constraints

- Follow `AGENTS.md`: every pytest command uses a unique `.pytest-runs\<timestamp>` base, `--basetemp`, and `-p no:cacheprovider`.
- Production-only CUDA preflight remains unchanged; demo queues never require models or leases.
- Preserve existing positional inference-adapter constructor slots and the completed compute/beam snapshots.
- Readiness is local-only: no download, repair, catalog refresh, activation, or benchmark.
- `force=True` may override active-model removal policy but never a live model-use lease.
- One queue-start attempt either creates the complete snapshot and leases before UI mutation or leaves queue/UI state untouched.

---

### Task 1: Atomic queue runtime snapshot, leases, and truthful Generate readiness

**Files:**
- Modify: `src/quietcaption/model_service.py`
- Modify: `src/quietcaption/ui/main_window.py`
- Modify: `src/quietcaption/ui/new_job.py`
- Test: `tests/test_model_service.py`
- Test: `tests/test_product_ui.py`
- Test: `tests/test_control_contract.py`
- Test: `tests/test_ui.py`
- Create: `.superpowers/sdd/task-queue-runtime-snapshot-report.md`

**Interfaces:**
- Produces: `ModelRuntime(descriptor: ModelDescriptor, path: Path)`.
- Produces: `ModelUseLease.runtimes: tuple[ModelRuntime, ...]`, `release() -> None`, and context-manager support; release is idempotent.
- Produces: `ModelService.acquire_runtime(kinds: tuple[str, ...]) -> ModelUseLease`; it validates active pointer, installed marker, manifest, and directory while holding one service lock.
- Produces: frozen `QueueRuntimeSnapshot` in `main_window.py` containing output directory, target/source/formats, compute config, transcription options, and optional model runtimes/lease.
- Produces: `NewJobView.set_runtime_ready(ready: bool, reason: str = "")` and `set_queue_running(running: bool)`; enabled state is `bool(files) and runtime_ready and not queue_running`.

- [ ] **Step 1: Write service RED tests for readiness and ownership**

Add local-fixture tests proving `acquire_runtime(("transcription",))` rejects missing pointers, missing installations, and malformed/missing manifests; returns the exact descriptor/path for a valid install; blocks `remove(..., force=True)`, `update`, `repair`, and `move` before filesystem mutation while leased; and permits removal after two calls to `lease.release()`.

Use a local descriptor and a helper that writes `.complete`, `manifest.json`, model bytes, and `active-transcription.json`. Never invoke the default fetcher.

- [ ] **Step 2: Run the service RED tests**

Run:

```powershell
$base = ".pytest-runs\$(Get-Date -Format 'yyyyMMdd-HHmmssfff')"
New-Item -ItemType Directory -Path $base -Force | Out-Null
try { .\.venv\Scripts\python.exe -m pytest -q tests/test_model_service.py -k "runtime or in_use" --basetemp $base -p no:cacheprovider } finally { if (Test-Path -LiteralPath $base) { Remove-Item -LiteralPath $base -Recurse -Force } }
```

Expected: FAIL because `ModelRuntime`, `ModelUseLease`, and `acquire_runtime` do not exist and mutations do not reject leased models.

- [ ] **Step 3: Implement the minimal service-owned runtime/lease contract**

In `model_service.py`, add frozen `ModelRuntime`, an idempotent lease whose `release()` decrements service-owned per-model counts under `RLock`, and `acquire_runtime`. Resolve every requested role first, validate the exact directory plus `.complete` and `manifest.json`, then increment all counts atomically. Add `_assert_not_in_use(*model_ids)` and call it before any staging/deletion in install/update/repair/remove and before any destination work in move. Do not make `active()` itself acquire a lease.

- [ ] **Step 4: Run the service GREEN tests**

Run the Step 2 command with a fresh base.

Expected: PASS; local bytes and active pointers remain unchanged on every in-use rejection.

- [ ] **Step 5: Write queue snapshot and readiness RED tests**

Add behavior tests with a recording thread pool/factories:

- a two-file demo queue keeps the original saved output directory after Settings is changed between workers;
- a two-file production queue keeps the original transcription and translation paths after active pointers and `registry.root` are changed between workers;
- production with files but no ready transcription model keeps Generate disabled and exposes accessible Models guidance; activation enables without re-adding files; translation selection without a ready translation model disables it;
- demo with files remains enabled without models, including unavailable-CUDA policy;
- completed, failed, cancelled, and adapter-construction-failure paths release the queue lease exactly once;
- compute config and `TranscriptionOptions` object identity remain stable across both files.

- [ ] **Step 6: Run the UI RED tests**

Run:

```powershell
$base = ".pytest-runs\$(Get-Date -Format 'yyyyMMdd-HHmmssfff')"
New-Item -ItemType Directory -Path $base -Force | Out-Null
try { .\.venv\Scripts\python.exe -m pytest -q tests/test_product_ui.py tests/test_ui.py tests/test_control_contract.py -k "snapshot or readiness or release or demo_queue" --basetemp $base -p no:cacheprovider } finally { if (Test-Path -LiteralPath $base) { Remove-Item -LiteralPath $base -Recurse -Force } }
```

Expected: FAIL because output/models are still resolved per file, Generate considers only files, and no lease cleanup exists.

- [ ] **Step 7: Implement one immutable queue-start transaction**

Add frozen `QueueRuntimeSnapshot`. In `_start_jobs()`, preserve the production compute preflight, then resolve output and acquire required model runtimes before setting `_pending_files`, navigating, or disabling controls. Store exact model paths and reuse them in `_run_next_job()` without calling `active()` or reading Settings. Centralize `_release_queue_runtime()` and call it from `_finish_queue`, `_failed`, `_cancelled`, and construction/preflight exception cleanup. In `NewJobView`, recompute Generate state from files/readiness/running and set an accessible reason/tool tip. `_sync_active_models()` must refresh both selectors and readiness; demo readiness is always true.

- [ ] **Step 8: Run focused GREEN verification**

Run the Step 6 command with a fresh base, then run:

```powershell
$base = ".pytest-runs\$(Get-Date -Format 'yyyyMMdd-HHmmssfff')"
New-Item -ItemType Directory -Path $base -Force | Out-Null
try { .\.venv\Scripts\python.exe -m pytest -q tests/test_model_service.py tests/test_product_ui.py tests/test_ui.py tests/test_control_contract.py tests/test_runtime.py tests/test_translation.py --basetemp $base -p no:cacheprovider } finally { if (Test-Path -LiteralPath $base) { Remove-Item -LiteralPath $base -Recurse -Force } }
```

Expected: all selected tests PASS with no network/model download.

- [ ] **Step 9: Record evidence and verify the whole repository**

Write `.superpowers/sdd/task-queue-runtime-snapshot-report.md` with exact RED/GREEN commands and outputs. Run the full suite with a fresh base, redirected compileall with a unique workspace-local `PYTHONPYCACHEPREFIX`, and `git diff --check`.

Expected: full suite PASS, compileall exit 0, diff check exit 0.

- [ ] **Step 10: Commit the approved slice**

After independent spec/code review reports no Critical or Important findings:

```powershell
git add src/quietcaption/model_service.py src/quietcaption/ui/main_window.py src/quietcaption/ui/new_job.py tests/test_model_service.py tests/test_product_ui.py tests/test_control_contract.py tests/test_ui.py .superpowers/sdd/task-queue-runtime-snapshot-report.md .superpowers/sdd/progress.md
git commit -m "fix: snapshot queue runtime inputs"
```

