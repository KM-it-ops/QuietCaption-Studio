from pathlib import Path

import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from quietcaption.languages import default_registry
from quietcaption.hardware import HardwareProfile
from quietcaption.models import built_in_catalog
from quietcaption.models import ModelRegistry
from quietcaption.models import ModelDescriptor
from quietcaption.model_service import ModelRuntime
from quietcaption.pipeline import PipelineResult
from quietcaption.settings import AppSettings, SettingsStore
from quietcaption.ui.main_window import CancellationToken, MainWindow, PipelineWorker
from quietcaption.ui.models_view import ModelsView


def test_language_selectors_are_capability_driven(qtbot):
    window = MainWindow(demo=True); qtbot.addWidget(window)
    assert window.new_job.source_language.count() >= 100  # automatic + Whisper
    assert window.new_job.target_language.count() >= 203  # none + NLLB
    assert window.new_job.source_language.itemData(0) == "auto"
    assert window.new_job.target_language.itemData(0) == "none"


def test_models_and_settings_are_real_views(qtbot, tmp_path):
    settings = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(demo=True, settings_store=settings); qtbot.addWidget(window)
    assert window.models_page.objectName() == "modelsView"
    assert window.settings_page.objectName() == "settingsView"
    assert window.settings_page.save_button.isEnabled()
    assert window.settings_page.tabs.count() >= 6
    qtbot.mouseClick(window.settings_page.technical_button, Qt.LeftButton)
    assert settings.load().interface_mode == "technical"
    assert window.new_job.advanced_panel.isVisibleTo(window)


def test_setup_view_offers_automated_and_custom_paths(qtbot):
    window = MainWindow(demo=True); qtbot.addWidget(window)
    setup = window.models_page.setup_panel
    assert setup.automated_button.text() == "Automated setup"
    assert setup.custom_button.text() == "Custom setup"
    assert setup.findings_list.count() >= 4


def test_model_install_button_runs_service_and_updates_status(qtbot, monkeypatch):
    class Service:
        def __init__(self): self.installed = []
        def install(self, descriptor): self.installed.append(descriptor.id); return Path("model")
        def verify(self, descriptor): return True
        def activate(self, descriptor): return descriptor
        def remove(self, descriptor, force=False): return None
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    service = Service(); view = ModelsView(service=service); qtbot.addWidget(view)
    view.model_list.setCurrentRow(0)
    qtbot.mouseClick(view.install_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: bool(service.installed), timeout=3000)
    qtbot.waitUntil(lambda: "Installed" in view.status.text(), timeout=3000)


@pytest.mark.parametrize("failure", [False, True])
def test_model_lifecycle_busy_disables_all_mutations_and_restores_controls(qtbot, monkeypatch, failure):
    class Service:
        def __init__(self):
            self.install_calls = []
            self.activate_calls = []
            self.remove_calls = []

        def install(self, descriptor):
            self.install_calls.append(descriptor.id)
            if failure:
                raise RuntimeError("disk unavailable")
            return Path("model")

        def verify(self, descriptor): return True
        def activate(self, descriptor): self.activate_calls.append(descriptor.id); return descriptor
        def remove(self, descriptor, force=False): self.remove_calls.append(descriptor.id)

    class CapturingPool:
        def __init__(self): self.workers = []
        def start(self, worker): self.workers.append(worker)

    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    service = Service()
    view = ModelsView(service=service)
    qtbot.addWidget(view)
    pool = CapturingPool()
    view.thread_pool = pool
    view.model_list.setCurrentRow(0)

    qtbot.mouseClick(view.install_button, Qt.LeftButton)

    conflicting = (
        view.install_button,
        view.update_button,
        view.repair_button,
        view.activate_button,
        view.remove_button,
        view.setup_panel.automated_button,
    )
    assert all(not button.isEnabled() for button in conflicting)
    assert view.verify_button.isEnabled()
    assert len(pool.workers) == 1
    assert len(view._workers) == 1

    view._activate()
    view._remove()
    assert service.activate_calls == []
    assert service.remove_calls == []
    assert "in progress" in view.status.text().lower()

    pool.workers[0].run()

    assert all(button.isEnabled() for button in conflicting)
    assert view._workers == set()
    if failure:
        assert "stopped safely" in view.status.text().lower()
        assert "disk unavailable" in view.status.text()
    else:
        assert view.status.text() == "Installed whisper-small."


