from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from quietcaption.domain import Project, SubtitleSegment, SubtitleTrack
from quietcaption.editor_session import EditorSession
from quietcaption.pipeline import PipelineResult
from quietcaption.projects import ProjectStore
from quietcaption.ui.editor import SubtitleEditor
from quietcaption.ui.main_window import MainWindow


def session_at(tmp_path: Path) -> EditorSession:
    project = Project("id", "clip.mp4", [SubtitleTrack("en", [SubtitleSegment("a", 0, 1, "old")])])
    path = tmp_path / "clip.qcp"
    ProjectStore(path).save(project)
    return EditorSession(project, path, 0, [tmp_path / "clip.en.srt"])


def test_editor_actions_are_accessible_connected_and_dirty_is_observable(qtbot, tmp_path):
    session = session_at(tmp_path)
    editor = SubtitleEditor(session)
    qtbot.addWidget(editor)
    dirty_changes = []
    editor.dirtyChanged.connect(dirty_changes.append)

    assert editor.save_action.text() == "Save"
    assert editor.save_action.shortcut().toString()
    assert editor.save_as_action.text() == "Save As…"
    assert not editor.table.item(0, 0).flags() & Qt.ItemIsEditable
    assert not editor.table.item(0, 1).flags() & Qt.ItemIsEditable

    editor.table.item(0, 2).setText("edited")
    assert editor.is_dirty()
    assert dirty_changes[-1] is True
    editor.save_action.trigger()
    assert not editor.is_dirty()
    assert dirty_changes[-1] is False


def test_save_as_cancellation_changes_nothing(qtbot, tmp_path):
    session = session_at(tmp_path)
    editor = SubtitleEditor(session, save_path_chooser=lambda _: None)
    qtbot.addWidget(editor)
    editor.table.item(0, 2).setText("edited")

    editor.save_as_action.trigger()

    assert session.project_path == tmp_path / "clip.qcp"
    assert editor.is_dirty()


def test_format_controls_toggle_all_supported_outputs_and_save_them(qtbot, tmp_path):
    session = session_at(tmp_path)
    editor = SubtitleEditor(session)
    qtbot.addWidget(editor)
    editor.table.item(0, 2).setText("all formats")

    for extension in ("srt", "vtt", "txt"):
        check = editor.format_checks[extension]
        check.setChecked(False)
        assert extension not in session.selected_formats
        check.setChecked(True)
        assert extension in session.selected_formats
        assert check.accessibleName()

    editor.save_action.trigger()

    for extension in ("srt", "vtt", "txt"):
        assert "all formats" in (tmp_path / f"clip.en.{extension}").read_text(encoding="utf-8")


def test_successful_save_as_action_uses_chosen_path_and_surfaces_warning_separately(qtbot, tmp_path):
    session = session_at(tmp_path)
    destination = tmp_path / "chosen.qcp"
    warnings = []
    editor = SubtitleEditor(
        session,
        save_path_chooser=lambda _: destination,
        warning_handler=lambda title, message: warnings.append((title, message)),
    )
    qtbot.addWidget(editor)
    editor.table.item(0, 2).setText("chosen edit")

    editor.save_as_action.trigger()

    assert session.project_path == destination
    assert ProjectStore(destination).load().tracks[0].segments[0].text == "chosen edit"
    assert not editor.is_dirty()
    assert warnings == []


def test_committed_save_with_recovery_cleanup_failure_surfaces_warning(qtbot, tmp_path, monkeypatch):
    session = session_at(tmp_path)
    editor_warnings = []
    editor = SubtitleEditor(session, warning_handler=lambda title, message: editor_warnings.append((title, message)))
    qtbot.addWidget(editor)
    editor.table.item(0, 2).setText("committed")
    session.write_recovery()
    recovery_path = session.recovery_path
    real_unlink = Path.unlink

    def deny_recovery_unlink(path, *args, **kwargs):
        if path == recovery_path:
            raise PermissionError("Windows file lock")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_recovery_unlink)

    assert editor.save()

    assert not editor.is_dirty()
    assert editor_warnings and "Save committed" in editor_warnings[0][1]


