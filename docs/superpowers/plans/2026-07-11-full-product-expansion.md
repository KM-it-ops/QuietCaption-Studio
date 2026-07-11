# QuietCaption Studio Full Product Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all placeholder product surfaces with a capability-driven language system, hardware-aware model setup, complete model management, persisted settings, and polished Everyday/Technical interfaces whose controls are fully connected and tested.

**Architecture:** Model and language capabilities live in typed domain registries independent of Qt. Setup, transfers, recommendations, and settings are application services injected into focused PySide6 views; the main window coordinates navigation only. Network access remains isolated in explicit catalog/download operations while inference stays offline.

**Tech Stack:** Python 3.11+, PySide6 6.7+, Faster-Whisper, CTranslate2, NLLB-200 metadata, platformdirs, urllib, pytest, pytest-qt, PyInstaller, Inno Setup 6.

## Global Constraints

- Windows 11 is the primary platform.
- Normal transcription and translation make no network requests.
- Language selectors are generated from active model capability metadata.
- Every visible enabled control must have connected behavior, state handling, accessibility metadata, and automated coverage.
- Everyday and Technical modes operate on the same state and never discard values.
- Model downloads require confirmation, SHA-256 verification, and atomic installation.
- Model support is labeled Strong, Supported, or Experimental; support is never described as guaranteed accuracy.
- Use unique `.pytest-runs\<timestamp>` directories with `--basetemp` and `-p no:cacheprovider` for local tests.

---

### Task 1: Capability and language registry

**Files:**
- Create: `src/quietcaption/languages.py`, `src/quietcaption/resources/languages.json`, `src/quietcaption/resources/model-catalog.json`
- Modify: `src/quietcaption/models.py`, `pyproject.toml`
- Test: `tests/test_languages.py`, `tests/test_models.py`

**Interfaces:**
- Produces: `Language`, `CapabilityTier`, `LanguageRegistry.search/get`, `ModelCapability`, `ModelDescriptor.supported_languages`, `ModelCatalog.load`.

- [ ] Write failing tests proving unique language codes, English/native-name search, RTL metadata, Whisper source coverage, NLLB target coverage, and active-model filtering.
- [ ] Run `pytest tests/test_languages.py tests/test_models.py -q`; expect missing-module/API failures.
- [ ] Implement immutable language records loaded from packaged JSON and model descriptors that reference stable codes rather than UI strings.
- [ ] Populate the registry from official Whisper and NLLB language mappings, retaining model-specific tokens and capability tiers.
- [ ] Re-run focused tests and the full suite; expect all pass.
- [ ] Commit `feat: add capability-driven language registry`.

### Task 2: Hardware findings and recommendation engine

**Files:**
- Modify: `src/quietcaption/hardware.py`
- Create: `src/quietcaption/setup.py`
- Test: `tests/test_setup.py`, `tests/test_hardware.py`

**Interfaces:**
- Produces: `FindingStatus`, `HardwareFinding`, `SystemScan`, `SetupPlan`, `SetupScanner.scan()`, `RecommendationEngine.recommend(scan, priorities)`.

- [ ] Write failing matrix tests for CPU-only, low-RAM, NVIDIA-ready, CUDA-broken, low-disk, missing-FFmpeg, and existing-model systems.
- [ ] Run focused tests and confirm failures come from missing setup APIs.
- [ ] Expand hardware detection through injected probes so tests do not depend on host hardware.
- [ ] Implement findings with plain-language summary, technical details, severity, and concrete action.
- [ ] Implement deterministic bundle recommendations with download size, disk use, memory guidance, languages, quality, and rationale.
- [ ] Re-run focused and full suites; expect pass.
- [ ] Commit `feat: add hardware-aware setup recommendations`.

### Task 3: Transactional model lifecycle

**Files:**
- Modify: `src/quietcaption/models.py`, `src/quietcaption/downloads.py`
- Create: `src/quietcaption/model_service.py`, `src/quietcaption/benchmarks.py`
- Test: `tests/test_model_service.py`, `tests/test_downloads.py`, `tests/test_benchmarks.py`

**Interfaces:**
- Produces: `ModelState`, `TransferProgress`, `ModelService.install/activate/verify/repair/remove/update/move`, `BenchmarkService.run`.

- [ ] Write failing tests for resume, cancel, checksum quarantine, atomic install, activation rollback, dependency-aware removal, repair, update, move rollback, and benchmark persistence.
- [ ] Run focused tests and confirm the lifecycle APIs are absent.
- [ ] Implement catalog refresh and downloads as explicit network operations with injectable clients.
- [ ] Implement transactional filesystem operations, installed manifests, active-role pointers, and privacy-safe events.
- [ ] Implement deterministic benchmark service and compatibility results.
- [ ] Re-run focused and full suites; expect pass.
- [ ] Commit `feat: implement transactional local model management`.

### Task 4: Settings schema and services

**Files:**
- Modify: `src/quietcaption/settings.py`
- Create: `src/quietcaption/settings_schema.py`, `src/quietcaption/subtitle_style.py`
- Test: `tests/test_settings_schema.py`, `tests/test_subtitle_style.py`

**Interfaces:**
- Produces: expanded `AppSettings`, `SettingsSection`, `SettingsValidator`, `SettingsStore.export/import/reset_section`, `SubtitleStyle`, `NamingTemplate.preview`.

