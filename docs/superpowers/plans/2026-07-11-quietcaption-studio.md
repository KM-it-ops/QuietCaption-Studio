# QuietCaption Studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a tested Windows-first desktop application that creates, edits, translates, and exports subtitles locally with automatic CUDA/CPU selection.

**Architecture:** A PySide6 UI calls a typed application service that coordinates media probing, Faster-Whisper transcription, offline translation adapters, project persistence, and subtitle exporters. Runtime integrations sit behind protocols so tests run without large models or external binaries.

**Tech Stack:** Python 3.11+, PySide6 6.7+, faster-whisper 1.0+, CTranslate2, transformers/sentencepiece for local model conversion compatibility, platformdirs, pydantic 2, pytest, pytest-qt, PyInstaller.

## Global Constraints

- Windows 11 is the primary supported platform.
- Normal media processing performs no network requests.
- Translation has no online provider or fallback.
- NVIDIA CUDA is selected only after runtime initialization succeeds; CPU is the fallback.
- User media is never modified and transcript content is excluded from logs.
- Model and application downloads require explicit confirmation and SHA-256 verification.
- Initial delivery is a functional source application with reproducible installer and portable build scripts; model binaries are separate downloads.

---

### Task 1: Package foundation and subtitle domain

**Files:**
- Create: `pyproject.toml`, `src/quietcaption/__init__.py`, `src/quietcaption/domain.py`, `src/quietcaption/formats.py`
- Test: `tests/test_domain.py`, `tests/test_formats.py`

**Interfaces:**
- Produces: `SubtitleSegment`, `SubtitleTrack`, `Project`, `format_timestamp()`, `parse_timestamp()`, `SrtWriter`, `VttWriter`, `TextWriter`.

- [ ] Write failing tests proving long timestamps, segment validation, split/merge behavior, and Unicode SRT/VTT output.
- [ ] Run `python -m pytest tests/test_domain.py tests/test_formats.py -v`; expect collection/import failure.
- [ ] Implement immutable identifiers, validated timing, editing operations, and deterministic UTF-8 serializers.
- [ ] Re-run the focused tests; expect all pass.
- [ ] Commit with `feat: add subtitle domain and exporters` when Git is available.

### Task 2: Settings, projects, and privacy-safe diagnostics

**Files:**
- Create: `src/quietcaption/settings.py`, `src/quietcaption/projects.py`, `src/quietcaption/diagnostics.py`
- Test: `tests/test_settings.py`, `tests/test_projects.py`, `tests/test_diagnostics.py`

**Interfaces:**
- Produces: `AppSettings`, `SettingsStore.load/save`, `ProjectStore.load/save`, `redact_path()`, `configure_logging()`.

- [ ] Write tests for defaults, corrupt-config recovery, atomic save/load round trips, autosave files, and path/transcript redaction.
- [ ] Run the focused tests and confirm failure before implementation.
- [ ] Implement platformdirs-based storage, JSON schema versioning, atomic replacement, and logs containing job IDs rather than media names.
- [ ] Re-run focused tests; expect all pass.
- [ ] Commit with `feat: add safe local persistence` when Git is available.

### Task 3: Hardware, models, and verified updates

**Files:**
- Create: `src/quietcaption/hardware.py`, `src/quietcaption/models.py`, `src/quietcaption/downloads.py`, `src/quietcaption/resources/model-catalog.json`
- Test: `tests/test_hardware.py`, `tests/test_models.py`, `tests/test_downloads.py`

**Interfaces:**
- Produces: `HardwareProfile`, `detect_hardware()`, `ModelDescriptor`, `ModelRegistry`, `VerifiedDownloader.download()`.

- [ ] Write tests for mocked CUDA success/failure, CPU recommendations, manifest validation, checksum rejection, resume behavior, and atomic install.
- [ ] Run focused tests and confirm failure.
- [ ] Implement lazy CUDA probing, model metadata, explicit download requests, streamed SHA-256 verification, and safe extraction without path traversal.
- [ ] Re-run focused tests; expect all pass.
- [ ] Commit with `feat: add hardware and model management` when Git is available.

### Task 4: Media and local inference adapters

**Files:**
- Create: `src/quietcaption/media.py`, `src/quietcaption/transcription.py`, `src/quietcaption/translation.py`
- Test: `tests/test_media.py`, `tests/test_transcription.py`, `tests/test_translation.py`

**Interfaces:**
- Produces: `MediaInfo`, `FFmpegService.probe/extract_audio/burn_subtitles`, `Transcriber` protocol, `FasterWhisperTranscriber`, `Translator` protocol, `CTranslate2Translator`.