def test_dirty_edit_is_debounced_to_a_recovery_snapshot(qtbot, tmp_path):
    session = session_at(tmp_path)
    editor = SubtitleEditor(session)
    qtbot.addWidget(editor)

    editor.table.item(0, 2).setText("autosaved edit")

    qtbot.waitUntil(session.recovery_path.exists, timeout=2000)
    recovered = session.recovery_project()
    assert recovered.tracks[0].segments[0].text == "autosaved edit"


def test_main_window_passes_pipeline_project_and_exports_to_editor(qtbot, tmp_path):
    session = session_at(tmp_path)
    result = PipelineResult(session.project_path, list(session.export_paths.values()))
    window = MainWindow(demo=True)
    qtbot.addWidget(window)
    window._last_result = result
    window._completed_jobs = 1

    window._finish_queue()

    editor = window.pages.currentWidget()
    assert isinstance(editor, SubtitleEditor)
    assert editor.session.project.id == "id"
    assert editor.session.project_path == session.project_path
    assert editor.session.export_paths == session.export_paths


def test_clean_close_does_not_prompt_and_dirty_cancel_keeps_window_open(qtbot, tmp_path):
    session = session_at(tmp_path)
    editor = SubtitleEditor(session)
    window = MainWindow(demo=True)
    qtbot.addWidget(window)
    window._editors = [editor]
    prompts = []
    window._close_choice = lambda _: prompts.append(True) or QMessageBox.Cancel

    assert window.request_close()
    assert prompts == []

    editor.table.item(0, 2).setText("edited")
    assert not window.request_close()
    assert prompts == [True]
    assert editor.is_dirty()
    window._close_choice = lambda _: QMessageBox.Discard
    window.close()


def test_dirty_close_save_only_closes_on_success_and_discard_removes_recovery(qtbot, tmp_path, monkeypatch):
    session = session_at(tmp_path)
    editor = SubtitleEditor(session, error_handler=lambda *_: None)
    window = MainWindow(demo=True)
    qtbot.addWidget(window)
    window._editors = [editor]
    editor.table.item(0, 2).setText("edited")
    session.write_recovery()
    window._close_choice = lambda _: QMessageBox.Save
    monkeypatch.setattr(session, "save", lambda: (_ for _ in ()).throw(OSError("read only")))
    assert not window.request_close()
    assert editor.is_dirty()

    window._close_choice = lambda _: QMessageBox.Discard
    assert window.request_close()
    assert not session.recovery_path.exists()


def test_multi_editor_cancel_is_two_phase_and_preserves_all_state(qtbot, tmp_path):
    first_session = session_at(tmp_path / "first")
    second_session = session_at(tmp_path / "second")
    first = SubtitleEditor(first_session)
    second = SubtitleEditor(second_session)
    window = MainWindow(demo=True)
    qtbot.addWidget(window)
    first.table.item(0, 2).setText("first edit")
    second.table.item(0, 2).setText("second edit")
    first_session.write_recovery()
    second_session.write_recovery()
    window._editors = [first, second]
    choices = iter((QMessageBox.Save, QMessageBox.Cancel))
    window._close_choice = lambda _: next(choices)

    assert not window.request_close()

    assert first_session.dirty and second_session.dirty
    assert first_session.recovery_path.exists() and second_session.recovery_path.exists()
    assert first._recovery_timer.isActive() and second._recovery_timer.isActive()
    window._close_choice = lambda _: QMessageBox.Discard
    window.close()


def test_discard_waits_for_later_save_and_is_preserved_when_save_fails(qtbot, tmp_path, monkeypatch):
    discard_session = session_at(tmp_path / "discard")
    save_session = session_at(tmp_path / "save")
    discard_editor = SubtitleEditor(discard_session)
    save_editor = SubtitleEditor(save_session, error_handler=lambda *_: None)
    window = MainWindow(demo=True)
    qtbot.addWidget(window)
    discard_editor.table.item(0, 2).setText("keep if close fails")
    save_editor.table.item(0, 2).setText("save fails")
    discard_session.write_recovery()
    save_session.write_recovery()
    window._editors = [discard_editor, save_editor]
    choices = iter((QMessageBox.Discard, QMessageBox.Save))
    window._close_choice = lambda _: next(choices)
    monkeypatch.setattr(save_session, "save", lambda: (_ for _ in ()).throw(OSError("read only")))

    assert not window.request_close()
    window._close_choice = lambda _: QMessageBox.Discard

    assert discard_session.recovery_path.exists()
    assert discard_session.recovery_project().tracks[0].segments[0].text == "keep if close fails"
    assert discard_editor._recovery_timer.isActive()
    window.close()


