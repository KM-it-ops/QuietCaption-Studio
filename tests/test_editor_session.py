from pathlib import Path

import pytest

import quietcaption.atomic_files as atomic_module
import quietcaption.editor_session as session_module
from quietcaption.domain import Project, SubtitleSegment, SubtitleTrack
from quietcaption.editor_session import EditorSession
from quietcaption.projects import ProjectStore


def make_session(tmp_path: Path, formats=("srt", "vtt", "txt")) -> EditorSession:
    track = SubtitleTrack("en", [SubtitleSegment("a", 0, 1, "old")])
    project = Project("project-id", "clip.mp4", [track])
    path = tmp_path / "clip.qcp"
    ProjectStore(path).save(project)
    exports = [tmp_path / f"clip.en.{extension}" for extension in formats]
    for export in exports:
        export.write_text("durable old", encoding="utf-8")
    return EditorSession(project, path, 0, exports)


def test_save_reopens_edited_project_and_regenerates_selected_outputs(tmp_path):
    session = make_session(tmp_path)
    session.set_segment_text(0, "edited text")
    session.selected_formats = {"srt", "txt"}

    session.save()

    reopened = ProjectStore(session.project_path).load()
    assert reopened.tracks[0].segments[0].text == "edited text"
    assert "edited text" in (tmp_path / "clip.en.srt").read_text(encoding="utf-8")
    assert "edited text" in (tmp_path / "clip.en.txt").read_text(encoding="utf-8")
    assert session.dirty is False


def test_save_as_uses_new_project_base_without_changing_project_identity(tmp_path):
    session = make_session(tmp_path, ("srt",))
    session.set_segment_text(0, "renamed")
    destination = tmp_path / "renamed.qcp"

    session.save_as(destination)

    saved = ProjectStore(destination).load()
    assert saved.id == "project-id"
    assert saved.tracks[0].segments[0].text == "renamed"
    assert (tmp_path / "renamed.en.srt").exists()
    assert session.project_path == destination
    assert session.export_paths == {"srt": tmp_path / "renamed.en.srt"}


def test_save_as_refuses_to_replace_an_existing_project(tmp_path):
    session = make_session(tmp_path, ("srt",))
    session.set_segment_text(0, "edited")
    destination = tmp_path / "existing.qcp"
    destination.write_text("keep me", encoding="utf-8")

    with pytest.raises(FileExistsError):
        session.save_as(destination)

    assert destination.read_text(encoding="utf-8") == "keep me"
    assert session.project_path == tmp_path / "clip.qcp"
    assert session.dirty


def test_failed_save_preserves_all_originals_and_writes_recovery(tmp_path, monkeypatch):
    session = make_session(tmp_path, ("srt", "vtt"))
    session.set_segment_text(0, "recoverable edit")
    original_project = session.project_path.read_text(encoding="utf-8")
    original_srt = session.export_paths["srt"].read_text(encoding="utf-8")
    original_vtt = session.export_paths["vtt"].read_text(encoding="utf-8")
    real_replace = atomic_module.os.replace

    def fail_vtt(source, destination):
        if Path(destination).suffix == ".vtt":
            raise OSError("disk full")
        return real_replace(source, destination)

    monkeypatch.setattr(atomic_module.os, "replace", fail_vtt)

    with pytest.raises(OSError, match="disk full"):
        session.save()

    assert session.project_path.read_text(encoding="utf-8") == original_project
    assert session.export_paths["srt"].read_text(encoding="utf-8") == original_srt
    assert session.export_paths["vtt"].read_text(encoding="utf-8") == original_vtt
    assert ProjectStore(session.recovery_path).load().tracks[0].segments[0].text == "recoverable edit"
    assert session.dirty


def test_render_failure_keeps_originals_and_writes_recovery(tmp_path, monkeypatch):
    session = make_session(tmp_path, ("srt",))
    session.set_segment_text(0, "recover after render failure")
    original_project = session.project_path.read_text(encoding="utf-8")
    original_export = session.export_paths["srt"].read_text(encoding="utf-8")
    monkeypatch.setattr(session_module.SrtWriter, "render", lambda *_: (_ for _ in ()).throw(ValueError("cannot render")))

    with pytest.raises(ValueError, match="cannot render"):
        session.save()

    assert session.project_path.read_text(encoding="utf-8") == original_project
    assert session.export_paths["srt"].read_text(encoding="utf-8") == original_export
    assert ProjectStore(session.recovery_path).load().tracks[0].segments[0].text == "recover after render failure"


def test_recovery_can_be_loaded_dirty_or_discarded(tmp_path):
    session = make_session(tmp_path, ("srt",))
    session.set_segment_text(0, "recovered")
    session.write_recovery()

    recovered = EditorSession.open(session.project_path, 0, list(session.export_paths.values()), lambda _: "recover")
    assert recovered.track.segments[0].text == "recovered"
    assert recovered.dirty

    discarded = EditorSession.open(session.project_path, 0, list(session.export_paths.values()), lambda _: "discard")
    assert discarded.track.segments[0].text == "old"
    assert not discarded.recovery_path.exists()
    assert not discarded.dirty


def test_successful_save_removes_recovery(tmp_path):
    session = make_session(tmp_path, ("srt",))
    session.set_segment_text(0, "edited")
    session.write_recovery()
    assert session.recovery_path.exists()

    session.save()

    assert not session.recovery_path.exists()
