# Compute Device and GPU Fallback Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make saved automatic, CPU, and CUDA preferences plus an explicit GPU-fallback policy control real transcription and translation construction, with a truthful unavailable-device state before a job starts.

**Architecture:** Add a pure, immutable resolver in `hardware.py` that converts validated settings and an injected `HardwareProfile` into a `ComputeResolution`. `MainWindow` owns one detected profile, reapplies resolution on startup and Settings Save, snapshots the resolved configuration per queue, blocks an unavailable explicit-CUDA request before worker creation, and forwards the same device and compute type to both local inference adapters.

**Tech Stack:** Python 3.11+, frozen dataclasses, PySide6, Faster-Whisper, CTranslate2, pytest, pytest-qt.

## Global Constraints

- Windows 11 is the primary platform.
- Normal transcription and translation make no network requests.
- Every visible enabled control must have connected behavior, state handling, accessibility metadata, persistence, and automated coverage.
- Everyday and Technical modes operate on the same state and never discard values.
- Use unique `.pytest-runs\<timestamp>` directories with `--basetemp` and `-p no:cacheprovider` for every local pytest run.
- `compute_device` remains exactly one of `automatic`, `cpu`, or `cuda`; GPU fallback defaults to enabled and is persisted as a boolean.
- Automatic selects CUDA when the injected profile reports CUDA available and CPU otherwise; explicit CPU always selects CPU.
- Explicit CUDA selects CUDA when available, falls back to CPU only when GPU fallback is enabled, and otherwise produces an actionable blocking state before any worker is created.
- Faster-Whisper and NLLB CTranslate2 receive the same resolved device and compute type for a queue.
- Apply compute settings on startup and immediately after Settings Save; the New Job compute label must describe the actual resolved state and must not promise an unimplemented runtime-error retry.
- Do not change demo pipeline behavior, queue concurrency, saved language defaults, cache enforcement, subtitle appearance, update scheduling, logging, model lifecycle, or download behavior in this task.
- Do not merge to `main`.

---

### Task 1: Resolve, persist, display, and inject compute policy

**Files:**
- Modify: `src/quietcaption/hardware.py`
- Modify: `src/quietcaption/settings.py`
- Modify: `src/quietcaption/translation.py`
- Modify: `src/quietcaption/ui/settings_view.py`
- Modify: `src/quietcaption/ui/main_window.py`
- Test: `tests/test_runtime.py`
- Test: `tests/test_settings_schema.py`
- Test: `tests/test_translation.py`
- Test: `tests/test_product_ui.py`
- Test: `tests/test_control_contract.py`
- Modify: `.superpowers/sdd/progress.md`

**Interfaces:**
- Produces: immutable `ComputeResolution(config: ComputeConfig | None, label: str, blocking_reason: str | None = None, used_fallback: bool = False)` and `can_run` property.
- Produces: `resolve_compute(preference: str, allow_gpu_fallback: bool, profile: HardwareProfile) -> ComputeResolution`.
- Produces: persisted `AppSettings.gpu_fallback: bool = True` under schema version 3 and Processing-section reset/import/export behavior.
- Produces: `NllbCTranslate2Translator(model_path, device="cpu", compute_type=None, engine=None, tokenizer=None)`; an omitted compute type retains the current device-derived default.
- Consumes: an optional `hardware_probe` callable in `MainWindow.__init__`, defaulting to `detect_hardware`, called once per window.
- Produces: `MainWindow._queue_compute`, a per-queue `ComputeConfig` snapshot shared by transcription and translation construction.

- [x] **Step 1: Write failing pure resolver tests**

In `tests/test_runtime.py`, import `resolve_compute` and add a parameterized matrix that asserts:

```python
@pytest.mark.parametrize(
    ("preference", "fallback", "profile", "device", "compute_type", "used_fallback", "can_run"),
    [
        ("automatic", True, HardwareProfile(True, "RTX", 8, 32), "cuda", "float16", False, True),
        ("automatic", True, HardwareProfile(False, None, 0, 16), "cpu", "int8", False, True),
        ("cpu", False, HardwareProfile(True, "RTX", 8, 32), "cpu", "int8", False, True),
        ("cuda", False, HardwareProfile(True, "RTX", 3, 32), "cuda", "int8_float16", False, True),
        ("cuda", True, HardwareProfile(False, None, 0, 16), "cpu", "int8", True, True),
        ("cuda", False, HardwareProfile(False, None, 0, 16), None, None, False, False),
    ],
)
def test_compute_resolution_honors_preference_and_fallback(
    preference, fallback, profile, device, compute_type, used_fallback, can_run
):
    resolution = resolve_compute(preference, fallback, profile)
    assert resolution.can_run is can_run
    assert resolution.used_fallback is used_fallback
    assert (resolution.config.device if resolution.config else None) == device
    assert (resolution.config.compute_type if resolution.config else None) == compute_type
```

