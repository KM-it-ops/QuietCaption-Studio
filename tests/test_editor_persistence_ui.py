from pathlib import Path

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


def test_dirty_edit_is_debounced_to_a_recovery_snapshot(qtbot, tmp_path):
    session = session_at(tmp_path)
    editor = SubtitleEditor(session)
    qtbot.addWidget(editor)

    editor.table.item(0, 2).setText("autosaved edit")

    qtbot.waitUntil(session.recovery_path.exists, timeout=2000)
    recovered = ProjectStore(session.recovery_path).load()
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
