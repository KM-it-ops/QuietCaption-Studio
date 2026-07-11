# QuietCaption Studio — Product Design Specification

## Product definition

QuietCaption Studio is a native-feeling Windows desktop application for private, fully offline transcription and translation of video and audio. Media, speech, transcripts, and translations never leave the computer. Network access is restricted to explicit application or model update actions initiated by the user.

The first release targets Windows 11, supports NVIDIA GPU acceleration when available, and automatically falls back to CPU processing.

## Product principles

1. **Private by construction:** normal processing has no network dependency or online fallback.
2. **Understandable:** hardware mode, installed models, job state, and output location are always visible.
3. **Recoverable:** projects autosave, interrupted jobs fail safely, and completed work is not lost.
4. **Approachable:** drag-and-drop and sensible defaults produce useful subtitles without technical setup.
5. **Editable:** transcription is a starting point; users can correct text and timing before export.

## User experience

### Application shell

The application uses a PySide6 desktop window with four primary sections:

- **New job:** drag-and-drop intake and processing options.
- **Queue:** active, waiting, completed, cancelled, and failed jobs.
- **Models:** installed transcription and translation models, storage use, updates, and removal.
- **Settings:** defaults, output paths, appearance, privacy, performance, and subtitle styling.

The title bar displays the product name and current connectivity state. The main workspace displays the selected compute mode, such as `NVIDIA GPU` or `CPU`, without requiring the user to understand CUDA configuration.

### First-run setup

On first launch, QuietCaption Studio:

1. Verifies the bundled FFmpeg runtime.
2. Detects CUDA compatibility, available VRAM, system RAM, free storage, and CPU capabilities.
3. Recommends a transcription model appropriate for the hardware.
4. Offers optional offline translation model installation.
5. Shows download source, version, approximate size, license link, and checksum before installation.
6. Performs no download until the user confirms it.

The setup wizard can be reopened from Settings.

### New job workflow

Users can drag one or more local video/audio files onto the window or use a file picker. Version 1 does not accept remote video URLs because that would blur the offline privacy boundary and introduce site-specific download failures.

For each job, the user can choose:

- spoken language detection or a manual source language;
- transcription model;
- zero or more offline translation targets;
- output formats: SRT, VTT, plain text, and project JSON;
- optional subtitle embedding or permanent burn-in;
- destination folder and subtitle appearance for burn-in.

The primary action is **Generate subtitles**. Inputs are validated before a job enters the queue.

### Queue and progress

Long-running work executes outside the UI thread. Each job reports its current stage, elapsed time, progress when measurable, compute mode, and actionable status message. Users may cancel active jobs and retry failed jobs. Cancellation preserves the source file and any valid project data while removing incomplete export files.

Jobs run sequentially by default to avoid exhausting GPU memory. A later release may allow advanced concurrency after hardware-aware scheduling is proven safe.

### Subtitle editor

Completed transcription opens as a non-destructive project containing media metadata, subtitle tracks, timing, model provenance, and export settings.

The editor provides:

- synchronized media playback;
- a searchable list of subtitle segments;
- direct text editing;
- start/end time adjustment;
- split, merge, insert, and delete operations;
- warnings for overlaps, invalid ordering, empty segments, excessive line length, and implausible reading speed;
- separate source and translated tracks;
- undo/redo and automatic project saving.

Translation never overwrites the source transcription.

## Technical architecture

### Application layers

- **UI layer:** PySide6 views, reusable widgets, navigation, dialogs, and accessibility metadata.
- **Application layer:** job orchestration, commands, progress events, cancellation, settings, and project lifecycle.
- **Domain layer:** media metadata, subtitle segments/tracks, validation, format conversion, and model descriptors.
- **Infrastructure layer:** FFmpeg, Faster-Whisper/CTranslate2 adapters, offline translation adapters, filesystem persistence, hardware detection, and opt-in update clients.

These layers communicate through typed interfaces so model runtimes and UI components can be tested independently.

### Processing pipeline

1. Validate the input path, type, readability, duration, and available disk space.
2. Probe media with FFprobe and create an isolated job workspace.
3. Extract normalized mono audio with FFmpeg when required.
4. Load the selected Faster-Whisper model using the detected compute backend.
5. Transcribe locally with voice activity detection and segment timestamps.
6. Normalize and validate the source subtitle track.
7. Translate selected tracks with installed local translation models.
8. Save the editable project atomically.
9. Export selected formats through format-specific writers.
10. Optionally embed or burn subtitles through a safely escaped FFmpeg command.
11. Remove disposable temporary files while preserving logs and the project.

### Hardware selection

At startup, the hardware service tests whether a supported CUDA runtime can actually initialize; it does not rely solely on the presence of an NVIDIA device. The processing engine selects safe compute types based on backend and model compatibility.