def test_close_event_accepts_clean_and_ignores_cancelled_dirty_close(qtbot, tmp_path):
    class Event:
        def __init__(self):
            self.accepted = None

        def accept(self):
            self.accepted = True

        def ignore(self):
            self.accepted = False

    window = MainWindow(demo=True)
    qtbot.addWidget(window)
    clean_event = Event()
    window.closeEvent(clean_event)
    assert clean_event.accepted is True

    session = session_at(tmp_path)
    editor = SubtitleEditor(session)
    editor.table.item(0, 2).setText("dirty")
    window._editors = [editor]
    window._close_choice = lambda _: QMessageBox.Cancel
    dirty_event = Event()
    window.closeEvent(dirty_event)
    assert dirty_event.accepted is False
    assert editor.is_dirty()
    window._close_choice = lambda _: QMessageBox.Discard
    accepted_dirty_event = Event()
    window.closeEvent(accepted_dirty_event)
    assert accepted_dirty_event.accepted is True
    assert not editor._recovery_timer.isActive()


def test_save_error_reports_when_recovery_could_not_be_written(qtbot, tmp_path, monkeypatch):
    session = session_at(tmp_path)
    errors = []
    editor = SubtitleEditor(session, error_handler=lambda title, message: errors.append((title, message)))
    qtbot.addWidget(editor)
    editor.table.item(0, 2).setText("dirty")
    primary = OSError("publish failed")
    primary.recovery_error = OSError("recovery failed")
    monkeypatch.setattr(session, "save", lambda: (_ for _ in ()).throw(primary))

    assert not editor.save()

    assert "publish failed" in errors[0][1]
    assert "Recovery could not be written" in errors[0][1]
    assert "recovery failed" in errors[0][1]


def test_editor_surfaces_stale_recovery_cleanup_warning_on_open(qtbot, tmp_path, monkeypatch):
    session = session_at(tmp_path)
    session.set_segment_text(0, "stale")
    session.write_recovery()
    durable = ProjectStore(session.project_path).load()
    newer_track = replace(durable.tracks[0], segments=[replace(durable.tracks[0].segments[0], text="durable")])
    ProjectStore(session.project_path).save(replace(durable, tracks=[newer_track]))
    recovery_path = session.recovery_path
    real_unlink = Path.unlink

    def deny_cleanup(path, *args, **kwargs):
        if path == recovery_path:
            raise PermissionError("locked stale recovery")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_cleanup)
    opened = EditorSession.open(session.project_path, 0, list(session.export_paths.values()), lambda _: pytest.fail("must not prompt"))
    warnings = []

    editor = SubtitleEditor(opened, warning_handler=lambda title, message: warnings.append((title, message)))
    qtbot.addWidget(editor)

    assert warnings and warnings[0][0] == "Recovery warning"
    assert "locked stale recovery" in warnings[0][1]


def test_editor_surfaces_corrupt_recovery_warning_without_blocking_open(qtbot, tmp_path):
    session = session_at(tmp_path)
    session.recovery_path.write_text("not json", encoding="utf-8")
    opened = EditorSession.open(session.project_path, 0, list(session.export_paths.values()), lambda _: "recover")
    warnings = []

    editor = SubtitleEditor(opened, warning_handler=lambda title, message: warnings.append((title, message)))
    qtbot.addWidget(editor)

    assert opened.track.segments[0].text == "old"
    assert warnings and warnings[0][0] == "Recovery warning"
    assert "corrupt recovery" in warnings[0][1].lower()
