import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

import quietcaption.atomic_files as atomic_module
import quietcaption.editor_session as session_module
from quietcaption.domain import Project, SubtitleSegment, SubtitleTrack
from quietcaption.editor_session import EditorSession, SaveConflictError
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
    assert session.recovery_project().tracks[0].segments[0].text == "edited"


def test_save_as_refuses_existing_selected_export_and_writes_recovery(tmp_path):
    session = make_session(tmp_path, ("srt",))
    session.set_segment_text(0, "collision edit")
    destination = tmp_path / "renamed.qcp"
    export = tmp_path / "renamed.en.srt"
    export.write_text("keep export", encoding="utf-8")

    with pytest.raises(FileExistsError):
        session.save_as(destination)

    assert not destination.exists()
    assert export.read_text(encoding="utf-8") == "keep export"
    assert session.recovery_project().tracks[0].segments[0].text == "collision edit"


def test_save_as_race_at_project_publication_never_overwrites_and_recovers(tmp_path, monkeypatch):
    session = make_session(tmp_path, ("srt",))
    session.set_segment_text(0, "racing edit")
    destination = tmp_path / "raced.qcp"
    real_link = atomic_module.os.link

    def create_racer(source, target):
        target = Path(target)
        if target == destination:
            target.write_text("racer", encoding="utf-8")
        return real_link(source, target)

    monkeypatch.setattr(atomic_module.os, "link", create_racer)

    with pytest.raises(FileExistsError):
        session.save_as(destination)

    assert destination.read_text(encoding="utf-8") == "racer"
    assert session.project_path == tmp_path / "clip.qcp"
    assert session.recovery_project().tracks[0].segments[0].text == "racing edit"


def test_save_as_collision_reports_unresolved_partial_and_writes_recovery(tmp_path, monkeypatch):
    session = make_session(tmp_path, ("srt",))
    session.set_segment_text(0, "recover partial")
    destination = tmp_path / "partial.qcp"
    export = tmp_path / "partial.en.srt"
    export.write_text("collision", encoding="utf-8")
    real_unlink = Path.unlink

    def deny_project_rollback(path, *args, **kwargs):
        if path == destination:
            raise PermissionError("project is locked")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_project_rollback)

    with pytest.raises(FileExistsError) as caught:
        session.save_as(destination)

    assert [failure.path for failure in caught.value.rollback_failures] == [destination]
    assert session.recovery_project().tracks[0].segments[0].text == "recover partial"


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
    assert session.recovery_project().tracks[0].segments[0].text == "recoverable edit"
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
    assert session.recovery_project().tracks[0].segments[0].text == "recover after render failure"


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


def test_stale_or_equal_recovery_does_not_prompt_or_replace_newer_durable_project(tmp_path):
    session = make_session(tmp_path, ("srt",))
    session.set_segment_text(0, "stale recovery")
    session.write_recovery()
    durable = ProjectStore(session.project_path).load()
    durable_track = replace(durable.tracks[0], segments=[replace(durable.tracks[0].segments[0], text="new durable")])
    ProjectStore(session.project_path).save(replace(durable, tracks=[durable_track]))
    timestamp = session.project_path.stat().st_mtime_ns
    os.utime(session.recovery_path, ns=(timestamp, timestamp))
    decisions = []

    opened = EditorSession.open(session.project_path, 0, list(session.export_paths.values()), lambda _: decisions.append(True) or "recover")

    assert decisions == []
    assert opened.track.segments[0].text == "new durable"
    assert not opened.dirty


def test_fresh_recovery_prompts_and_can_be_recovered(tmp_path):
    session = make_session(tmp_path, ("srt",))
    session.set_segment_text(0, "fresh recovery")
    session.write_recovery()
    durable_time = session.project_path.stat().st_mtime_ns
    os.utime(session.recovery_path, ns=(durable_time + 1_000_000_000, durable_time + 1_000_000_000))
    decisions = []

    opened = EditorSession.open(session.project_path, 0, list(session.export_paths.values()), lambda _: decisions.append(True) or "recover")

    assert decisions == [True]
    assert opened.track.segments[0].text == "fresh recovery"
    assert opened.dirty


def test_recovery_unlink_failure_is_a_committed_save_warning(tmp_path, monkeypatch):
    session = make_session(tmp_path, ("srt",))
    session.set_segment_text(0, "committed edit")
    session.write_recovery()
    real_unlink = Path.unlink

    def deny_recovery_unlink(path, *args, **kwargs):
        if path == session.recovery_path:
            raise PermissionError("Windows file lock")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_recovery_unlink)

    session.save()

    assert not session.dirty
    assert ProjectStore(session.project_path).load().tracks[0].segments[0].text == "committed edit"
    assert "Windows file lock" in session.last_warning
    decisions = []
    reopened = EditorSession.open(session.project_path, 0, list(session.export_paths.values()), lambda _: decisions.append(True) or "recover")
    assert decisions == []
    assert reopened.track.segments[0].text == "committed edit"


