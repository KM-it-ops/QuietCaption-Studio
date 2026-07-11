# QuietCaption Studio Full Product Expansion

## Objective

Replace the release's placeholder model/settings surfaces and short language lists with a complete, hardware-aware, capability-driven offline workstation. Every visible control must connect to tested application behavior. Everyday and Technical interface modes provide different levels of detail without creating separate product states.

## Scope boundaries

This expansion covers five connected subsystems:

1. language and capability registry;
2. first-run hardware and model setup;
3. local model catalog, installation, integrity, updates, and removal;
4. complete persisted application settings;
5. polished dual-mode UI integration and release validation.

Online inference, accounts, telemetry, and arbitrary unverified model execution remain out of scope.

## Capability-driven language registry

### Rules

- Language selectors are generated from the active model descriptors, never from UI literals.
- Spoken-language choices are the union supported by the active transcription model plus **Detect automatically**.
- Translation targets are the languages supported by the active translation model, excluding the selected source when the model cannot meaningfully translate a language to itself.
- Each entry has a stable internal code, English display name, native display name, script, direction, model-specific token, capability type, and quality tier.
- Search matches English names, native names, codes, and scripts.
- Right-to-left names and subtitle text render with correct directionality.
- A language remains discoverable in Models even when unavailable in New Job; the UI explains which model enables it.

### Accuracy language

Model support does not equal guaranteed accuracy. QuietCaption displays capability tiers derived from published model evidence and local benchmark results:

- **Strong support:** broadly evaluated and recommended.
- **Supported:** model exposes the language; results vary by audio/domain.
- **Experimental:** limited evaluation or specialized model required.

No interface copy uses “accurate” as an unconditional claim.

### Initial engines

- Faster-Whisper provides multilingual transcription and automatic language detection.
- NLLB-200 provides broad offline text translation across its published language/script variants.
- The catalog interface supports later specialized transcription or language-pair models without changing UI code.

## Hardware-aware first-run setup

### Scan

The setup wizard runs non-destructive checks for:

- Windows version and architecture;
- CPU model and logical cores;
- total and available RAM;
- NVIDIA GPU, VRAM, driver, CUDA runtime initialization, and supported compute types;
- free space in the selected model/cache location;
- FFmpeg and FFprobe availability/version;
- existing QuietCaption models and incomplete downloads;
- network availability only when the user requests catalog refresh or installation.

### Findings page

Findings are presented in plain language with expandable technical details. Each item reports **Ready**, **Action recommended**, or **Blocking**, with a concrete remediation. Hardware discovery never changes the computer.

### Recommended plan

The recommendation engine chooses a transcription model, translation model, compute type, and storage location based on RAM, VRAM, CPU, free disk, and user priorities. It shows:

- downloads and installed disk size;
- approximate memory requirements;
- expected speed category and quality trade-off;
- transcription and translation language coverage;
- licenses and upstream sources;
- why each recommendation was made.

### User choice

- **Automated Setup:** one confirmation starts resumable downloads, checksum verification, atomic installation, runtime validation, a short local benchmark, activation, and settings persistence.
- **Custom Setup:** the same catalog is filtered for compatibility but exposes individual model selection, install location, compute preference, storage totals, and warnings.

Setup can be cancelled safely, resumed, or rerun from Settings. The application remains usable in project/demo mode when inference prerequisites are absent, but cannot misrepresent itself as ready for real transcription.

## Models workspace

### Installed view

Each installed model row provides:

- name, engine, version, role, source, license, and install date;
- supported language count and searchable coverage list;
- active/inactive state and current compute configuration;
- on-disk size, integrity status, and last verification time;
- local benchmark results for CPU/GPU;
- **Activate**, **Benchmark**, **Verify**, **Repair**, **Update**, **Open location**, and **Remove** actions.

Removal warns when a model is active, required by a saved default, or in use by a job. It never deletes shared files used by another installed descriptor.

### Catalog view

The catalog supports search and filters for role, language, hardware compatibility, download size, quality tier, and installed state. Model details include provenance, license, hashes, files, release notes, compatibility, and known limitations before installation.

### Transfers

Downloads expose progress, speed, bytes, remaining estimate, pause/resume/cancel, retry, and failure details. Partial files live in cache; verified models are installed by atomic rename. Checksum failure quarantines the artifact and never replaces an installed model.

## Settings workspace

Settings use inline sections with immediate validation and explicit save/revert behavior. Search is available in Technical mode.

### General

- interface mode: Everyday or Technical;
- theme: system, light, dark;
- UI language;
- launch behavior and first-run/setup status;
- update-check preference with no automatic download.

### Output and projects

- output/project directories with writable-space validation;
- naming template preview and collision policy;
- default export formats and encodings;
- autosave interval, recovery, and recent-project retention;
- reveal-output and post-completion behavior.