def test_automated_setup_uses_one_service_bundle_and_shared_busy_state(qtbot, monkeypatch):
    class Service:
        def __init__(self): self.bundles = []
        def install_and_activate(self, models): self.bundles.append(tuple(model.id for model in models)); return models
        def verify(self, descriptor): return True
        def activate(self, descriptor): return descriptor
        def remove(self, descriptor, force=False): return None

    class CapturingPool:
        def __init__(self): self.workers = []
        def start(self, worker): self.workers.append(worker)

    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    service = Service()
    view = ModelsView(service=service)
    qtbot.addWidget(view)
    pool = CapturingPool()
    view.thread_pool = pool

    qtbot.mouseClick(view.setup_panel.automated_button, Qt.LeftButton)

    assert not view.install_button.isEnabled()
    assert not view.setup_panel.automated_button.isEnabled()
    pool.workers[0].run()
    assert service.bundles == [("whisper-small", "nllb-200-distilled-600m")]
    assert view.install_button.isEnabled()
    assert view.setup_panel.automated_button.isEnabled()
    assert "complete" in view.status.text().lower()


def test_production_language_choices_follow_active_models(qtbot, tmp_path):
    catalog = built_in_catalog(default_registry())

    class Service:
        def __init__(self):
            self.registry = ModelRegistry(tmp_path / "models", catalog)
            self._active = {}
        def active(self, kind): return self._active.get(kind)
        def verify(self, descriptor): return True
        def install(self, descriptor): return self.registry.root / descriptor.id
        def activate(self, descriptor): self._active[descriptor.kind] = descriptor; return descriptor
        def remove(self, descriptor, force=False): return None

    service = Service()
    settings = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(demo=False, settings_store=settings, model_service=service)
    qtbot.addWidget(window)

    assert window.new_job.source_language.count() == 1
    assert window.new_job.target_language.count() == 1

    transcription = next(item for item in catalog if item.kind == "transcription")
    translation = next(item for item in catalog if item.kind == "translation")
    service.activate(transcription)
    window.models_page.modelActivated.emit(transcription)
    service.activate(translation)
    window.models_page.modelActivated.emit(translation)

    assert window.new_job.source_language.count() >= 100
    assert window.new_job.target_language.count() >= 203


def test_generate_tracks_local_model_readiness_without_readding_files(qtbot, tmp_path):
    transcription = ModelDescriptor("whisper", "transcription", {"*"}, 1, "local", "0" * 64)
    translation = ModelDescriptor("nllb", "translation", {"*"}, 1, "local", "1" * 64)

    class Lease:
        runtimes = ()
        def release(self): pass

    class Service:
        def __init__(self):
            self.registry = ModelRegistry(tmp_path / "models", [transcription, translation])
            self.active_models = {}
            self.ready_kinds = set()

        def active(self, kind): return self.active_models.get(kind)
        def acquire_runtime(self, kinds):
            missing = next((kind for kind in kinds if kind not in self.ready_kinds), None)
            if missing:
                raise ValueError(f"No ready {missing} model. Open Models to install and activate one.")
            return Lease()

    service = Service()
    window = MainWindow(demo=False, settings_store=SettingsStore(tmp_path / "settings.json"), model_service=service)
    qtbot.addWidget(window)
    media = tmp_path / "clip.wav"
    media.write_bytes(b"audio")
    window.new_job.add_files([media])

    assert not window.new_job.generate.isEnabled()
    assert "Models" in window.new_job.generate.toolTip()

    service.active_models["transcription"] = transcription
    service.ready_kinds.add("transcription")
    window.models_page.modelActivated.emit(transcription)

    assert window.new_job.generate.isEnabled()
    assert window.new_job.files == [media]

    service.active_models["translation"] = translation
    window.models_page.modelActivated.emit(translation)
    window.new_job.target_language.setCurrentIndex(1)

    assert not window.new_job.generate.isEnabled()
    assert "translation" in window.new_job.generate.toolTip().lower()


