from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QStackedWidget, QVBoxLayout, QWidget

from ..demo import DemoMedia, DemoTranscriber, DemoTranslator
from ..hardware import choose_compute, detect_hardware
from ..media import FFmpegService
from ..pipeline import PipelineRequest, SubtitlePipeline
from ..projects import ProjectStore
from ..settings import AppSettings
from ..transcription import FasterWhisperTranscriber
from .editor import SubtitleEditor
from .new_job import NewJobView


class WorkerSignals(QObject):
    completed = Signal(object)
    failed = Signal(str)


class PipelineWorker(QRunnable):
    def __init__(self, pipeline, request):
        super().__init__(); self.pipeline, self.request, self.signals = pipeline, request, WorkerSignals()

    @Slot()
    def run(self):
        try: self.signals.completed.emit(self.pipeline.run(self.request))
        except Exception as exc: self.signals.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self, demo: bool = False, output_directory: Path | None = None):
        super().__init__(); self.demo = demo; self.output_directory = output_directory; self.thread_pool = QThreadPool.globalInstance()
        self.setWindowTitle("QuietCaption Studio"); self.resize(1100, 720); self.setMinimumSize(820, 560)
        root = QWidget(); shell = QHBoxLayout(root); shell.setContentsMargins(0, 0, 0, 0); shell.setSpacing(0)
        sidebar = QFrame(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(190); side = QVBoxLayout(sidebar)
        brand = QLabel("QuietCaption\nStudio"); brand.setStyleSheet("font-size: 21px; font-weight: 600; padding: 18px 10px")
        self.navigation = QListWidget(); self.navigation.setObjectName("navigation")
        for label in ("New job", "Queue", "Models", "Settings"): self.navigation.addItem(QListWidgetItem(label))
        self.navigation.setCurrentRow(0); self.offline_badge = QLabel("● Offline processing"); self.offline_badge.setObjectName("badge")
        side.addWidget(brand); side.addWidget(self.navigation); side.addStretch(); side.addWidget(self.offline_badge)
        self.pages = QStackedWidget(); self.new_job = NewJobView(); self.pages.addWidget(self.new_job)
        self.queue_page = self._queue_page()
        self.models_page = self._placeholder("Local models", "Install and update transcription or translation models here. Downloads always require confirmation.")
        self.settings_page = self._placeholder("Settings", "Output, performance, accessibility, and privacy preferences.")
        for page in (self.queue_page, self.models_page, self.settings_page): self.pages.addWidget(page)
        shell.addWidget(sidebar); shell.addWidget(self.pages, 1); self.setCentralWidget(root)
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        compute = choose_compute(detect_hardware()); self.new_job.compute.setText(f"{compute.label} · automatic fallback")
        self.compute = compute
        self.new_job.generateRequested.connect(self._start_jobs)
        self.statusBar().showMessage("Ready — media and transcripts stay on this device")

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
        layout.addWidget(heading); layout.addWidget(self.queue_status); layout.addWidget(self.queue_progress); layout.addStretch()
        return page

    def _start_jobs(self, files):
        if not files: return
        self.navigation.setCurrentRow(1); self.queue_progress.show(); self.queue_status.setText(f"Processing {files[0].name} locally…")
        self.new_job.generate.setEnabled(False)
        target_names = {"Spanish": "es", "French": "fr", "German": "de"}
        selected = self.new_job.target_language.currentText(); targets = [target_names[selected]] if selected in target_names else []
        formats = {"SRT": ["srt"], "VTT": ["vtt"], "SRT + VTT": ["srt", "vtt"], "SRT + VTT + TXT": ["srt", "vtt", "txt"]}[self.new_job.output_format.currentText()]
        output = self.output_directory or files[0].parent / "QuietCaption Output"
        if self.demo:
            pipeline = SubtitlePipeline(DemoMedia(), DemoTranscriber(), DemoTranslator())
        else:
            model = {"Small — balanced": "small", "Medium — accurate": "medium", "Large v3 — highest accuracy": "large-v3"}[self.new_job.model.currentText()]
            pipeline = SubtitlePipeline(FFmpegService(), FasterWhisperTranscriber(model, self.compute), None)
        request = PipelineRequest(files[0], output, targets, formats)
        worker = PipelineWorker(pipeline, request); worker.signals.completed.connect(self._completed); worker.signals.failed.connect(self._failed)
        self._worker = worker; self.thread_pool.start(worker)

    @Slot(object)
    def _completed(self, result):
        self.queue_progress.hide(); self.queue_status.setText(f"Completed · {len(result.exports)} subtitle files created")
        self.new_job.generate.setEnabled(True)
        project = ProjectStore(result.project_path).load()
        editor = SubtitleEditor(project.tracks[-1]); editor.setObjectName("editor")
        self.pages.addWidget(editor); self.pages.setCurrentWidget(editor)
        self.statusBar().showMessage(f"Saved to {result.project_path.parent}")

    @Slot(str)
    def _failed(self, message):
        self.queue_progress.hide(); self.queue_status.setText("Job failed — no source files were modified")
        self.new_job.generate.setEnabled(True)
        QMessageBox.critical(self, "QuietCaption could not finish", message)
