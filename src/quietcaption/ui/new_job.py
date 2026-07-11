from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QListWidget, QPushButton, QSpinBox, QVBoxLayout, QWidget

from ..languages import default_registry
from ..models import built_in_catalog
from .drop_zone import DropZone
from .language_combo import CapabilityLanguageCombo


MEDIA_SUFFIXES = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".mp3", ".wav", ".m4a", ".flac", ".ogg"}


class NewJobView(QWidget):
    generateRequested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent); self.files: list[Path] = []
        layout = QVBoxLayout(self); layout.setContentsMargins(28, 24, 28, 24); layout.setSpacing(14)
        heading = QLabel("Create subtitles"); heading.setStyleSheet("font-size: 26px; font-weight: 600")
        self.drop_zone = DropZone(); self.drop_zone.setMinimumHeight(150)
        self.file_list = QListWidget(); self.file_list.setMaximumHeight(92); self.file_list.hide()
        form = QFormLayout(); form.setSpacing(12)
        registry = default_registry(); catalog = built_in_catalog(registry)
        whisper = next(item for item in catalog if item.kind == "transcription"); nllb = next(item for item in catalog if item.kind == "translation")
        self.source_language = CapabilityLanguageCombo(registry, whisper, "Detect automatically", "auto")
        self.target_language = CapabilityLanguageCombo(registry, nllb, "No translation", "none")
        self.model = QComboBox(); self.model.addItems(["Small — balanced", "Medium — accurate", "Large v3 — highest accuracy"])
        self.output_format = QComboBox(); self.output_format.addItems(["SRT + VTT", "SRT", "VTT", "SRT + VTT + TXT"])
        form.addRow("Spoken language", self.source_language); form.addRow("Translate offline to", self.target_language)
        form.addRow("Transcription model", self.model); form.addRow("Output formats", self.output_format)
        actions = QHBoxLayout(); self.compute = QLabel("CPU mode · automatic fallback"); self.compute.setObjectName("muted")
        self.generate = QPushButton("Generate subtitles"); self.generate.setObjectName("primary"); self.generate.setEnabled(False)
        actions.addWidget(self.compute); actions.addStretch(); actions.addWidget(self.generate)
        for widget in (heading, self.drop_zone, self.file_list): layout.addWidget(widget)
        self.advanced_panel = QFrame(); advanced = QFormLayout(self.advanced_panel); self.beam_size = QSpinBox(); self.beam_size.setRange(1, 20); self.beam_size.setValue(5); advanced.addRow("Beam size", self.beam_size); self.advanced_panel.hide()
        layout.addLayout(form); layout.addWidget(self.advanced_panel); layout.addStretch(); layout.addLayout(actions)
        self.drop_zone.filesDropped.connect(self.add_files); self.drop_zone.browse.clicked.connect(self.browse)
        self.generate.clicked.connect(lambda: self.generateRequested.emit(self.files.copy()))

    def set_interface_mode(self, mode: str):
        self.advanced_panel.setVisible(mode == "technical")

    def browse(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose media", "", "Media files (*.mp4 *.mkv *.mov *.avi *.webm *.mp3 *.wav *.m4a *.flac *.ogg)")
        self.add_files([Path(item) for item in paths])

    def add_files(self, paths):
        for path in paths:
            path = Path(path)
            if path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES and path not in self.files:
                self.files.append(path); self.file_list.addItem(f"{path.name}  ·  Ready")
        self.file_list.setVisible(bool(self.files)); self.generate.setEnabled(bool(self.files))