- [ ] Write tests for command argument arrays, timeout/error mapping, segment conversion, compute selection, batching, language validation, and the absence of online adapters.
- [ ] Run focused tests and confirm failure.
- [ ] Implement subprocess-safe FFmpeg calls, lazy model imports, progress callbacks, cancellation checks, and local-only translation.
- [ ] Re-run focused tests; expect all pass.
- [ ] Commit with `feat: add offline media inference pipeline` when Git is available.

### Task 5: Job orchestration and recovery

**Files:**
- Create: `src/quietcaption/jobs.py`, `src/quietcaption/pipeline.py`
- Test: `tests/test_jobs.py`, `tests/test_pipeline.py`

**Interfaces:**
- Produces: `Job`, `JobState`, `CancellationToken`, `JobQueue`, `PipelineRequest`, `PipelineResult`, `SubtitlePipeline.run()`.

- [ ] Write tests for legal state transitions, sequential execution, cancellation cleanup, GPU-to-CPU retry, export failure, and recovery metadata.
- [ ] Run focused tests and confirm failure.
- [ ] Implement a stage-based pipeline with isolated workspaces, atomic result publication, structured events, and preserved editable projects.
- [ ] Re-run focused tests; expect all pass.
- [ ] Commit with `feat: orchestrate recoverable subtitle jobs` when Git is available.

### Task 6: Native desktop shell and editor

**Files:**
- Create: `src/quietcaption/app.py`, `src/quietcaption/ui/main_window.py`, `src/quietcaption/ui/drop_zone.py`, `src/quietcaption/ui/new_job.py`, `src/quietcaption/ui/queue_view.py`, `src/quietcaption/ui/model_view.py`, `src/quietcaption/ui/settings_view.py`, `src/quietcaption/ui/editor.py`, `src/quietcaption/ui/theme.py`
- Test: `tests/ui/test_main_window.py`, `tests/ui/test_editor.py`

**Interfaces:**
- Produces: `create_application()`, `MainWindow`, `DropZone`, `SubtitleEditor`.

- [ ] Write pytest-qt tests for navigation, drag/drop validation, form state, progress events, editing operations, keyboard labels, and offline/compute indicators.
- [ ] Run UI tests with `QT_QPA_PLATFORM=offscreen`; confirm failure.
- [ ] Implement the approved sidebar layout, worker-thread bridge, queue cards, model controls, preferences, and synchronized editor table.
- [ ] Re-run UI tests offscreen; expect all pass.
- [ ] Commit with `feat: build QuietCaption Studio desktop UI` when Git is available.

### Task 7: First-run experience and runnable demo

**Files:**
- Create: `src/quietcaption/ui/onboarding.py`, `src/quietcaption/demo.py`, `tests/ui/test_onboarding.py`, `tests/test_demo.py`
- Modify: `src/quietcaption/app.py`

**Interfaces:**
- Produces: `OnboardingWizard`, `DemoTranscriber`, `DemoTranslator`; command `quietcaption --demo`.

- [ ] Write tests for hardware recommendations, explicit download confirmation, offline demo processing, and onboarding completion persistence.
- [ ] Run focused tests and confirm failure.
- [ ] Implement onboarding and deterministic demo adapters so the full UI is evaluable before multi-gigabyte models are installed.
- [ ] Re-run focused tests; expect all pass.
- [ ] Commit with `feat: add onboarding and offline demo mode` when Git is available.

### Task 8: Packaging, documentation, and release verification

**Files:**
- Create: `README.md`, `LICENSE`, `THIRD_PARTY_NOTICES.md`, `packaging/quietcaption.spec`, `packaging/build.ps1`, `packaging/installer.iss`, `.github/workflows/windows.yml`
- Test: `tests/test_privacy_boundary.py`, `tests/test_package_metadata.py`

**Interfaces:**
- Produces: `dist/QuietCaption-Studio-portable.zip` and an Inno Setup installer when the external compiler is installed.

- [ ] Write tests that block sockets during processing, validate metadata/entry points, and ensure no online translation dependency exists.
- [ ] Run the complete suite and confirm any remaining failures.
- [ ] Add user/developer documentation, licenses, PyInstaller data collection, PowerShell build automation, and Windows CI.
- [ ] Run `python -m pytest -q`, `python -m compileall -q src`, and a demo pipeline smoke test; expect success.
- [ ] Build with `powershell -ExecutionPolicy Bypass -File packaging/build.ps1`; verify the portable executable launches. Build the installer when Inno Setup is present, otherwise report that external prerequisite precisely.
- [ ] Commit with `chore: package and document QuietCaption Studio` when Git is available.

## Completion audit

- [ ] Compare every section of the approved design specification with the implemented files.
- [ ] Confirm processing passes while outbound sockets are blocked.
- [ ] Confirm CPU selection locally and cover CUDA selection through deterministic tests when compatible hardware is unavailable.
- [ ] Record any external limitation, especially missing FFmpeg, CUDA hardware, model downloads, code signing, or Inno Setup, without claiming those paths were executed.
