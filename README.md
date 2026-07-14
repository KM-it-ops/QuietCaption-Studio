# QuietCaption Studio

QuietCaption Studio is a native Windows application for private, offline transcription and subtitle translation. Media and transcript content stay on your computer. Internet access is used only when you explicitly install or update models.

## What works

- Native drag-and-drop Windows interface
- Automatic NVIDIA CUDA detection with CPU fallback
- Local Faster-Whisper transcription
- Local CTranslate2 transcription and NLLB translation runtimes included in Windows builds
- Capability-driven selectors for 100+ spoken languages and 200+ translation language/script variants
- First-run hardware findings with Automated Setup and Custom Setup choices
- Local model installation, pinned revisions, integrity manifests, activation, repair, update, and safe removal
- Everyday and Technical interface modes with persisted light, dark, and system themes
- SRT, WebVTT, text, and editable `.qcp` project exports
- Multi-file background queue, cancellation, status, and subtitle editing
- Deterministic demo mode that needs no models or FFmpeg
- Bundled PyAV media decoding fallback when external FFmpeg tools are absent
- Validated settings import/export/reset and atomic project/settings writes
- Privacy-redacted diagnostics and no online inference fallback

## Try the complete interface without models

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\quietcaption.exe --demo
```

Drop any supported local media file. Demo mode does not decode it; it exercises the entire native workflow with deterministic sample captions.

## Set up real offline transcription and translation

The Windows portable and installer builds already contain the inference libraries and a local media decoder. On first launch, open **Models** and review the hardware findings:

- **Automated Setup** confirms the recommended model bundle, downloads pinned snapshots, creates local integrity manifests, activates both roles, and marks onboarding complete.
- **Custom Setup** leaves the catalog available for individual installation and activation.

Model download/update is the only model-related network operation. Media, decoded audio, transcripts, projects, and translations are never sent to an online service. After model setup, inference works without a network connection.

For source development, install the local inference runtime:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[inference]"
```

Then launch `quietcaption` without `--demo` and use the Models workspace to install models. The application does not silently download a model when processing starts.

Translation has no online fallback. The broad NLLB-200 INT8 catalog model is licensed **CC-BY-NC-4.0 for non-commercial use**; QuietCaption displays that restriction before download. Commercial deployments must select or add a model whose license permits their intended use.

External [FFmpeg](https://ffmpeg.org/) and FFprobe are optional for ordinary subtitle generation because the packaged PyAV decoder can create the local Whisper audio stream. External FFmpeg is still required for advanced subtitle burn-in export.

Language lists are derived from the active local models. Before activation, real mode intentionally shows only **Detect automatically** and **No translation** rather than claiming unavailable capabilities.

## Supported input and output

Inputs: MP4, MKV, MOV, AVI, WebM, MP3, WAV, M4A, FLAC, and OGG.

Outputs: SRT, VTT, TXT, and `.qcp` editable project data. The media source is never modified.

## Development and verification

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
$base = ".pytest-runs\$(Get-Date -Format 'yyyyMMdd-HHmmss')"
New-Item -ItemType Directory -Path $base -Force | Out-Null
.\.venv\Scripts\python.exe -m pytest -q --basetemp $base -p no:cacheprovider
.\.venv\Scripts\python.exe -m compileall -q src
```

## Build the portable application

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

The script produces `dist\QuietCaption-Studio-portable.zip`. If Inno Setup 6 is installed, it also produces `dist\QuietCaption-Studio-Setup-1.0.0.exe`. Run `packaging\smoke.ps1` to launch-test normal/demo portable modes plus a silent temporary installer deployment.

Code signing is intentionally not automated because it requires the publisher's private certificate and explicit release approval.

The public repository also includes a free GitHub Actions release pipeline. It rebuilds on a clean Windows runner, runs the full test suite, compiles the installer, publishes SHA-256 checksums, and creates Sigstore-backed GitHub provenance attestations. Verify a downloaded artifact with:

```powershell
gh attestation verify QuietCaption-Studio-Setup-1.0.0.exe --repo KM-it-ops/QuietCaption-Studio
```

Provenance verifies that an artifact came from this repository's workflow. It is complementary to Authenticode and does not remove Windows SmartScreen prompts. The project is eligible to apply for free trusted Authenticode signing through SignPath Foundation; that service requires external project approval before its signing step can be enabled.

## Privacy boundary

Normal processing contains no telemetry, accounts, analytics, online transcription, or online translation. Explicit model downloads use pinned upstream revisions. QuietCaption records per-file SHA-256 values in each installed manifest, verifies them later, stages replacements separately, and restores the previous installation if an update swap fails.
