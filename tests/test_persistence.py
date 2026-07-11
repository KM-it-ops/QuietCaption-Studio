import logging

from quietcaption.diagnostics import PrivacyFilter, redact_path
from quietcaption.domain import Project, SubtitleSegment, SubtitleTrack
from quietcaption.projects import ProjectStore
from quietcaption.settings import AppSettings, SettingsStore


def test_settings_and_project_are_saved_atomically(tmp_path):
    settings_path = tmp_path / "settings.json"
    SettingsStore(settings_path).save(AppSettings(theme="dark"))
    assert SettingsStore(settings_path).load().theme == "dark"
    project = Project.new("secret.mp4", SubtitleTrack("en", [SubtitleSegment("a", 0, 1, "private")]))
    path = tmp_path / "project.qcp"
    ProjectStore(path).save(project)
    assert ProjectStore(path).load() == project
    assert not list(tmp_path.glob("*.tmp"))


def test_diagnostics_redact_paths_and_transcript(caplog):
    caplog.handler.addFilter(PrivacyFilter(["private words"]))
    with caplog.at_level(logging.INFO):
        logging.info("processing C:\\Users\\me\\secret.mp4 private words")
    assert "secret.mp4" not in caplog.text
    assert "private words" not in caplog.text
    assert redact_path("C:\\Users\\me\\secret.mp4") == "<media>"
