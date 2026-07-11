from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget

from ..languages import default_registry
from ..models import built_in_catalog
from .setup_wizard import SetupPanel


class ModelsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent); self.setObjectName("modelsView")
        layout = QVBoxLayout(self); layout.setContentsMargins(28, 24, 28, 24); layout.setSpacing(12)
        heading = QLabel("Local models"); heading.setStyleSheet("font-size: 26px; font-weight: 600")
        subtitle = QLabel("Install, verify, benchmark, update, and remove offline inference models."); subtitle.setObjectName("muted")
        self.setup_panel = SetupPanel()
        self.model_list = QListWidget(); self.model_list.setAccessibleName("Available local models")
        registry = default_registry()
        for model in built_in_catalog(registry):
            self.model_list.addItem(QListWidgetItem(f"{model.id}\n{model.kind.title()} · {len(model.languages)} languages · {model.size_mb / 1000:.1f} GB"))
        actions = QHBoxLayout()
        self.install_button = QPushButton("Install selected"); self.verify_button = QPushButton("Verify"); self.open_button = QPushButton("Open model folder")
        for button in (self.install_button, self.verify_button, self.open_button): actions.addWidget(button)
        actions.addStretch()
        self.status = QLabel("Choose Automated setup or Custom setup to configure this computer."); self.status.setObjectName("muted")
        self.setup_panel.automatedRequested.connect(lambda plan: self.status.setText(f"Automated plan ready: {plan.transcription_model} + {plan.translation_model}. Confirmation is required before downloading."))
        self.setup_panel.customRequested.connect(lambda scan: self.status.setText("Custom setup ready. Select compatible models from the catalog below."))
        self.install_button.clicked.connect(self._install)
        self.verify_button.clicked.connect(lambda: self.status.setText("Integrity verification requires an installed model; no files were changed."))
        self.open_button.clicked.connect(lambda: self.status.setText("The model directory is configured in Settings → Storage and models."))
        layout.addWidget(heading); layout.addWidget(subtitle); layout.addWidget(self.setup_panel); layout.addWidget(self.model_list); layout.addLayout(actions); layout.addWidget(self.status)

    def _install(self):
        item = self.model_list.currentItem()
        self.status.setText("Select a model first." if item is None else f"{item.text().splitlines()[0]} selected. Review its license and storage requirements before download.")

