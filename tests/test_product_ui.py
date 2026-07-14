from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from quietcaption.languages import default_registry
from quietcaption.models import built_in_catalog
from quietcaption.models import ModelRegistry
from quietcaption.settings import AppSettings, SettingsStore
from quietcaption.ui.main_window import MainWindow
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
