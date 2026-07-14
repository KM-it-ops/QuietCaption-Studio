from pathlib import Path
from dataclasses import dataclass, replace

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot, Qt
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from ..demo import DemoMedia, DemoTranscriber, DemoTranslator
from ..editor_session import EditorSession
from ..hardware import ComputeConfig, detect_hardware, resolve_compute
from ..media import best_available_media_service
from ..languages import default_registry
from ..model_service import ModelRuntime, ModelService, ModelUseLease
from ..models import ModelRegistry, built_in_catalog
from ..pipeline import PipelineRequest, SubtitlePipeline
from ..projects import ProjectStore
from ..settings import AppSettings
from ..settings import SettingsStore
from ..transcription import FasterWhisperTranscriber, TranscriptionOptions
from ..translation import NllbCTranslate2Translator
from .editor import SubtitleEditor
from .new_job import NewJobView
from .models_view import ModelsView
from .settings_view import SettingsView
from .theme import stylesheet_for


class WorkerSignals(QObject):
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal(str)


class PipelineWorker(QRunnable):
    def __init__(self, pipeline, request, cancel_token):
        super().__init__(); self.pipeline, self.request, self.cancel_token, self.signals = pipeline, request, cancel_token, WorkerSignals()

    @Slot()
    def run(self):
        try: self.signals.completed.emit(self.pipeline.run(self.request, cancel=self.cancel_token))
        except InterruptedError as exc: self.signals.cancelled.emit(str(exc))
        except Exception as exc: self.signals.failed.emit(str(exc))


class CancellationToken:
    def __init__(self):
        self.cancelled = False


@dataclass(frozen=True)
class QueueRuntimeSnapshot:
    output_directory: Path
    target_language: str
    source_language: str
    formats: tuple[str, ...]
    compute: ComputeConfig | None
    transcription_options: TranscriptionOptions
    model_runtimes: tuple[ModelRuntime, ...] = ()
    lease: ModelUseLease | None = None