def test_failed_runtime_acquisition_leaves_queue_and_ui_untouched(qtbot, tmp_path):
    descriptor = ModelDescriptor("whisper", "transcription", {"*"}, 1, "local", "0" * 64)

    class Service:
        registry = ModelRegistry(tmp_path / "models", [descriptor])
        def active(self, kind): return descriptor if kind == "transcription" else None
        def acquire_runtime(self, kinds): raise ValueError("runtime unavailable")

    window = MainWindow(demo=False, settings_store=SettingsStore(tmp_path / "settings.json"), model_service=Service())
    qtbot.addWidget(window)
    before = (
        window.navigation.currentRow(),
        window.queue_status.text(),
        window.statusBar().currentMessage(),
        window.queue_progress.isVisible(),
        window.cancel_button.isEnabled(),
    )

    window._start_jobs([tmp_path / "clip.wav"])

    assert (
        window.navigation.currentRow(),
        window.queue_status.text(),
        window.statusBar().currentMessage(),
        window.queue_progress.isVisible(),
        window.cancel_button.isEnabled(),
    ) == before
    assert not hasattr(window, "_pending_files")
    assert not hasattr(window, "_queue_snapshot")


def test_incomplete_first_run_opens_hardware_setup(qtbot, tmp_path):
    settings = SettingsStore(tmp_path / "settings.json")
    settings.save(AppSettings(onboarding_complete=False))
    window = MainWindow(demo=False, settings_store=settings)
    qtbot.addWidget(window)

    assert window.navigation.currentItem().text() == "Models"
    assert window.pages.currentWidget() is window.models_page


def test_model_repair_and_update_buttons_call_lifecycle_service(qtbot, monkeypatch):
    class Service:
        def __init__(self): self.calls = []
        def repair(self, descriptor): self.calls.append(("repair", descriptor.id)); return Path("model")
        def update(self, descriptor): self.calls.append(("update", descriptor.id)); return Path("model")
        def verify(self, descriptor): return True
        def activate(self, descriptor): return descriptor
        def remove(self, descriptor, force=False): return None
        def install(self, descriptor): return Path("model")
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    service = Service(); view = ModelsView(service=service); qtbot.addWidget(view)
    view.model_list.setCurrentRow(0)

    qtbot.mouseClick(view.repair_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: ("repair", "whisper-small") in service.calls, timeout=3000)
    qtbot.mouseClick(view.update_button, Qt.LeftButton)
    qtbot.waitUntil(lambda: ("update", "whisper-small") in service.calls, timeout=3000)

    assert "Updated" in view.status.text()


def test_settings_export_import_and_reset_buttons_are_functional(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    store = SettingsStore(tmp_path / "settings.json")
    store.save(AppSettings(theme="dark", subtitle_font_size=40))
    window = MainWindow(demo=True, settings_store=store); qtbot.addWidget(window)
    view = window.settings_page
    exported = tmp_path / "settings-export.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(exported), "JSON"))
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)

    qtbot.mouseClick(view.export_button, Qt.LeftButton)
    assert exported.is_file()

    view.tabs.setCurrentIndex(3)
    qtbot.mouseClick(view.reset_section_button, Qt.LeftButton)
    assert store.load().subtitle_font_size == AppSettings().subtitle_font_size


