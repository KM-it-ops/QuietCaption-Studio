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
    modelActivated = Signal(object)

    def __init__(self, service=None, parent=None):
        super().__init__(parent); self.setObjectName("modelsView")
        self.registry_data = default_registry(); self.catalog = built_in_catalog(self.registry_data)
        self.service = service or ModelService(ModelRegistry(user_data_path("QuietCaption Studio") / "models", self.catalog))
        self.thread_pool = QThreadPool.globalInstance()
        layout = QVBoxLayout(self); layout.setContentsMargins(28, 24, 28, 24); layout.setSpacing(12)
        heading = QLabel("Local models"); heading.setStyleSheet("font-size: 26px; font-weight: 600")
        subtitle = QLabel("Install, verify, update, repair, activate, and remove offline inference models."); subtitle.setObjectName("muted")
        self.setup_panel = SetupPanel()
        self.model_list = QListWidget(); self.model_list.setAccessibleName("Available local models"); self.model_list.setMaximumHeight(200)
        for model in self.catalog:
            item = QListWidgetItem(f"{model.id}\n{model.kind.title()} · {len(model.languages)} languages · {model.size_mb / 1000:.1f} GB")
            item.setData(Qt.UserRole, model.id); self.model_list.addItem(item)
        actions = QHBoxLayout()
        self.install_button = QPushButton("Install selected"); self.update_button = QPushButton("Update"); self.verify_button = QPushButton("Verify"); self.repair_button = QPushButton("Repair"); self.activate_button = QPushButton("Activate"); self.remove_button = QPushButton("Remove")
        self._lifecycle_controls = (self.install_button, self.update_button, self.verify_button, self.repair_button, self.activate_button, self.remove_button, self.setup_panel.automated_button)
        self._lifecycle_busy = False
        self._lifecycle_control_states = {}
        self._workers = set()
        for button in (self.install_button, self.update_button, self.verify_button, self.repair_button, self.activate_button, self.remove_button): actions.addWidget(button)
        actions.addStretch()
        self.status = QLabel("Choose Automated setup or Custom setup to configure this computer."); self.status.setObjectName("muted")
        self.setup_panel.automatedRequested.connect(self._automated_setup)
        self.setup_panel.customRequested.connect(lambda scan: self.status.setText("Custom setup ready. Select compatible models from the catalog below."))
        self.install_button.clicked.connect(self._install)
        self.update_button.clicked.connect(self._update); self.verify_button.clicked.connect(self._verify); self.repair_button.clicked.connect(self._repair); self.activate_button.clicked.connect(self._activate); self.remove_button.clicked.connect(self._remove)
        layout.addWidget(heading); layout.addWidget(subtitle); layout.addWidget(self.setup_panel); layout.addWidget(self.model_list); layout.addLayout(actions); layout.addWidget(self.status); layout.addStretch()

    def _install(self):
        descriptor = self._selected()
        if descriptor is None: self.status.setText("Select a model first."); return
        answer = QMessageBox.question(self, "Install local model", f"Download {descriptor.id} ({descriptor.size_mb / 1000:.1f} GB)?\n\nSource: {descriptor.url}\nLicense: {descriptor.license}", QMessageBox.Yes | QMessageBox.No)
        if answer != QMessageBox.Yes: return
        self._run_operation(
            f"Downloading {descriptor.id} from its pinned revision…",
            lambda: self.service.install(descriptor),
            lambda _: self.status.setText(f"Installed {descriptor.id}."),
        )

    def _automated_setup(self, plan):
        models = [next(item for item in self.catalog if item.id == plan.transcription_model), next(item for item in self.catalog if item.id == plan.translation_model)]
        answer = QMessageBox.question(self, "Automated local setup", f"Install the recommended offline bundle?\n\nDownload: {plan.download_gb:g} GB\nDisk after installation: {plan.disk_gb:g} GB\n\nNo media or transcripts will be uploaded.", QMessageBox.Yes | QMessageBox.No)
        if answer != QMessageBox.Yes: return
        self._run_operation(
            "Automated setup is downloading and verifying the recommended models…",
            lambda: self.service.install_and_activate(models),
            self._automated_done,
            failure_prefix="Automated setup stopped safely",
        )

    def _automated_done(self, models):
        self.status.setText("Automated setup complete. Transcription and translation models are active.")
        for model in models:
            self.modelActivated.emit(model)

    def _selected(self):
        item = self.model_list.currentItem()
        return next((model for model in self.catalog if item and model.id == item.data(Qt.UserRole)), None)

    def _verify(self):
        if self._lifecycle_busy: return
        model = self._selected(); self.status.setText("Select a model first." if model is None else (f"{model.id} passed integrity verification." if self.service.verify(model) else f"{model.id} is missing or needs repair."))

    def _repair(self):
        model = self._selected()
        if model is None: self.status.setText("Select a model first."); return
        if QMessageBox.question(self, "Repair local model", f"Re-download and repair {model.id}?", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes: return
        self._run_operation(f"Repairing {model.id}…", lambda: self.service.repair(model), lambda _: self.status.setText(f"Repaired {model.id}."))

    def _update(self):
        model = self._selected()
        if model is None: self.status.setText("Select a model first."); return
        if QMessageBox.question(self, "Update local model", f"Install the pinned catalog revision for {model.id}?", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes: return
        self._run_operation(f"Updating {model.id}…", lambda: self.service.update(model), lambda _: self.status.setText(f"Updated {model.id}."))

    def _set_lifecycle_busy(self, busy):
        if busy == self._lifecycle_busy:
            return
        self._lifecycle_busy = busy
        if busy:
            self._lifecycle_control_states = {control: control.isEnabled() for control in self._lifecycle_controls}
            for control in self._lifecycle_controls:
                control.setEnabled(False)
            return
        for control, enabled in self._lifecycle_control_states.items():
            control.setEnabled(enabled)
        self._lifecycle_control_states = {}

    def _run_operation(self, pending, operation, completed, failure_prefix="Operation stopped safely"):
        if self._lifecycle_busy:
            self.status.setText("Another model lifecycle operation is already in progress. Wait for it to finish and retry.")
            return
        self._set_lifecycle_busy(True)
        self.status.setText(pending)
        worker = ModelWorker(operation)
        self._workers.add(worker)
        worker.signals.completed.connect(lambda result, current=worker: self._lifecycle_done(current, completed, result))
        worker.signals.failed.connect(lambda message, current=worker: self._lifecycle_failed(current, failure_prefix, message))
        try:
            self.thread_pool.start(worker)
        except Exception as exc:
            self._lifecycle_failed(worker, failure_prefix, str(exc))

    def _lifecycle_done(self, worker, completed, result):
        self._workers.discard(worker)
        self._set_lifecycle_busy(False)
        completed(result)

    def _lifecycle_failed(self, worker, prefix, message):
        self._workers.discard(worker)
        self._set_lifecycle_busy(False)
        self.status.setText(f"{prefix}: {message}")

    def _reject_lifecycle_busy(self):
        if not self._lifecycle_busy:
            return False
        self.status.setText("Another model lifecycle operation is already in progress. Wait for it to finish and retry.")
        return True

    def _activate(self):
        if self._reject_lifecycle_busy(): return
        model = self._selected()
        try:
            if model is None:
                self.status.setText("Select a model first.")
            else:
                activated = self.service.activate(model)
                self.status.setText(f"Activated {activated.id}.")
                self.modelActivated.emit(activated)
        except Exception as exc: self.status.setText(str(exc))

    def _remove(self):
        if self._reject_lifecycle_busy(): return
        model = self._selected()
        if model is None: self.status.setText("Select a model first."); return
        if QMessageBox.question(self, "Remove local model", f"Remove {model.id} from this computer?", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes: return
        try: self.service.remove(model); self.status.setText(f"Removed {model.id}.")
        except Exception as exc: self.status.setText(str(exc))
