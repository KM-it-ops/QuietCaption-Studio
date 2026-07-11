from dataclasses import replace

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget


class SettingsView(QWidget):
    modeChanged = Signal(str)

    def __init__(self, store, parent=None):
        super().__init__(parent); self.setObjectName("settingsView"); self.store = store; self.settings = store.load()
        layout = QVBoxLayout(self); layout.setContentsMargins(28, 24, 28, 24)
        heading = QLabel("Settings"); heading.setStyleSheet("font-size: 26px; font-weight: 600")
        mode_row = QHBoxLayout(); self.everyday_button = QPushButton("Everyday"); self.technical_button = QPushButton("Technical")
        self.everyday_button.setCheckable(True); self.technical_button.setCheckable(True)
        mode_row.addWidget(QLabel("Interface")); mode_row.addWidget(self.everyday_button); mode_row.addWidget(self.technical_button); mode_row.addStretch()
        self.tabs = QTabWidget(); self.tabs.setAccessibleName("Settings categories")
        self.output_path = QLineEdit(self.settings.output_directory); self.theme = QComboBox(); self.theme.addItems(["system", "light", "dark"]); self.theme.setCurrentText(self.settings.theme)
        self.update_checks = QCheckBox("Check for catalog and application updates"); self.update_checks.setChecked(self.settings.update_checks)
        self.reduced_motion = QCheckBox("Reduce interface motion"); self.reduced_motion.setChecked(self.settings.reduced_motion)
        self.cache_limit = QSpinBox(); self.cache_limit.setRange(1, 1000); self.cache_limit.setValue(self.settings.cache_limit_gb); self.cache_limit.setSuffix(" GB")
        self.tabs.addTab(self._form([("Output folder", self.output_path), ("Theme", self.theme)]), "General & output")
        self.tabs.addTab(self._form([("Model cache limit", self.cache_limit)]), "Storage & models")
        self.tabs.addTab(self._form([("Network", self.update_checks), ("Accessibility", self.reduced_motion)]), "Privacy & accessibility")
        actions = QHBoxLayout(); self.save_button = QPushButton("Save settings"); self.save_button.setObjectName("primary"); self.revert_button = QPushButton("Revert")
        actions.addStretch(); actions.addWidget(self.revert_button); actions.addWidget(self.save_button)
        self.status = QLabel("Changes are stored locally."); self.status.setObjectName("muted")
        layout.addWidget(heading); layout.addLayout(mode_row); layout.addWidget(self.tabs); layout.addWidget(self.status); layout.addLayout(actions)
        self.everyday_button.clicked.connect(lambda: self.set_mode("everyday")); self.technical_button.clicked.connect(lambda: self.set_mode("technical"))
        self.save_button.clicked.connect(self.save); self.revert_button.clicked.connect(self.reload); self._sync_mode()

    @staticmethod
    def _form(rows):
        page = QWidget(); form = QFormLayout(page)
        for label, widget in rows: form.addRow(label, widget)
        return page

    def _sync_mode(self):
        self.everyday_button.setChecked(self.settings.interface_mode == "everyday"); self.technical_button.setChecked(self.settings.interface_mode == "technical")

    def set_mode(self, mode):
        self.settings = replace(self.settings, interface_mode=mode); self.store.save(self.settings); self._sync_mode(); self.modeChanged.emit(mode); self.status.setText(f"{mode.title()} interface enabled.")

    def save(self):
        self.settings = replace(self.settings, output_directory=self.output_path.text(), theme=self.theme.currentText(), update_checks=self.update_checks.isChecked(), reduced_motion=self.reduced_motion.isChecked(), cache_limit_gb=self.cache_limit.value())
        self.store.save(self.settings); self.status.setText("Settings saved locally.")

    def reload(self):
        self.settings = self.store.load(); self.output_path.setText(self.settings.output_directory); self.theme.setCurrentText(self.settings.theme); self.update_checks.setChecked(self.settings.update_checks); self.reduced_motion.setChecked(self.settings.reduced_motion); self.cache_limit.setValue(self.settings.cache_limit_gb); self._sync_mode(); self.status.setText("Unsaved changes reverted.")