def test_save_as_updates_path_after_commit_when_old_recovery_cannot_be_removed(tmp_path, monkeypatch):
    session = make_session(tmp_path, ("srt",))
    session.set_segment_text(0, "committed save as")
    session.write_recovery()
    old_recovery = session.recovery_path
    destination = tmp_path / "new-name.qcp"
    real_unlink = Path.unlink

    def deny_old_recovery_unlink(path, *args, **kwargs):
        if path == old_recovery:
            raise PermissionError("Windows file lock")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_old_recovery_unlink)

    session.save_as(destination)

    assert session.project_path == destination
    assert not session.dirty
    assert ProjectStore(destination).load().tracks[0].segments[0].text == "committed save as"
    assert "Windows file lock" in session.last_warning


def test_recovery_base_fingerprint_prevents_edit_a_after_newer_edit_b_commit(tmp_path, monkeypatch):
    session = make_session(tmp_path, ("srt",))
    session.set_segment_text(0, "edit A")
    session.write_recovery()
    recovery_path = session.recovery_path
    envelope = json.loads(recovery_path.read_text(encoding="utf-8"))
    assert envelope["base_fingerprint"]
    assert envelope["project"]["tracks"][0]["segments"][0]["text"] == "edit A"

    session.set_segment_text(0, "edit B")
    real_unlink = Path.unlink

    def deny_recovery_cleanup(path, *args, **kwargs):
        if path == recovery_path:
            raise PermissionError("recovery is locked")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_recovery_cleanup)
    session.save()
    decisions = []

    reopened = EditorSession.open(
        session.project_path,
        0,
        list(session.export_paths.values()),
        lambda _: decisions.append(True) or "recover",
    )

    assert decisions == []
    assert reopened.track.segments[0].text == "edit B"
    assert "stale recovery" in reopened.last_warning.lower()


def test_stale_recovery_cleanup_failure_loads_durable_with_warning(tmp_path, monkeypatch):
    session = make_session(tmp_path, ("srt",))
    session.set_segment_text(0, "old recovery")
    session.write_recovery()
    durable = ProjectStore(session.project_path).load()
    newer_track = replace(durable.tracks[0], segments=[replace(durable.tracks[0].segments[0], text="new durable")])
    ProjectStore(session.project_path).save(replace(durable, tracks=[newer_track]))
    recovery_path = session.recovery_path
    real_unlink = Path.unlink

    def deny_stale_cleanup(path, *args, **kwargs):
        if path == recovery_path:
            raise PermissionError("stale snapshot is locked")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_stale_cleanup)

    opened = EditorSession.open(session.project_path, 0, list(session.export_paths.values()), lambda _: pytest.fail("must not prompt"))

    assert opened.track.segments[0].text == "new durable"
    assert "stale snapshot is locked" in opened.last_warning


def test_primary_save_error_survives_recovery_write_failure(tmp_path, monkeypatch):
    session = make_session(tmp_path, ("srt",))
    session.set_segment_text(0, "unsaved")
    primary = OSError("publish failed")
    recovery = OSError("recovery failed")
    monkeypatch.setattr(session_module, "publish_text_batch", lambda *args, **kwargs: (_ for _ in ()).throw(primary))
    monkeypatch.setattr(session, "write_recovery", lambda: (_ for _ in ()).throw(recovery))

    with pytest.raises(OSError, match="publish failed") as caught:
        session.save()

    assert caught.value is primary
    assert caught.value.recovery_error is recovery


def test_successful_save_removes_recovery(tmp_path):
    session = make_session(tmp_path, ("srt",))
    session.set_segment_text(0, "edited")
    session.write_recovery()
    assert session.recovery_path.exists()

    session.save()

    assert not session.recovery_path.exists()


@pytest.mark.parametrize("external_change", ["modified", "deleted"])
def test_save_refuses_external_project_change_and_preserves_dirty_recovery(tmp_path, external_change):
    session = make_session(tmp_path, ("srt",))
    session.set_segment_text(0, "my unsaved edit")
    if external_change == "modified":
        session.project_path.write_text("external durable edit", encoding="utf-8")
    else:
        session.project_path.unlink()

    with pytest.raises(SaveConflictError) as caught:
        session.save()

    assert caught.value.project_path == session.project_path
    assert session.dirty
    assert session.recovery_project().tracks[0].segments[0].text == "my unsaved edit"
    if external_change == "modified":
        assert session.project_path.read_text(encoding="utf-8") == "external durable edit"
    else:
        assert not session.project_path.exists()


@pytest.mark.parametrize("recovery_content", ["{not json", '{"recovery_version": 1, "project": {}}'])
def test_corrupt_recovery_does_not_block_valid_durable_project(tmp_path, recovery_content):
    session = make_session(tmp_path, ("srt",))
    session.recovery_path.write_text(recovery_content, encoding="utf-8")

    opened = EditorSession.open(
        session.project_path, 0, list(session.export_paths.values()), lambda _: pytest.fail("must not prompt")
    )

    assert opened.track.segments[0].text == "old"
    assert opened.recovery_path.exists()
    assert "corrupt recovery" in opened.last_warning.lower()