def test_saved_theme_is_applied_immediately(qtbot, tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    window = MainWindow(demo=True, settings_store=store); qtbot.addWidget(window)
    view = window.settings_page

    view.theme.setCurrentText("light")
    qtbot.mouseClick(view.save_button, Qt.LeftButton)

    assert store.load().theme == "light"
    assert "#f4f7fb" in QApplication.instance().styleSheet()


def test_gpu_fallback_control_is_visible_persisted_and_applied_immediately(qtbot, tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.save(AppSettings(compute_device="cuda", gpu_fallback=True))
    cpu_profile = HardwareProfile(False, None, 0, 16)
    window = MainWindow(demo=True, settings_store=store, hardware_probe=lambda: cpu_profile)
    qtbot.addWidget(window)

    checkbox = window.settings_page.gpu_fallback
    assert checkbox.text() == "Use CPU when requested CUDA is unavailable"
    assert checkbox.isChecked()
    checkbox.setChecked(False)
    qtbot.mouseClick(window.settings_page.save_button, Qt.LeftButton)

    assert store.load().gpu_fallback is False
    assert window.compute_resolution.can_run is False
    assert "CUDA unavailable" in window.new_job.compute.text()


def test_saved_cpu_preference_overrides_available_cuda_at_startup(qtbot, tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.save(AppSettings(compute_device="cpu"))
    profile = HardwareProfile(True, "RTX", 8, 32)

    window = MainWindow(demo=True, settings_store=store, hardware_probe=lambda: profile)
    qtbot.addWidget(window)

    assert window.compute.device == "cpu"
    assert window.new_job.compute.text() == "CPU · selected"


def _production_compute_window(qtbot, tmp_path, monkeypatch, settings, profile):
    transcription_model = ModelDescriptor("whisper-small", "transcription", {"*"}, 500, "local", "0" * 64)
    translation_model = ModelDescriptor("nllb", "translation", {"*"}, 500, "local", "1" * 64)

    class Service:
        def __init__(self):
            self.registry = ModelRegistry(tmp_path / "models", [transcription_model, translation_model])

        def active(self, kind):
            return transcription_model if kind == "transcription" else translation_model

        def acquire_runtime(self, kinds):
            runtimes = tuple(
                ModelRuntime(self.active(kind), self.registry.root / self.active(kind).id)
                for kind in kinds
            )
            return type("Lease", (), {"runtimes": runtimes, "release": lambda self: None})()

    class RecordingThreadPool:
        def __init__(self):
            self.workers = []

        def start(self, worker):
            self.workers.append(worker)

    received = {"transcription": [], "translation": []}

    def recording_transcriber(model, compute, options):
        received["transcription"].append(compute)
        return object()

    def recording_translator(model, device="cpu", compute_type=None):
        received["translation"].append((device, compute_type))
        return object()

    monkeypatch.setattr("quietcaption.ui.main_window.FasterWhisperTranscriber", recording_transcriber)
    monkeypatch.setattr("quietcaption.ui.main_window.NllbCTranslate2Translator", recording_translator)
    store = SettingsStore(tmp_path / "settings.json")
    store.save(settings)
    window = MainWindow(
        demo=False,
        output_directory=tmp_path / "output",
        settings_store=store,
        model_service=Service(),
        hardware_probe=lambda: profile,
    )
    qtbot.addWidget(window)
    window.thread_pool = RecordingThreadPool()
    window.new_job.target_language.setCurrentIndex(1)
    return window, store, received


def test_cpu_fallback_is_forwarded_to_both_local_adapters(qtbot, tmp_path, monkeypatch):
    window, _, received = _production_compute_window(
        qtbot,
        tmp_path,
        monkeypatch,
        AppSettings(compute_device="cuda", gpu_fallback=True, onboarding_complete=True),
        HardwareProfile(False, None, 0, 16),
    )

    assert "CPU" in window.new_job.compute.text()
    assert "fallback" in window.new_job.compute.text()
    window._start_jobs([tmp_path / "first.wav"])

    assert [(item.device, item.compute_type) for item in received["transcription"]] == [("cpu", "int8")]
    assert received["translation"] == [("cpu", "int8")]


def test_unavailable_cuda_blocks_before_queue_mutation_or_worker_creation(qtbot, tmp_path, monkeypatch):
    window, _, received = _production_compute_window(
        qtbot,
        tmp_path,
        monkeypatch,
        AppSettings(compute_device="cuda", gpu_fallback=False, onboarding_complete=True),
        HardwareProfile(False, None, 0, 16),
    )

    assert "CUDA unavailable" in window.new_job.compute.text()
    window._start_jobs([tmp_path / "first.wav"])

    guidance = f"{window.queue_status.text()} {window.statusBar().currentMessage()}"
    assert "Enable GPU fallback or select CPU" in guidance
    assert window.thread_pool.workers == []
    assert received == {"transcription": [], "translation": []}
    assert not hasattr(window, "_pending_files")


def test_demo_queue_ignores_unavailable_cuda_preflight(qtbot, tmp_path):
    class RecordingThreadPool:
        def __init__(self):
            self.workers = []

        def start(self, worker):
            self.workers.append(worker)

    store = SettingsStore(tmp_path / "settings.json")
    store.save(AppSettings(compute_device="cuda", gpu_fallback=False))
    window = MainWindow(
        demo=True,
        output_directory=tmp_path / "output",
        settings_store=store,
        hardware_probe=lambda: HardwareProfile(False, None, 0, 16),
    )
    qtbot.addWidget(window)
    window.thread_pool = RecordingThreadPool()
    media = tmp_path / "demo.wav"
    media.write_bytes(b"audio")
    window.new_job.add_files([media])

    assert window.new_job.generate.isEnabled()
    window._start_jobs(window.new_job.files)

    assert len(window.thread_pool.workers) == 1
    assert window._pending_files == []
    assert window.queue_status.text() == "Processing demo.wav locally…"


def test_cuda_save_applies_immediately_and_queue_snapshot_stays_stable(qtbot, tmp_path, monkeypatch):
    window, _, received = _production_compute_window(
        qtbot,
        tmp_path,
        monkeypatch,
        AppSettings(compute_device="cpu", onboarding_complete=True),
        HardwareProfile(True, "RTX", 8, 32),
    )
    window.settings_page.compute_device.setCurrentText("cuda")
    qtbot.mouseClick(window.settings_page.save_button, Qt.LeftButton)

    assert window.new_job.compute.text() == "RTX · selected"
    window._start_jobs([tmp_path / "first.wav", tmp_path / "second.wav"])
    queue_compute = window._queue_compute
    window.settings_page.compute_device.setCurrentText("cpu")
    qtbot.mouseClick(window.settings_page.save_button, Qt.LeftButton)
    window._completed(object())

    assert window.compute.device == "cpu"
    assert window._queue_compute is queue_compute
    assert [(item.device, item.compute_type) for item in received["transcription"]] == [
        ("cuda", "float16"),
        ("cuda", "float16"),
    ]
    assert received["translation"] == [("cuda", "float16"), ("cuda", "float16")]


def test_model_service_uses_the_saved_model_directory(qtbot, tmp_path):
    model_directory = tmp_path / "custom-models"
    store = SettingsStore(tmp_path / "settings.json")
    store.save(AppSettings(model_directory=str(model_directory)))

    window = MainWindow(demo=False, settings_store=store); qtbot.addWidget(window)

    assert window.models_page.service.registry.root == model_directory


def test_hardware_findings_wrap_without_horizontal_scrolling(qtbot):
    window = MainWindow(demo=True); qtbot.addWidget(window)
    findings = window.models_page.setup_panel.findings_list

    assert findings.wordWrap()
    assert findings.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    assert findings.maximumHeight() <= 250


def test_technical_settings_search_navigates_compact_sections(qtbot, tmp_path):
    window = MainWindow(demo=True, settings_store=SettingsStore(tmp_path / "settings.json")); qtbot.addWidget(window)
    view = window.settings_page
    window.navigation.setCurrentRow(3)
    assert [view.tabs.tabText(index) for index in range(view.tabs.count())] == ["General", "Models", "Processing", "Subtitles", "Privacy", "Diagnostics"]

    qtbot.mouseClick(view.technical_button, Qt.LeftButton)
    assert view.settings_search.isVisibleTo(window)
    view.settings_search.setText("subtitle font")

    assert view.tabs.currentIndex() == 3


def test_finish_queue_handles_skipped_pipeline_result(qtbot, tmp_path):
    window = MainWindow(demo=True, settings_store=SettingsStore(tmp_path / "settings.json"))
    qtbot.addWidget(window)
    original_page_count = window.pages.count()
    window._completed_jobs = 0
    window._last_result = PipelineResult(None, [], skipped=True)

    window._finish_queue()

    assert window.pages.count() == original_page_count
    assert window.queue_status.text() == "Job skipped — existing output kept"
    assert window.statusBar().currentMessage() == "Skipped because output already exists"


def test_pipeline_worker_uses_dedicated_cancelled_signal(qtbot):
    class Pipeline:
        def run(self, request, cancel=None):
            raise InterruptedError("Job cancelled")

    worker = PipelineWorker(Pipeline(), object(), CancellationToken())
    cancelled = []
    failed = []
    worker.signals.cancelled.connect(cancelled.append)
    worker.signals.failed.connect(failed.append)

    worker.run()

    assert cancelled == ["Job cancelled"]
    assert failed == []


def test_main_window_cancelled_state_is_non_error(qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    critical = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: critical.append(args))
    window = MainWindow(demo=True)
    qtbot.addWidget(window)
    window._pending_files = []

    window._cancelled("Job cancelled")

    assert window.queue_status.text() == "Cancelled — no output was published"
    assert window.statusBar().currentMessage() == "Cancelled"
    assert critical == []


def test_production_beam_size_is_snapshotted_for_each_queue(qtbot, tmp_path, monkeypatch):
    transcription_model = ModelDescriptor(
        "whisper-small",
        "transcription",
        {"*"},
        500,
        "local",
        "0" * 64,
    )

    class Service:
        def __init__(self):
            self.registry = ModelRegistry(tmp_path / "models", [transcription_model])

        def active(self, kind):
            return transcription_model if kind == "transcription" else None

        def acquire_runtime(self, kinds):
            runtimes = tuple(ModelRuntime(transcription_model, self.registry.root / transcription_model.id) for _ in kinds)
            return type("Lease", (), {"runtimes": runtimes, "release": lambda self: None})()

    class RecordingThreadPool:
        def __init__(self):
            self.workers = []

        def start(self, worker):
            self.workers.append(worker)

    received_options = []

    def recording_transcriber(model, compute, options):
        received_options.append(options)
        return object()

    monkeypatch.setattr("quietcaption.ui.main_window.FasterWhisperTranscriber", recording_transcriber)
    window = MainWindow(
        demo=False,
        output_directory=tmp_path / "output",
        settings_store=SettingsStore(tmp_path / "settings.json"),
        model_service=Service(),
    )
    qtbot.addWidget(window)
    window.thread_pool = RecordingThreadPool()

    window.new_job.beam_size.setValue(11)
    window._start_jobs([tmp_path / "first.wav", tmp_path / "second.wav"])
    window.new_job.beam_size.setValue(3)
    window._completed(object())

    assert [options.beam_size for options in received_options] == [11, 11]
    assert received_options[0] is received_options[1]

    window._start_jobs([tmp_path / "third.wav"])

    assert received_options[2].beam_size == 3
    assert received_options[2] is not received_options[0]


def test_production_queue_snapshots_model_paths_before_first_worker(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "critical", lambda *args: None)
    transcription = ModelDescriptor("whisper", "transcription", {"*"}, 1, "local", "0" * 64)
    translation = ModelDescriptor("nllb", "translation", {"*"}, 1, "local", "1" * 64)
    original_root = tmp_path / "original-models"
    changed_root = tmp_path / "changed-models"

    class Lease:
        def __init__(self, runtimes):
            self.runtimes = runtimes
            self.releases = 0

        def release(self):
            self.releases += 1

    class Service:
        def __init__(self):
            self.registry = ModelRegistry(original_root, [transcription, translation])
            self.active_models = {"transcription": transcription, "translation": translation}
            self.lease = None

        def active(self, kind):
            return self.active_models.get(kind)

        def acquire_runtime(self, kinds):
            self.lease = Lease(tuple(ModelRuntime(self.active_models[kind], original_root / self.active_models[kind].id) for kind in kinds))
            return self.lease

    class RecordingThreadPool:
        def __init__(self): self.workers = []
        def start(self, worker): self.workers.append(worker)

    received = {"transcription": [], "translation": []}
    monkeypatch.setattr("quietcaption.ui.main_window.FasterWhisperTranscriber", lambda model, compute, options: received["transcription"].append(Path(model)) or object())
    monkeypatch.setattr("quietcaption.ui.main_window.NllbCTranslate2Translator", lambda model, *args, **kwargs: received["translation"].append(Path(model)) or object())
    service = Service()
    window = MainWindow(
        demo=False,
        output_directory=tmp_path / "output",
        settings_store=SettingsStore(tmp_path / "settings.json"),
        model_service=service,
    )
    qtbot.addWidget(window)
    window.thread_pool = RecordingThreadPool()
    window.new_job.target_language.setCurrentIndex(1)

    window._start_jobs([tmp_path / "first.wav", tmp_path / "second.wav"])
    service.registry.root = changed_root
    service.active_models.clear()
    window._completed(object())

    assert received == {
        "transcription": [original_root / "whisper", original_root / "whisper"],
        "translation": [original_root / "nllb", original_root / "nllb"],
    }


@pytest.mark.parametrize("exit_path", ["finish", "failed", "cancelled", "adapter_failure", "pool_failure"])
def test_queue_releases_runtime_lease_once_on_every_exit(qtbot, tmp_path, monkeypatch, exit_path):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "critical", lambda *args: None)
    descriptor = ModelDescriptor("whisper", "transcription", {"*"}, 1, "local", "0" * 64)

    class Lease:
        def __init__(self):
            self.runtimes = (ModelRuntime(descriptor, tmp_path / "models" / descriptor.id),)
            self.releases = 0
        def release(self): self.releases += 1

    class Service:
        def __init__(self):
            self.registry = ModelRegistry(tmp_path / "models", [descriptor])
            self.leases = []
        def active(self, kind): return descriptor if kind == "transcription" else None
        def acquire_runtime(self, kinds):
            lease = Lease(); self.leases.append(lease); return lease

    class Pool:
        def __init__(self): self.workers = []
        def start(self, worker):
            if exit_path == "pool_failure": raise RuntimeError("pool unavailable")
            self.workers.append(worker)

    if exit_path == "adapter_failure":
        monkeypatch.setattr("quietcaption.ui.main_window.FasterWhisperTranscriber", lambda *args: (_ for _ in ()).throw(RuntimeError("adapter unavailable")))
    else:
        monkeypatch.setattr("quietcaption.ui.main_window.FasterWhisperTranscriber", lambda *args: object())
    service = Service()
    window = MainWindow(demo=False, output_directory=tmp_path / "output", settings_store=SettingsStore(tmp_path / "settings.json"), model_service=service)
    qtbot.addWidget(window)
    window.thread_pool = Pool()

    window._start_jobs([tmp_path / "clip.wav"])
    queue_lease = service.leases[-1]
    if exit_path == "finish": window._finish_queue()
    elif exit_path == "failed": window._failed("failed")
    elif exit_path == "cancelled": window._cancelled("cancelled")

    assert queue_lease.releases == 1