class MainWindow(QMainWindow):
    def __init__(self, demo: bool = False, output_directory: Path | None = None, settings_store=None, model_service=None, hardware_probe=detect_hardware):
        super().__init__(); self.demo = demo; self.output_directory = output_directory; self.thread_pool = QThreadPool.globalInstance(); self.settings_store = settings_store or SettingsStore()
        self._editors = []
        self.hardware_profile = hardware_probe()
        initial_settings = self.settings_store.load()
        if model_service is None:
            registry_data = default_registry()
            model_service = ModelService(ModelRegistry(Path(initial_settings.model_directory), built_in_catalog(registry_data)))
        self.setWindowTitle("QuietCaption Studio"); self.resize(1100, 720); self.setMinimumSize(820, 560)
        root = QWidget(); shell = QHBoxLayout(root); shell.setContentsMargins(0, 0, 0, 0); shell.setSpacing(0)
        sidebar = QFrame(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(190); side = QVBoxLayout(sidebar)
        brand = QLabel("QuietCaption\nStudio"); brand.setStyleSheet("font-size: 21px; font-weight: 600; padding: 18px 10px")
        self.navigation = QListWidget(); self.navigation.setObjectName("navigation")
        for label in ("New job", "Queue", "Models", "Settings"): self.navigation.addItem(QListWidgetItem(label))
        self.navigation.setCurrentRow(0); self.offline_badge = QLabel("● Offline processing"); self.offline_badge.setObjectName("badge")
        side.addWidget(brand); side.addWidget(self.navigation); side.addStretch(); side.addWidget(self.offline_badge)
        self.pages = QStackedWidget(); self.new_job = NewJobView(use_catalog_defaults=demo); self.pages.addWidget(self.new_job)
        self.queue_page = self._queue_page()
        self.models_page = ModelsView(service=model_service)
        self.settings_page = SettingsView(self.settings_store)
        for page in (self.queue_page, self.models_page, self.settings_page): self.pages.addWidget(page)
        shell.addWidget(sidebar); shell.addWidget(self.pages, 1); self.setCentralWidget(root)
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.new_job.generateRequested.connect(self._start_jobs)
        self.settings_page.modeChanged.connect(self.new_job.set_interface_mode)
        self.settings_page.settingsSaved.connect(self._apply_settings)
        self.models_page.modelActivated.connect(self._model_activated)
        self.new_job.target_language.currentIndexChanged.connect(lambda _: self._sync_runtime_readiness())
        loaded_settings = initial_settings
        self.new_job.set_interface_mode(loaded_settings.interface_mode)
        self._apply_settings(loaded_settings)
        if not self.demo:
            self._sync_active_models()
            if not self.settings_store.load().onboarding_complete:
                self.navigation.setCurrentRow(2)
        self.statusBar().showMessage("Ready — media and transcripts stay on this device")

    def _apply_settings(self, settings):
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(stylesheet_for(settings.theme))
        self.compute_resolution = resolve_compute(
            settings.compute_device,
            settings.gpu_fallback,
            self.hardware_profile,
        )
        self.compute = self.compute_resolution.config
        self.new_job.compute.setText(self.compute_resolution.label)

    def _model_activated(self, descriptor):
        self._sync_active_models()
        transcription = self.models_page.service.active("transcription")
        translation = self.models_page.service.active("translation")
        if transcription is not None and translation is not None:
            settings = replace(self.settings_store.load(), onboarding_complete=True)
            self.settings_store.save(settings)

    def _sync_active_models(self):
        self.new_job.set_active_models(
            self.models_page.service.active("transcription"),
            self.models_page.service.active("translation"),
        )
        self._sync_runtime_readiness()

    def _sync_runtime_readiness(self):
        if self.demo:
            self.new_job.set_runtime_ready(True)
            return
        kinds = ("transcription",)
        if self.new_job.target_language.code() != "none":
            kinds += ("translation",)
        lease = None
        try:
            lease = self.models_page.service.acquire_runtime(kinds)
        except Exception as exc:
            reason = str(exc) or "Required local model is not ready. Open Models to install and activate it."
            if "Models" not in reason:
                reason = f"{reason} Open Models to install and activate the required local model."
            self.new_job.set_runtime_ready(False, reason)
        else:
            self.new_job.set_runtime_ready(True)
        finally:
            if lease is not None:
                lease.release()

    @staticmethod
    def _placeholder(title, text):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(32, 28, 32, 28)
        heading = QLabel(title); heading.setStyleSheet("font-size: 26px; font-weight: 600")
        copy = QLabel(text); copy.setWordWrap(True); copy.setObjectName("muted")
        layout.addWidget(heading); layout.addWidget(copy); layout.addStretch(); return page

    def _queue_page(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(32, 28, 32, 28)
        heading = QLabel("Queue"); heading.setStyleSheet("font-size: 26px; font-weight: 600")
        self.queue_status = QLabel("No jobs yet"); self.queue_status.setObjectName("muted")
        self.queue_progress = QProgressBar(); self.queue_progress.setRange(0, 0); self.queue_progress.hide()
        self.cancel_button = QPushButton("Cancel current job"); self.cancel_button.setEnabled(False); self.cancel_button.clicked.connect(self._cancel_current_job)
        layout.addWidget(heading); layout.addWidget(self.queue_status); layout.addWidget(self.queue_progress); layout.addWidget(self.cancel_button); layout.addStretch()
        return page

    def _start_jobs(self, files):
        if not files: return
        if not self.demo and not self.compute_resolution.can_run:
            reason = self.compute_resolution.blocking_reason
            self.queue_status.setText(reason)
            self.statusBar().showMessage(reason)
            return
        queue_compute = self.compute_resolution.config
        queue_target = self.new_job.target_language.code()
        queue_formats = {"SRT": ("srt",), "VTT": ("vtt",), "SRT + VTT": ("srt", "vtt"), "SRT + VTT + TXT": ("srt", "vtt", "txt")}[self.new_job.output_format.currentText()]
        queue_source_language = self.new_job.source_language.code()
        queue_transcription_options = TranscriptionOptions(
            beam_size=self.new_job.beam_size.value(),
        )
        lease = None
        try:
            runtimes = ()
            if not self.demo:
                kinds = ("transcription",) + (("translation",) if queue_target != "none" else ())
                lease = self.models_page.service.acquire_runtime(kinds)
                runtimes = lease.runtimes
            snapshot = QueueRuntimeSnapshot(
                self.output_directory or Path(self.settings_store.load().output_directory),
                queue_target,
                queue_source_language,
                queue_formats,
                queue_compute,
                queue_transcription_options,
                runtimes,
                lease,
            )
        except Exception:
            if lease is not None:
                lease.release()
            return
        self._queue_snapshot = snapshot
        self._pending_files = list(files); self._completed_jobs = 0; self._last_result = None
        self._queue_compute = queue_compute
        self._queue_target = queue_target
        self._queue_formats = queue_formats
        self._queue_source_language = queue_source_language
        self._queue_transcription_options = queue_transcription_options
        self.navigation.setCurrentRow(1); self.queue_progress.show()
        self.new_job.set_queue_running(True)
        self.cancel_button.setEnabled(True)
        self._run_next_job()

    def _run_next_job(self):
        if not self._pending_files:
            self._finish_queue()
            return
        try:
            source = self._pending_files.pop(0)
            self.queue_status.setText(f"Processing {source.name} locally…")
            snapshot = self._queue_snapshot
            target = snapshot.target_language; targets = [] if target == "none" else [target]
            output = snapshot.output_directory
            if self.demo:
                pipeline = SubtitlePipeline(DemoMedia(), DemoTranscriber(), DemoTranslator())
            else:
                runtime_by_kind = {runtime.descriptor.kind: runtime for runtime in snapshot.model_runtimes}
                transcription_path = runtime_by_kind["transcription"].path
                translator = None
                if targets:
                    translator = NllbCTranslate2Translator(
                        runtime_by_kind["translation"].path,
                        snapshot.compute.device,
                        compute_type=snapshot.compute.compute_type,
                    )
                pipeline = SubtitlePipeline(best_available_media_service(), FasterWhisperTranscriber(str(transcription_path), snapshot.compute, snapshot.transcription_options), translator)
            request = PipelineRequest(source, output, targets, list(snapshot.formats), snapshot.source_language)
            self._cancel_token = CancellationToken()
            worker = PipelineWorker(pipeline, request, self._cancel_token); worker.signals.completed.connect(self._completed); worker.signals.failed.connect(self._failed); worker.signals.cancelled.connect(self._cancelled)
            self._worker = worker; self.thread_pool.start(worker)
        except Exception as exc:
            self._failed(str(exc))

    def _cancel_current_job(self):
        if getattr(self, "_cancel_token", None) is not None:
            self._cancel_token.cancelled = True
            self._pending_files = []
            self.queue_status.setText("Cancelling safely after the current processing step…")
            self.cancel_button.setEnabled(False)

    @Slot(object)
    def _completed(self, result):
        self._completed_jobs += 1; self._last_result = result
        if self._pending_files:
            self._run_next_job()
        else:
            self._finish_queue()

    def _finish_queue(self):
        self._release_queue_lease()
        self.queue_progress.hide(); self.cancel_button.setEnabled(False); self.new_job.set_queue_running(False)
        count = getattr(self, "_completed_jobs", 0)
        self.queue_status.setText(f"{count} job{'s' if count != 1 else ''} completed")
        result = getattr(self, "_last_result", None)
        if result is None:
            return
        if result.skipped:
            self.queue_status.setText("Job skipped — existing output kept")
            self.statusBar().showMessage("Skipped because output already exists")
            return
        project = ProjectStore(result.project_path).load()
        session = EditorSession.open(
            result.project_path,
            len(project.tracks) - 1,
            result.exports,
            self._recovery_choice,
        )
        editor = SubtitleEditor(session); editor.setObjectName("editor")
        self._editors.append(editor)
        self.pages.addWidget(editor); self.pages.setCurrentWidget(editor)
        self.statusBar().showMessage(f"Saved to {result.project_path.parent}")
        if result.warnings:
            QMessageBox.warning(self, "Completed with cleanup warning", "\n".join(result.warnings))

    def _recovery_choice(self, recovery_path: Path) -> str:
        choice = QMessageBox.question(
            self,
            "Recover unsaved subtitle edits?",
            f"A recovery snapshot exists beside this project:\n{recovery_path}\n\nRecover those edits? Choose No to discard it.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        return "recover" if choice == QMessageBox.Yes else "discard"

    def _close_choice(self, editor: SubtitleEditor):
        return QMessageBox.question(
            self,
            "Unsaved subtitle edits",
            "Save subtitle edits before closing QuietCaption Studio?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )

    def request_close(self) -> bool:
        decisions = []
        for editor in self._editors:
            if not editor.is_dirty():
                continue
            choice = self._close_choice(editor)
            if choice == QMessageBox.Cancel:
                return False
            decisions.append((editor, choice))
        for editor, _ in decisions:
            editor.stop_recovery_timer()
        try:
            for editor, _ in decisions:
                editor.session.write_recovery()
        except Exception as exc:
            self._resume_pending_editors(editor for editor, _ in decisions)
            QMessageBox.critical(self, "Could not protect unsaved edits", str(exc))
            return False
        for editor, choice in decisions:
            if choice == QMessageBox.Save and not editor.save():
                self._resume_pending_editors(item for item, _ in decisions)
                return False
        for editor, choice in decisions:
            if choice == QMessageBox.Discard:
                try:
                    editor.session.discard_recovery()
                except Exception as exc:
                    self._resume_pending_editors(item for item, _ in decisions)
                    QMessageBox.critical(self, "Could not discard recovery", str(exc))
                    return False
        return True

    @staticmethod
    def _resume_pending_editors(editors) -> None:
        for editor in editors:
            if not editor.is_dirty():
                continue
            try:
                editor.session.write_recovery()
            except Exception:
                pass
            editor.resume_recovery_timer()

    def closeEvent(self, event):
        if self.request_close():
            event.accept()
        else:
            event.ignore()

    @Slot(str)
    def _failed(self, message):
        self._release_queue_lease()
        self._pending_files = []; self.queue_progress.hide(); self.cancel_button.setEnabled(False); self.queue_status.setText("Job failed — source media was not modified")
        self.new_job.set_queue_running(False)
        QMessageBox.critical(self, "QuietCaption could not finish", message)

    @Slot(str)
    def _cancelled(self, message):
        self._release_queue_lease()
        self._pending_files = []
        self.queue_progress.hide()
        self.cancel_button.setEnabled(False)
        self.new_job.set_queue_running(False)
        self.queue_status.setText("Cancelled — no output was published")
        self.statusBar().showMessage("Cancelled")

    def _release_queue_lease(self):
        snapshot = getattr(self, "_queue_snapshot", None)
        if snapshot is None or snapshot.lease is None:
            return
        lease = snapshot.lease
        self._queue_snapshot = replace(snapshot, lease=None)
        lease.release()
