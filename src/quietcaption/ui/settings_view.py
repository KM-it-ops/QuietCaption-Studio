from dataclasses import replace

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSizePolicy, QSpinBox, QTabWidget, QVBoxLayout, QWidget


class SettingsView(QWidget):
    modeChanged = Signal(str)
    settingsSaved = Signal(object)

    def __init__(self, store, parent=None):
        super().__init__(parent); self.setObjectName("settingsView"); self.store = store
        load_result = store.load_result(); self.settings = load_result.settings
        layout = QVBoxLayout(self); layout.setContentsMargins(28, 24, 28, 24)
        heading = QLabel("Settings"); heading.setStyleSheet("font-size: 26px; font-weight: 600")
        mode_row = QHBoxLayout(); self.everyday_button = QPushButton("Everyday"); self.technical_button = QPushButton("Technical")
        self.everyday_button.setCheckable(True); self.technical_button.setCheckable(True)
        mode_row.addWidget(QLabel("Interface")); mode_row.addWidget(self.everyday_button); mode_row.addWidget(self.technical_button); mode_row.addStretch()
        self.tabs = QTabWidget(); self.tabs.setAccessibleName("Settings categories"); self.tabs.setMinimumHeight(230); self.tabs.setMaximumHeight(320); self.tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.settings_search = QLineEdit(); self.settings_search.setPlaceholderText("Search settings in Technical mode"); self.settings_search.setAccessibleName("Search settings")
        self.output_path = QLineEdit(self.settings.output_directory); self.output_browse = QPushButton("Browse…")
        self.model_path = QLineEdit(self.settings.model_directory); self.model_browse = QPushButton("Browse…")
        self.theme = QComboBox(); self.theme.addItems(["system", "light", "dark"]); self.theme.setCurrentText(self.settings.theme)
        self.update_checks = QCheckBox("Check for catalog and application updates"); self.update_checks.setChecked(self.settings.update_checks)
        self.reduced_motion = QCheckBox("Reduce interface motion"); self.reduced_motion.setChecked(self.settings.reduced_motion)
        self.cache_limit = QSpinBox(); self.cache_limit.setRange(1, 1000); self.cache_limit.setValue(self.settings.cache_limit_gb); self.cache_limit.setSuffix(" GB")
        self.compute_device = QComboBox(); self.compute_device.addItems(["automatic", "cpu", "cuda"]); self.compute_device.setCurrentText(self.settings.compute_device)
        self.gpu_fallback = QCheckBox("Use CPU when requested CUDA is unavailable"); self.gpu_fallback.setChecked(self.settings.gpu_fallback)
        self.queue_concurrency = QSpinBox(); self.queue_concurrency.setRange(1, 8); self.queue_concurrency.setValue(self.settings.queue_concurrency)
        self.subtitle_size = QSpinBox(); self.subtitle_size.setRange(10, 96); self.subtitle_size.setValue(self.settings.subtitle_font_size); self.subtitle_size.setSuffix(" px")
        self.line_length = QSpinBox(); self.line_length.setRange(20, 80); self.line_length.setValue(self.settings.subtitle_line_length)
        self.log_level = QComboBox(); self.log_level.addItems(["minimal", "standard", "technical"]); self.log_level.setCurrentText(self.settings.log_level)
        self.tabs.addTab(self._form([("Output folder", self._path_row(self.output_path, self.output_browse)), ("Theme", self.theme)]), "General")
        self.tabs.addTab(self._form([("Model folder (applies after restart)", self._path_row(self.model_path, self.model_browse)), ("Model cache limit", self.cache_limit)]), "Models")
        self.tabs.addTab(self._form([("Compute device", self.compute_device), ("GPU fallback", self.gpu_fallback), ("Concurrent jobs", self.queue_concurrency)]), "Processing")
        self.tabs.addTab(self._form([("Font size", self.subtitle_size), ("Characters per line", self.line_length)]), "Subtitles")
        self.tabs.addTab(self._form([("Catalog and app update checks", self.update_checks), ("Accessibility", self.reduced_motion)]), "Privacy")
        self.tabs.addTab(self._form([("Diagnostic detail", self.log_level)]), "Diagnostics")
        actions = QHBoxLayout(); self.export_button = QPushButton("Export"); self.import_button = QPushButton("Import"); self.reset_section_button = QPushButton("Reset section"); self.save_button = QPushButton("Save settings"); self.save_button.setObjectName("primary"); self.revert_button = QPushButton("Revert")
        actions.addWidget(self.export_button); actions.addWidget(self.import_button); actions.addWidget(self.reset_section_button); actions.addStretch(); actions.addWidget(self.revert_button); actions.addWidget(self.save_button)
        self.status = QLabel(load_result.warning or "Changes are stored locally."); self.status.setObjectName("muted")
        layout.addWidget(heading); layout.addLayout(mode_row); layout.addWidget(self.settings_search); layout.addWidget(self.tabs); layout.addStretch(); layout.addWidget(self.status); layout.addLayout(actions)
        self.everyday_button.clicked.connect(lambda: self.set_mode("everyday")); self.technical_button.clicked.connect(lambda: self.set_mode("technical"))
        self.output_browse.clicked.connect(lambda: self._choose_directory(self.output_path, "Choose output folder"))
        self.model_browse.clicked.connect(lambda: self._choose_directory(self.model_path, "Choose model folder"))
        self.export_button.clicked.connect(self.export_settings); self.import_button.clicked.connect(self.import_settings); self.reset_section_button.clicked.connect(self.reset_section)
        self.settings_search.textChanged.connect(self._search_settings)
        self.save_button.clicked.connect(self.save); self.revert_button.clicked.connect(self.reload); self._sync_mode()

    @staticmethod
    def _form(rows):
        page = QWidget(); form = QFormLayout(page)
        for label, widget in rows: form.addRow(label, widget)
        return page

    @staticmethod
    def _path_row(field, button):
        container = QWidget(); row = QHBoxLayout(container); row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(field, 1); row.addWidget(button)
        return container

    def _choose_directory(self, field, title):
        selected = QFileDialog.getExistingDirectory(self, title, field.text())
        if selected:
            field.setText(selected)

    def _sync_mode(self):
        self.everyday_button.setChecked(self.settings.interface_mode == "everyday"); self.technical_button.setChecked(self.settings.interface_mode == "technical")
        self.settings_search.setVisible(self.settings.interface_mode == "technical")

    def _search_settings(self, query):
        value = query.casefold().strip()
        if not value:
            return
        keywords = (
            ("output theme general", 0),
            ("model cache storage folder", 1),
            ("processing compute cpu gpu cuda fallback queue concurrent", 2),
            ("subtitle font caption line appearance", 3),
            ("privacy network update accessibility motion", 4),
            ("diagnostic log recovery", 5),
        )
        match = next((index for terms, index in keywords if any(word in terms for word in value.split())), None)
        if match is not None:
            self.tabs.setCurrentIndex(match)
            self.status.setText(f"Showing {self.tabs.tabText(match)} settings.")

    def set_mode(self, mode):
        self.settings = replace(self.settings, interface_mode=mode); self.store.save(self.settings); self._sync_mode(); self.modeChanged.emit(mode); self.status.setText(f"{mode.title()} interface enabled.")

    def save(self):
        self.settings = replace(self.settings, output_directory=self.output_path.text(), model_directory=self.model_path.text(), theme=self.theme.currentText(), update_checks=self.update_checks.isChecked(), reduced_motion=self.reduced_motion.isChecked(), cache_limit_gb=self.cache_limit.value(), compute_device=self.compute_device.currentText(), gpu_fallback=self.gpu_fallback.isChecked(), queue_concurrency=self.queue_concurrency.value(), subtitle_font_size=self.subtitle_size.value(), subtitle_line_length=self.line_length.value(), log_level=self.log_level.currentText())
        try:
            self.store.save(self.settings); self.status.setText("Settings saved locally."); self.settingsSaved.emit(self.settings)
        except ValueError as exc:
            self.status.setText(f"Settings were not saved: {exc}")

    def reload(self):
        load_result = self.store.load_result(); self.settings = load_result.settings; self.output_path.setText(self.settings.output_directory); self.model_path.setText(self.settings.model_directory); self.theme.setCurrentText(self.settings.theme); self.update_checks.setChecked(self.settings.update_checks); self.reduced_motion.setChecked(self.settings.reduced_motion); self.cache_limit.setValue(self.settings.cache_limit_gb); self.compute_device.setCurrentText(self.settings.compute_device); self.gpu_fallback.setChecked(self.settings.gpu_fallback); self.queue_concurrency.setValue(self.settings.queue_concurrency); self.subtitle_size.setValue(self.settings.subtitle_font_size); self.line_length.setValue(self.settings.subtitle_line_length); self.log_level.setCurrentText(self.settings.log_level); self._sync_mode(); self.status.setText(load_result.warning or "Unsaved changes reverted.")

    def export_settings(self):
        destination, _ = QFileDialog.getSaveFileName(self, "Export settings", "quietcaption-settings.json", "JSON files (*.json)")
        if not destination: return
        try:
            self.store.export_to(destination); self.status.setText("Portable settings exported without machine-local paths.")
        except (OSError, ValueError) as exc:
            self.status.setText(f"Settings export failed: {exc}")

    def import_settings(self):
        source, _ = QFileDialog.getOpenFileName(self, "Import settings", "", "JSON files (*.json)")
        if not source: return
        try:
            self.store.import_from(source); self.reload(); self.status.setText("Settings imported and validated.")
        except (OSError, ValueError) as exc:
            self.status.setText(f"Settings import rejected: {exc}")

    def reset_section(self):
        sections = ("general", "models", "processing", "subtitle", "privacy", "diagnostics")
        section = sections[self.tabs.currentIndex()]
        if QMessageBox.question(self, "Reset settings section", f"Reset {self.tabs.tabText(self.tabs.currentIndex())} to defaults?", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes: return
        self.store.reset_section(section); self.reload(); self.status.setText(f"{self.tabs.tabText(self.tabs.currentIndex())} reset to defaults.")