Also assert the blocked CUDA resolution label contains `CUDA unavailable` and its blocking reason tells the user to enable GPU fallback or select CPU.

- [x] **Step 2: Write failing settings persistence and control tests**

In `tests/test_settings_schema.py`, extend the legacy migration test to assert `gpu_fallback is True`, add a round-trip assertion for `AppSettings(compute_device="cuda", gpu_fallback=False)`, and assert `gpu_fallback="yes"` is rejected with `SettingsValidationError` mentioning `gpu_fallback`.

In `tests/test_product_ui.py`, create `MainWindow(demo=True, settings_store=store, hardware_probe=lambda: cpu_profile)`, uncheck `settings_page.gpu_fallback`, save, and assert the store and window resolution update immediately. Assert the Processing tab exposes a checkbox whose text describes fallback when CUDA is unavailable.

- [x] **Step 3: Write failing UI preflight and adapter-forwarding tests**

In `tests/test_product_ui.py`, use injected CPU-only and CUDA-ready profiles plus the existing fake model service/thread pool pattern to prove:

1. saved `compute_device="cpu"` selects CPU even on a CUDA-ready profile at startup;
2. saved `compute_device="cuda", gpu_fallback=True` on CPU-only hardware displays a CPU fallback label and constructs both adapters with `device="cpu", compute_type="int8"`;
3. saved `compute_device="cuda", gpu_fallback=False` on CPU-only hardware displays `CUDA unavailable`, `_start_jobs()` creates no worker, and `queue_status` or the status bar tells the user to enable GPU fallback or select CPU;
4. saving `compute_device="cuda"` while a CUDA-ready profile is injected updates the label immediately and a later queue constructs both adapters with the CUDA resolution;
5. changing Settings after a queue starts does not alter `_queue_compute` for later files in that queue.

Patch `FasterWhisperTranscriber` and `NllbCTranslate2Translator` with recording factories that assert constructor inputs; do not assert only that a mock was called.

- [x] **Step 4: Write the failing translation compute-type test**

In `tests/test_translation.py`, monkeypatch `sys.modules["ctranslate2"]` and `sys.modules["sentencepiece"]` with complete local fakes, create the required `sentencepiece.bpe.model`, instantiate `NllbCTranslate2Translator(tmp_path, device="cuda", compute_type="float16")`, call `_load()`, and assert the real adapter boundary passed `device="cuda"` and `compute_type="float16"` to the fake CTranslate2 constructor. Retain the existing engine/tokenizer injection tests.

- [x] **Step 5: Verify RED**

Run:

```powershell
$base = ".pytest-runs\$(Get-Date -Format 'yyyyMMdd-HHmmssfff')"
New-Item -ItemType Directory -Path $base -Force | Out-Null
try {
    .\.venv\Scripts\python.exe -m pytest -q tests\test_runtime.py tests\test_settings_schema.py tests\test_translation.py tests\test_product_ui.py tests\test_control_contract.py --basetemp $base -p no:cacheprovider
} finally {
    if (Test-Path -LiteralPath $base) { Remove-Item -LiteralPath $base -Recurse -Force }
}
```

Expected: collection or assertion failures because `ComputeResolution`, `resolve_compute`, `gpu_fallback`, `hardware_probe`, and explicit translation compute-type forwarding do not yet exist.

- [x] **Step 6: Implement the pure resolver**

In `src/quietcaption/hardware.py`, retain `choose_compute` and add:

```python
@dataclass(frozen=True)
class ComputeResolution:
    config: ComputeConfig | None
    label: str
    blocking_reason: str | None = None
    used_fallback: bool = False

    @property
    def can_run(self) -> bool:
        return self.config is not None


def resolve_compute(
    preference: str,
    allow_gpu_fallback: bool,
    profile: HardwareProfile,
) -> ComputeResolution:
    if preference == "automatic":
        config = choose_compute(profile)
        return ComputeResolution(config, f"{config.label} · automatic selection")
    if preference == "cpu":
        config = ComputeConfig("cpu", "int8", "CPU")
        return ComputeResolution(config, "CPU · selected")
    if preference != "cuda":
        raise ValueError("compute preference must be automatic, cpu, or cuda")
    if profile.cuda_available:
        config = choose_compute(profile)
        return ComputeResolution(config, f"{config.label} · selected")
    reason = "CUDA is unavailable. Enable GPU fallback or select CPU in Settings."
    if allow_gpu_fallback:
        config = ComputeConfig("cpu", "int8", "CPU")
        return ComputeResolution(config, "CPU · CUDA unavailable; GPU fallback enabled", used_fallback=True)
    return ComputeResolution(None, "CUDA unavailable · GPU fallback disabled", reason)
```