If GPU initialization or inference fails with a recognized compatibility or memory error, the job offers a CPU retry and records the fallback reason. It never silently changes output settings.

### Offline translation

Translation uses downloadable, local CTranslate2-compatible model packages behind a common adapter. The initial catalog prioritizes multilingual coverage, while smaller language-pair models may be offered for low-memory systems. Every catalog entry declares supported languages, RAM/VRAM guidance, source, version, license, file size, and SHA-256 checksums.

There is no online translation provider, telemetry SDK, or network fallback in the processing path.

### Model and application updates

The update subsystem is separate from the processing engine and inactive unless opened or explicitly enabled for update checks.

- Model downloads require user confirmation.
- Downloads use HTTPS, resume partial transfers, verify expected size and SHA-256, and install atomically.
- A failed verification never replaces an installed model.
- Application updates display release notes and require confirmation before installation.
- Update endpoints are configurable only through signed application configuration, not arbitrary project files.

## Files and persistence

Application data uses Windows-known folders rather than the working directory:

- settings and catalog metadata in the user configuration directory;
- models in a user-selectable model directory;
- cache and resumable partial downloads in a disposable cache directory;
- projects and exports in user-selected locations;
- privacy-safe diagnostic logs in the local application data directory.

Writes use temporary files followed by atomic replacement where supported. Input media is never modified.

## Security and privacy

- Normal processing performs no network request.
- Dropped files must resolve to regular readable files; unsupported types and unsafe paths are rejected.
- Display names are separated from internal workspace identifiers.
- External processes receive argument arrays, never shell-built command strings.
- FFmpeg filter paths and subtitle content are escaped for the target platform.
- Logs omit transcript text and redact user paths by default.
- Crash reports are local files unless the user explicitly chooses to share them.
- No analytics, advertising identifiers, or telemetry are included.

## Error handling

Errors are mapped to user-facing categories with recovery actions:

- missing or damaged media;
- unsupported codec or FFmpeg failure;
- missing, corrupt, or incompatible model;
- insufficient disk space, RAM, or VRAM;
- GPU initialization or inference failure;
- invalid subtitle timing or export path;
- interrupted or checksum-failed update.

Technical details remain available in an expandable panel and privacy-safe log. Exceptions do not surface raw stack traces in ordinary dialogs.

## Packaging and delivery

The product ships as:

- a signed-ready Windows installer build;
- a portable ZIP build;
- a source distribution for developers.

FFmpeg is bundled with its license notices. Large speech and translation models are installed separately during first-run setup so the application installer remains manageable and users download only what their hardware needs.

The build uses a reproducible Python environment and PyInstaller-based packaging. Installer creation is scripted and suitable for CI, but publishing and code-signing remain explicit release actions.

## Accessibility

- Complete keyboard navigation and visible focus states.
- Programmatic labels for controls and progress indicators.
- Windows text scaling support.
- High-contrast-compatible colors and no color-only status meanings.
- Reduced-motion behavior.
- Errors and stage changes announced through accessible status regions where supported by Qt.

## Verification strategy

### Unit tests

- timestamp formatting and long-duration handling;
- SRT/VTT/TXT serialization and round trips;
- segment split, merge, ordering, overlap, and reading-speed validation;
- settings migration and defaults;
- model manifest and checksum validation;
- hardware selection and fallback decisions;
- safe path and filename handling.

### Integration tests

- FFprobe and FFmpeg extraction using short committed fixtures;
- deterministic pipeline execution with stub transcription/translation adapters;
- real-model smoke tests marked optional because of model size;
- cancellation, retry, cleanup, and crash-recovery paths;
- export of multilingual and right-to-left text.

### UI and packaging tests

- drag-and-drop, queue state, editor operations, and keyboard navigation;
- first-run setup under CPU-only and mocked CUDA configurations;
- installer and portable launch tests on a clean Windows environment;
- verification that normal processing succeeds with network access blocked.

## Definition of done

QuietCaption Studio is complete when a user on a clean Windows 11 machine can install or unpack it, select approved local models, drop supported media, transcribe and translate without network access, correct subtitles, export valid files, cancel and recover jobs safely, and understand any failure without consulting source code.

The release must pass automated tests, a CPU end-to-end fixture run, a GPU smoke test when compatible hardware is available, a network-blocked privacy test, and clean-machine packaging verification.

## Deliberately deferred

- remote URL downloading;
- cloud storage and synchronization;
- online translation or transcription;
- accounts, telemetry, and multi-user server deployment;
- live microphone transcription;
- collaborative editing;
- unrestricted parallel GPU jobs.

These exclusions keep the first product private, reliable, and finishable without weakening its core promise.