### Processing

- automatic or explicit compute device;
- CPU thread limits, worker priority, and power behavior;
- default transcription/translation models;
- default source language/detection and translation targets;
- queue concurrency, retry, temporary files, and GPU fallback policy;
- Technical mode: beam size, VAD, batching, compute type, and model-specific parameters with safe ranges.

### Subtitle appearance

- font family, size, weight, colors, outline, shadow, alignment, safe margins, line length, and lines per caption;
- live preview across light/dark video samples and right-to-left text;
- presets, reset, and burn-in defaults.

### Storage and models

- model/cache locations and usage totals;
- cache limit and cleanup controls;
- incomplete download management;
- integrity scan and model repair;
- move-model workflow with free-space checks and rollback.

### Privacy, network, and diagnostics

- explicit permissions for catalog refresh, model downloads, and update checks;
- confirmation that media/transcripts never use network inference;
- redacted logging level, log location, export diagnostics, and clear logs;
- local data inventory and deletion controls.

### Accessibility

- text scaling, contrast, reduced motion, focus enhancement, screen-reader announcements, and keyboard shortcut reference;
- preview and reset controls.

### Recovery and advanced

- rerun hardware setup;
- export/import settings with schema validation and secret exclusion;
- reset section or all preferences;
- runtime paths, environment diagnostics, FFmpeg selection, and factory repair.

## Everyday and Technical modes

The toggle is global, immediate, persisted, keyboard accessible, and available in the application header and Settings.

Everyday mode presents goals and recommendations: quality, language, output, and clear status. Technical mode reveals exact model, device, compute, tuning, storage, and diagnostic controls. Switching modes never discards edits or silently changes values. Advanced values changed in Technical mode remain effective and are summarized in Everyday mode as **Customized**.

## Navigation and visual system

- Retain the compact left navigation and calm dark workstation identity, with complete system-light and high-contrast behavior.
- Use one consistent component vocabulary for buttons, selectors, progress, tables, banners, and inline errors.
- Avoid nested cards. Use dividers, aligned rows, and progressive disclosure for density.
- Transitions are 150–250 ms, state-driven, and disabled under reduced motion.
- Every empty state explains why it is empty and offers the correct next action.
- Long model/language names, Windows text scaling, keyboard focus, narrow windows, and bidirectional text must not clip or overlap.

## Functional control contract

No visible control may be decorative in the production application. Each button, menu item, selector, toggle, link, row action, and keyboard shortcut must have:

1. a connected command or navigation result;
2. enabled/disabled rules;
3. keyboard access and an accessible name;
4. loading/progress behavior for asynchronous work;
5. validation and actionable errors;
6. persistence or explicit non-persistence semantics;
7. cancellation/rollback where the action mutates files;
8. unit or UI coverage proving its behavior.

A release test enumerates interactive widgets and fails when a visible enabled control has no connected behavior.

## Error and recovery model

Errors are typed by stage: discovery, compatibility, network, download, integrity, installation, activation, benchmark, settings validation, processing, and export. User messages state what failed, what remains safe, and the next action. Technical details are expandable and privacy-redacted.

Model operations are transactional. Interrupted downloads resume; failed verification quarantines; failed installation rolls back; failed activation restores the previous active model; failed model moves retain the source until destination verification succeeds.

## Testing and release gates

### Domain and service tests

- complete language metadata, uniqueness, search, direction, and model-token mapping;
- compatibility and recommendation matrices across CPU/RAM/GPU/VRAM/storage profiles;
- catalog schema/signature/hash validation;
- resume, cancellation, quarantine, repair, update, activation, removal, and rollback;
- settings defaults, migrations, validation, import/export, and atomic persistence.

### UI tests

- setup scan findings and both setup paths;
- Everyday/Technical switching with state preservation;
- dynamic language options from active model capabilities;
- every Models and Settings action plus disabled/loading/error states;
- keyboard-only flows, accessible labels, scaling, RTL, contrast, and reduced motion;
- interactive-control connection audit.

### Integration and packaging

- clean Windows first launch with no models;
- CPU-only automated setup using small fixtures and mocked download server;
- CUDA recommendation and fallback through deterministic hardware adapters;
- network-blocked inference after models are installed;
- portable and installed application launch tests;
- GitHub clean-run build, checksums, provenance attestations, and artifact startup smoke test.

## Definition of done

This expansion is complete only when:

- first launch accurately reports hardware and offers working automated/custom setup;
- active models determine all language choices;
- Models and Settings contain no placeholders and every control satisfies the functional contract;
- Everyday and Technical modes are polished, persistent, and preserve state;
- model operations are verifiable, resumable, cancellable, and recoverable;
- offline inference succeeds with network access blocked;
- all automated, accessibility, packaging, portable-launch, installed-launch, and clean GitHub pipeline checks pass.

