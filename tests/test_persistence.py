import logging

import pytest

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


def test_project_partial_temp_is_removed_when_write_raises(tmp_path, monkeypatch):
    project = Project.new("secret.mp4", SubtitleTrack("en", [SubtitleSegment("a", 0, 1, "private")]))
    path = tmp_path / "project.qcp"
    path.write_text("existing project", encoding="utf-8")
    temporary = tmp_path / "project.qcp.tmp"
    real_write_text = type(path).write_text

    def partial_write_then_fail(target, content, *args, **kwargs):
        if target == temporary:
            real_write_text(target, "partial", encoding="utf-8")
            raise OSError("disk write failed")
        return real_write_text(target, content, *args, **kwargs)

    monkeypatch.setattr(type(path), "write_text", partial_write_then_fail)

    with pytest.raises(OSError, match="disk write failed"):
        ProjectStore(path).save(project)

    assert path.read_text(encoding="utf-8") == "existing project"
    assert not temporary.exists()


def test_diagnostics_redact_paths_and_transcript(caplog):
    caplog.handler.addFilter(PrivacyFilter(["private words"]))
    with caplog.at_level(logging.INFO):
        logging.info("processing C:\\Users\\me\\secret.mp4 private words")
    assert "secret.mp4" not in caplog.text
    assert "private words" not in caplog.text
    assert redact_path("C:\\Users\\me\\secret.mp4") == "<media>"
