# Transcription Beam Runtime Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the visible Technical-mode beam-size control change the real Faster-Whisper transcription request for every file in the queued job.

**Architecture:** Represent Faster-Whisper request tuning as an immutable, Qt-independent `TranscriptionOptions` value. Snapshot the New Job control when a queue starts, then inject that value into each real `FasterWhisperTranscriber`; the backend adapter remains the only layer that knows Faster-Whisper keyword arguments.

**Tech Stack:** Python 3.11+, dataclasses, PySide6, Faster-Whisper adapter, pytest, pytest-qt.

## Global Constraints

- Windows 11 is the primary platform.
- Normal transcription and translation make no network requests.
- Every visible enabled control must have connected behavior, state handling, accessibility metadata, and automated coverage.
- Everyday and Technical modes operate on the same state and never discard values.
- Use unique `.pytest-runs\<timestamp>` directories with `--basetemp` and `-p no:cacheprovider` for local tests.
- The beam-size range remains 1 through 20 and defaults to 5.
- Do not change demo transcription behavior, queue concurrency, saved defaults, or model lifecycle behavior in this task.

---

### Task 1: Wire beam size from New Job to Faster-Whisper

**Files:**
- Modify: `src/quietcaption/transcription.py`
- Modify: `src/quietcaption/ui/main_window.py`
- Test: `tests/test_runtime.py`
- Test: `tests/test_product_ui.py`
- Test: `tests/test_control_contract.py`

**Interfaces:**
- Produces: immutable `TranscriptionOptions(beam_size: int = 5)` with range validation.
- Consumes: `NewJobView.beam_size.value()` when `MainWindow._start_jobs()` snapshots queue settings.
- Produces: `FasterWhisperTranscriber(model, compute, options=None)`, retaining the current default behavior when no options are supplied.

- [x] **Step 1: Write the failing backend behavior test**

Add a fake `faster_whisper.WhisperModel` in `tests/test_runtime.py` that records constructor and `transcribe` keyword arguments. Instantiate a transcriber with `TranscriptionOptions(beam_size=11)`, consume its returned segments, and assert the backend received `beam_size == 11` while `vad_filter` remains `True`.

- [x] **Step 2: Write the failing validation tests**

Assert `TranscriptionOptions(beam_size=1)` and `TranscriptionOptions(beam_size=20)` are accepted, while 0 and 21 raise `ValueError` containing `beam_size`.

- [x] **Step 3: Write the failing UI-to-adapter behavior test**

In `tests/test_product_ui.py`, construct a production-mode `MainWindow` with a fake active transcription model service, replace `FasterWhisperTranscriber` with a recording factory, set `new_job.beam_size` to 11, and start a one-file queue with a fake thread pool. Assert the recording factory receives `TranscriptionOptions(beam_size=11)`. Repeat the queue snapshot after changing the widget to 3 and assert the second factory receives 3, proving the visible value rather than a hard-coded constant controls runtime construction.

- [x] **Step 4: Verify RED**

Run the focused tests with a unique workspace-local base:

```powershell
$base = ".pytest-runs\$(Get-Date -Format 'yyyyMMdd-HHmmssfff')"
New-Item -ItemType Directory -Path $base -Force | Out-Null
try {
    .\.venv\Scripts\python.exe -m pytest -q tests\test_runtime.py tests\test_product_ui.py tests\test_control_contract.py --basetemp $base -p no:cacheprovider
} finally {
    if (Test-Path -LiteralPath $base) { Remove-Item -LiteralPath $base -Recurse -Force }
}
```

Expected: failures because `TranscriptionOptions` does not exist and the UI still constructs the transcriber without beam options.

- [x] **Step 5: Implement the immutable runtime options**

In `src/quietcaption/transcription.py`, add:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptionOptions:
    beam_size: int = 5

    def __post_init__(self) -> None:
        if not 1 <= self.beam_size <= 20:
            raise ValueError("beam_size must be between 1 and 20")
```

Update `FasterWhisperTranscriber.__init__` to accept `options: TranscriptionOptions | None = None`, store `options or TranscriptionOptions()`, and replace the hard-coded `beam_size=5` backend argument with `beam_size=self.options.beam_size`.

- [x] **Step 6: Snapshot and inject the visible control value**

In `src/quietcaption/ui/main_window.py`, import `TranscriptionOptions`. In `_start_jobs`, set:

```python
self._queue_transcription_options = TranscriptionOptions(
    beam_size=self.new_job.beam_size.value(),
)
```

When constructing the real transcriber in `_run_next_job`, pass `self._queue_transcription_options` as the third argument. The snapshot must be shared by every file in that queue so changing the widget mid-run cannot silently change later files.

- [x] **Step 7: Strengthen the control contract regression surface**

Add a targeted assertion or shared helper in `tests/test_control_contract.py` that treats the beam spinbox as behaviorally covered by the production-mode adapter-construction test. Do not broaden the task into a generic semantic audit of every widget.

- [x] **Step 8: Verify GREEN and regression safety**

Run the focused command from Step 4, then run the entire suite with a new unique `.pytest-runs` directory. Both commands must exit 0 and their disposable directories must be removed.

- [x] **Step 9: Commit**

Stage only the five task files plus this plan and `.superpowers/sdd/progress.md`, then commit:

```text
fix: wire transcription beam control
```

Do not merge to `main`.

## Self-review

- Spec coverage: this task covers only the existing visible beam control and deliberately leaves compute/fallback, queue concurrency, language defaults, cache, subtitle appearance, and diagnostics for subsequent reviewed tasks.
- Placeholder scan: no TBD/TODO or deferred implementation instruction appears inside the task scope.
- Type consistency: `TranscriptionOptions` is created in the UI coordinator and consumed unchanged by `FasterWhisperTranscriber`.