- [x] **Step 7: Persist and expose GPU fallback**

In `src/quietcaption/settings.py`, set `CURRENT_SCHEMA_VERSION = 3`, add `gpu_fallback: bool = True` beside `compute_device`, reject non-boolean values explicitly, and include `gpu_fallback` in the Processing reset set.

In `SettingsView`, add:

```python
self.gpu_fallback = QCheckBox("Use CPU when requested CUDA is unavailable")
self.gpu_fallback.setChecked(self.settings.gpu_fallback)
```

Place it in the Processing form, include it in `save()` as `gpu_fallback=self.gpu_fallback.isChecked()`, restore it in `reload()`, and add `fallback` to the Processing search keywords.

- [x] **Step 8: Forward explicit translation compute type**

Change `NllbCTranslate2Translator.__init__` to accept `compute_type: str | None = None`, store `self.compute_type = compute_type or ("int8_float16" if self.device == "cuda" else "int8")`, and pass `self.compute_type` to `ctranslate2.Translator` in `_load()`. Preserve existing positional `device` and injected engine/tokenizer behavior.

- [x] **Step 9: Apply resolution at startup/save and snapshot it per queue**

In `MainWindow.__init__`, accept `hardware_probe=detect_hardware`, call it once into `self.hardware_profile`, remove the unconditional `choose_compute(detect_hardware())`, and let the existing `_apply_settings(initial_settings)` perform resolution.

Extend `_apply_settings`:

```python
self.compute_resolution = resolve_compute(
    settings.compute_device,
    settings.gpu_fallback,
    self.hardware_profile,
)
self.compute = self.compute_resolution.config
self.new_job.compute.setText(self.compute_resolution.label)
```

At the top of `_start_jobs`, after the empty-files guard and before mutating queue state, return on a blocked resolution after placing `blocking_reason` in `queue_status` and the status bar. For a runnable state, snapshot `self._queue_compute = self.compute_resolution.config` with the other queue settings. Use `_queue_compute` rather than mutable `self.compute` in `_run_next_job`, pass its device and compute type to `NllbCTranslate2Translator`, and pass the same object to `FasterWhisperTranscriber`.

- [x] **Step 10: Strengthen the control contract regression surface**

In `tests/test_control_contract.py`, add a narrow test that changes the visible compute and GPU fallback controls, saves, and asserts the New Job compute label changes to the resolved state. Do not broaden this task into a semantic audit of all controls.

- [x] **Step 11: Verify GREEN and regression safety**

Run the focused command from Step 5, then run the full suite using a second unique `.pytest-runs` base. Both runs must exit 0 with pristine output, and only their own disposable directories may be removed.

Run `python -m compileall -q src` with `PYTHONPYCACHEPREFIX` directed to a unique workspace-local disposable directory, then remove only that directory. Run `git diff --check`.

- [x] **Step 12: Record, review, and commit**

Append the RED/GREEN evidence, exact test counts, task-review verdict, and any non-blocking follow-ups to `.superpowers/sdd/progress.md`. Stage only this task's files and commit:

```text
fix: honor compute and GPU fallback settings
```

Do not merge to `main`; push only `agent/full-product-expansion` after exact-HEAD verification and final review are clean.

## Self-review

- Spec coverage: startup/save application, all preference/profile states, explicit unavailable blocking, truthful label, persistence, queue snapshotting, and both inference adapters are covered.
- Scope boundary: runtime failures after a profile reports usable CUDA are surfaced by the worker; automatic retry after an arbitrary backend exception is intentionally not claimed or implemented because safe error classification is outside this detected-hardware policy slice.
- Placeholder scan: no TBD, TODO, or unspecified implementation step remains.
- Type consistency: `resolve_compute` produces `ComputeResolution`; runnable resolutions contain one `ComputeConfig`; `MainWindow` snapshots that config and forwards its exact values to both adapters.
