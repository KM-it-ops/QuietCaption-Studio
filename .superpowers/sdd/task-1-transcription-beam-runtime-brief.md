# Task 1: Wire beam size from New Job to Faster-Whisper

Source plan: `docs/superpowers/plans/2026-07-14-transcription-beam-runtime.md`

## Requirements

- Add immutable, Qt-independent `TranscriptionOptions(beam_size: int = 5)` in `src/quietcaption/transcription.py`.
- Validate the inclusive beam range 1 through 20; invalid values raise `ValueError` containing `beam_size`.
- Extend `FasterWhisperTranscriber(model, compute, options=None)` without breaking callers that omit options.
- Pass `self.options.beam_size` to Faster-Whisper while retaining `vad_filter=True`.
- Snapshot `NewJobView.beam_size.value()` once in `MainWindow._start_jobs()` and reuse that options object for every file in the queue.
- Pass the snapshot into every production `FasterWhisperTranscriber`; do not change demo behavior.
- Add behavioral tests in `tests/test_runtime.py` and `tests/test_product_ui.py` that prove beam values reach the backend/adapter construction.
- Strengthen `tests/test_control_contract.py` only with a targeted beam-behavior contract; do not broaden this task into a generic semantic audit.
- Follow strict RED/GREEN TDD and record commands plus relevant failure/pass output in `.superpowers/sdd/task-1-transcription-beam-runtime-report.md`.
- Every pytest command must use a unique `.pytest-runs\<timestamp>` base, `--basetemp`, and `-p no:cacheprovider`, then remove only that run directory.
- Run focused tests during iteration and the full suite once before commit.
- Commit only task files, this brief/plan, the progress ledger update, and the generalized AGENTS.md learning with message `fix: wire transcription beam control`.
- Do not push or merge.

## Global constraints

- Windows 11 is the primary platform.
- Normal transcription and translation make no network requests.
- Every visible enabled control must have connected behavior, state handling, accessibility metadata, and automated coverage.
- Everyday and Technical modes operate on the same state and never discard values.
- The beam-size range remains 1 through 20 and defaults to 5.
- Queue concurrency, compute/fallback, saved language defaults, model lifecycle, and demo transcription are out of scope.
