# QuietCaption Studio

QuietCaption Studio is a native Windows application for private, offline transcription and subtitle translation. Media and transcript content stay on your computer. Internet access is used only when you explicitly install or update models.

## What works

- Native drag-and-drop Windows interface
- Automatic NVIDIA CUDA detection with CPU fallback
- Local Faster-Whisper transcription
- Local CTranslate2 translation adapter
- SRT, WebVTT, text, and editable `.qcp` project exports
- Background processing, queue status, and subtitle editing
- Deterministic demo mode that needs no models or FFmpeg
- Checksum-verified, resumable model download foundation
- Privacy-redacted diagnostics and atomic project/settings writes

## Try the complete interface without models

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\quietcaption.exe --demo
```

Drop any supported local media file. Demo mode does not decode it; it exercises the entire native workflow with deterministic sample captions.

## Enable real offline transcription

1. Install [FFmpeg](https://ffmpeg.org/) and ensure `ffmpeg` and `ffprobe` are on `PATH`, or bundle those executables beside the packaged application.
2. Install the local inference runtime:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[inference]"
```

3. Launch `quietcaption` without `--demo`. Faster-Whisper downloads a selected model only when it is first requested. For a strictly air-gapped system, pre-stage a converted model directory and select it locally.

Translation has no online fallback. A compatible local CTranslate2 model must be installed before selecting a target language. The source adapter accepts a model directory containing `model.bin` and `sentencepiece.model`.

## Supported input and output

Inputs: MP4, MKV, MOV, AVI, WebM, MP3, WAV, M4A, FLAC, and OGG.

Outputs: SRT, VTT, TXT, and `.qcp` editable project data. The media source is never modified.

## Development and verification

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
$env:TEMP = (Resolve-Path ".tmp-test")
$env:TMP = $env:TEMP
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q src
```

## Build the portable application

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

The script produces `dist\QuietCaption-Studio-portable.zip`. If Inno Setup 6 is installed, it also produces a Windows installer. Code signing is intentionally not automated because it requires the publisher's private certificate and explicit release approval.

The public repository also includes a free GitHub Actions release pipeline. It rebuilds on a clean Windows runner, runs the full test suite, compiles the installer, publishes SHA-256 checksums, and creates Sigstore-backed GitHub provenance attestations. Verify a downloaded artifact with:

```powershell
gh attestation verify QuietCaption-Studio-Setup-1.0.0.exe --repo KM-it-ops/QuietCaption-Studio
```

Provenance verifies that an artifact came from this repository's workflow. It is complementary to Authenticode and does not remove Windows SmartScreen prompts. The project is eligible to apply for free trusted Authenticode signing through SignPath Foundation; that service requires external project approval before its signing step can be enabled.

## Privacy boundary

Normal processing contains no telemetry, accounts, analytics, online transcription, or online translation. The update/download utility is a separate explicit API and verifies model artifacts with SHA-256 before atomic installation.
