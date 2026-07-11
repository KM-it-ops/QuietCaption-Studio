from pathlib import Path

from PySide6.QtCore import Qt

from quietcaption.languages import default_registry
from quietcaption.models import built_in_catalog
from quietcaption.settings import AppSettings, SettingsStore
from quietcaption.ui.main_window import MainWindow


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
    qtbot.mouseClick(window.settings_page.technical_button, Qt.LeftButton)
    assert settings.load().interface_mode == "technical"
    assert window.new_job.advanced_panel.isVisibleTo(window)


def test_setup_view_offers_automated_and_custom_paths(qtbot):
    window = MainWindow(demo=True); qtbot.addWidget(window)
    setup = window.models_page.setup_panel
    assert setup.automated_button.text() == "Automated setup"
    assert setup.custom_button.text() == "Custom setup"
    assert setup.findings_list.count() >= 4