- [ ] Write failing tests for every specified settings section, validation, schema migration, import secret rejection, reset behavior, naming previews, paths, model references, and RTL style preview data.
- [ ] Run focused tests and confirm failures.
- [ ] Implement typed nested settings with versioned migration and atomic persistence.
- [ ] Implement validators for paths, ranges, active models, cache limits, and naming templates.
- [ ] Implement import/export excluding machine-local secrets and runtime credentials.
- [ ] Re-run focused and full suites; expect pass.
- [ ] Commit `feat: add complete validated application settings`.

### Task 5: Setup and model-management UI

**Files:**
- Create: `src/quietcaption/ui/setup_wizard.py`, `src/quietcaption/ui/models_view.py`, `src/quietcaption/ui/model_details.py`, `src/quietcaption/ui/transfer_row.py`
- Modify: `src/quietcaption/ui/main_window.py`, `src/quietcaption/ui/theme.py`
- Test: `tests/ui/test_setup_wizard.py`, `tests/ui/test_models_view.py`

**Interfaces:**
- Produces: `SetupWizard`, `HardwareFindingsPage`, `AutomatedSetupPage`, `CustomSetupPage`, `ModelsView`.

- [ ] Write pytest-qt failures for findings, automated/custom branching, confirmation, progress, cancellation, catalog filtering, details, all lifecycle actions, empty/error states, and keyboard labels.
- [ ] Run UI tests offscreen and confirm failures.
- [ ] Implement setup pages bound to the Task 2/3 services, with no direct filesystem/network logic in widgets.
- [ ] Implement Installed/Catalog/Transfers model views and complete action states.
- [ ] Replace the Models placeholder in `MainWindow` and route first-run incomplete state to setup.
- [ ] Re-run UI and full suites; expect pass.
- [ ] Commit `feat: build setup and model management workspaces`.

### Task 6: Complete settings and dual-mode UI

**Files:**
- Create: `src/quietcaption/ui/settings_view.py`, `src/quietcaption/ui/settings_sections.py`, `src/quietcaption/ui/mode.py`, `src/quietcaption/ui/language_combo.py`
- Modify: `src/quietcaption/ui/new_job.py`, `src/quietcaption/ui/main_window.py`, `src/quietcaption/ui/theme.py`
- Test: `tests/ui/test_settings_view.py`, `tests/ui/test_language_combo.py`, `tests/ui/test_interface_modes.py`

**Interfaces:**
- Produces: `SettingsView`, `InterfaceModeController`, `CapabilityLanguageCombo`.

- [ ] Write failing tests for every settings action, save/revert/reset/import/export, mode persistence, state preservation, dynamic language lists, search, RTL, and active-model changes.
- [ ] Run focused UI tests and confirm failures.
- [ ] Implement settings sections bound to Task 4 services with inline validation and accessible status feedback.
- [ ] Implement global Everyday/Technical toggle; technical widgets reveal without changing their values.
- [ ] Replace language literals and target maps with capability combo data objects.
- [ ] Replace the Settings placeholder and remove `_placeholder` from the production navigation path.
- [ ] Re-run focused and full suites; expect pass.
- [ ] Commit `feat: complete settings and adaptive expert interface`.

### Task 7: Functional-control, accessibility, and workflow hardening

**Files:**
- Create: `tests/ui/test_control_contract.py`, `tests/ui/test_accessibility.py`
- Modify: all `src/quietcaption/ui/*.py` files identified by audits.

**Interfaces:**
- Produces: test helper `assert_connected_controls(widget)` and accessibility audit coverage.

- [ ] Write a failing recursive widget audit that rejects visible enabled buttons/actions without signal receivers or explicit navigation behavior.
- [ ] Write keyboard, focus, text-scaling, RTL, reduced-motion, long-label, and narrow-window tests.
- [ ] Run audits and record all failures.
- [ ] Connect or remove every orphan control; implement loading, disabled, confirmation, cancellation, and error behavior.
- [ ] Correct focus order, accessible names/descriptions, contrast tokens, clipping, and directionality.
- [ ] Re-run UI and full suites; expect pass with no Qt warnings.
- [ ] Commit `fix: enforce complete control and accessibility contracts`.

### Task 8: End-to-end offline integration and release

**Files:**
- Modify: `src/quietcaption/pipeline.py`, `src/quietcaption/ui/main_window.py`, `README.md`, `packaging/build.ps1`, `.github/workflows/windows-release.yml`
- Create: `tests/test_offline_integration.py`, `tests/test_first_run_integration.py`

**Interfaces:**
- Produces: complete first-run → model-ready → process → edit → export workflow.

- [ ] Write integration tests using a local fixture server for downloads and socket blocking during inference.
- [ ] Verify first-run automated/custom setup, dynamic languages, processing, saved settings, model repair, and recovery.
- [ ] Add packaged smoke automation that launches portable and silently installed builds and confirms the main window remains alive.
- [ ] Update documentation with real setup, model storage, language capability, modes, and troubleshooting behavior.
- [ ] Run all tests, compileall, portable build, installer build, portable launch, silent install, installed launch, and GitHub clean-run pipeline.
- [ ] Verify checksums and GitHub provenance attestations; confirm local/remote SHA equality.
- [ ] Commit `release: complete QuietCaption Studio workstation` and push `main`.

## Completion audit

- [ ] Compare every paragraph of `docs/superpowers/specs/2026-07-11-full-product-expansion-design.md` to code or an explicit automated assertion.
- [ ] Confirm no placeholder pages, static short language lists, decorative controls, online inference paths, or unverified model installation paths remain.
- [ ] Confirm clean Windows packaged and installed launch behavior.
