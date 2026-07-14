from pathlib import Path

from platformdirs import user_data_path
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget

from ..languages import default_registry
from ..model_service import ModelService
from ..models import ModelRegistry, built_in_catalog
from .setup_wizard import SetupPanel


class ModelWorkerSignals(QObject):
    completed = Signal(object)
    failed = Signal(str)


class ModelWorker(QRunnable):
    def __init__(self, operation):
        super().__init__(); self.operation = operation; self.signals = ModelWorkerSignals()

    @Slot()
    def run(self):
        try: self.signals.completed.emit(self.operation())
        except Exception as exc: self.signals.failed.emit(str(exc))


class ModelsView(QWidget):
    def __init__(self, service=None, parent=None):
        super().__init__(parent); self.setObjectName("modelsView")
        self.registry_data = default_registry(); self.catalog = built_in_catalog(self.registry_data)
        self.service = service or ModelService(ModelRegistry(user_data_path("QuietCaption Studio") / "models", self.catalog))
        self.thread_pool = QThreadPool.globalInstance()
        layout = QVBoxLayout(self); layout.setContentsMargins(28, 24, 28, 24); layout.setSpacing(12)
        heading = QLabel("Local models"); heading.setStyleSheet("font-size: 26px; font-weight: 600")
        subtitle = QLabel("Install, verify, benchmark, update, and remove offline inference models."); subtitle.setObjectName("muted")
        self.setup_panel = SetupPanel()
        self.model_list = QListWidget(); self.model_list.setAccessibleName("Available local models")
        for model in self.catalog:
            item = QListWidgetItem(f"{model.id}\n{model.kind.title()} · {len(model.languages)} languages · {model.size_mb / 1000:.1f} GB")
            item.setData(Qt.UserRole, model.id); self.model_list.addItem(item)
        actions = QHBoxLayout()
        self.install_button = QPushButton("Install selected"); self.verify_button = QPushButton("Verify"); self.activate_button = QPushButton("Activate"); self.remove_button = QPushButton("Remove")
        for button in (self.install_button, self.verify_button, self.activate_button, self.remove_button): actions.addWidget(button)
        actions.addStretch()
        self.status = QLabel("Choose Automated setup or Custom setup to configure this computer."); self.status.setObjectName("muted")
        self.setup_panel.automatedRequested.connect(self._automated_setup)
        self.setup_panel.customRequested.connect(lambda scan: self.status.setText("Custom setup ready. Select compatible models from the catalog below."))
        self.install_button.clicked.connect(self._install)
        self.verify_button.clicked.connect(self._verify); self.activate_button.clicked.connect(self._activate); self.remove_button.clicked.connect(self._remove)
        layout.addWidget(heading); layout.addWidget(subtitle); layout.addWidget(self.setup_panel); layout.addWidget(self.model_list); layout.addLayout(actions); layout.addWidget(self.status)

    def _install(self):
        descriptor = self._selected()
        if descriptor is None: self.status.setText("Select a model first."); return
        answer = QMessageBox.question(self, "Install local model", f"Download {descriptor.id} ({descriptor.size_mb / 1000:.1f} GB)?\n\nSource: {descriptor.url}\nLicense: {descriptor.license}", QMessageBox.Yes | QMessageBox.No)
        if answer != QMessageBox.Yes: return
        self.install_button.setEnabled(False); self.status.setText(f"Downloading {descriptor.id} from its pinned revision…")
        worker = ModelWorker(lambda: self.service.install(descriptor)); worker.signals.completed.connect(lambda _: self._operation_done(f"Installed {descriptor.id}.")); worker.signals.failed.connect(self._operation_failed)
        self._worker = worker; self.thread_pool.start(worker)

    def _automated_setup(self, plan):
        models = [next(item for item in self.catalog if item.id == plan.transcription_model), next(item for item in self.catalog if item.id == plan.translation_model)]
        answer = QMessageBox.question(self, "Automated local setup", f"Install the recommended offline bundle?\n\nDownload: {plan.download_gb:g} GB\nDisk after installation: {plan.disk_gb:g} GB\n\nNo media or transcripts will be uploaded.", QMessageBox.Yes | QMessageBox.No)
        if answer != QMessageBox.Yes: return
        self.setup_panel.automated_button.setEnabled(False); self.status.setText("Automated setup is downloading and verifying the recommended models…")
        def operation():
            for model in models:
                self.service.install(model); self.service.activate(model)
            return models
        worker = ModelWorker(operation); worker.signals.completed.connect(lambda _: self._automated_done()); worker.signals.failed.connect(self._automated_failed)
        self._worker = worker; self.thread_pool.start(worker)

    def _automated_done(self):
        self.setup_panel.automated_button.setEnabled(True); self.status.setText("Automated setup complete. Transcription and translation models are active.")

    def _automated_failed(self, message):
        self.setup_panel.automated_button.setEnabled(True); self.status.setText(f"Automated setup stopped safely: {message}")

    def _selected(self):
        item = self.model_list.currentItem()
        return next((model for model in self.catalog if item and model.id == item.data(Qt.UserRole)), None)

    def _verify(self):
        model = self._selected(); self.status.setText("Select a model first." if model is None else (f"{model.id} passed integrity verification." if self.service.verify(model) else f"{model.id} is missing or needs repair."))

    def _activate(self):
        model = self._selected()
        try: self.status.setText("Select a model first." if model is None else f"Activated {self.service.activate(model).id}.")
        except Exception as exc: self.status.setText(str(exc))

    def _remove(self):
        model = self._selected()
        if model is None: self.status.setText("Select a model first."); return
        if QMessageBox.question(self, "Remove local model", f"Remove {model.id} from this computer?", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes: return
        try: self.service.remove(model); self.status.setText(f"Removed {model.id}.")
        except Exception as exc: self.status.setText(str(exc))

    def _operation_done(self, message):
        self.install_button.setEnabled(True); self.status.setText(message)

    def _operation_failed(self, message):
        self.install_button.setEnabled(True); self.status.setText(f"Installation failed safely: {message}")
