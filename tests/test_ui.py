from pathlib import Path

from PySide6.QtCore import QMimeData, QUrl, Qt
from PySide6.QtGui import QDropEvent

from quietcaption.ui.main_window import MainWindow
from quietcaption.settings import AppSettings, SettingsStore


def test_main_window_has_approved_navigation_and_offline_status(qtbot):
    window = MainWindow(demo=True)
    qtbot.addWidget(window)
    assert window.windowTitle() == "QuietCaption Studio"
    assert [window.navigation.item(i).text() for i in range(window.navigation.count())] == ["New job", "Queue", "Models", "Settings"]
    assert "Offline" in window.offline_badge.text()


def test_add_files_accepts_media_and_rejects_other_types(qtbot, tmp_path):
    video = tmp_path / "clip.mp4"; video.write_bytes(b"x")
    text = tmp_path / "notes.txt"; text.write_text("x")
    window = MainWindow(demo=True); qtbot.addWidget(window)
    window.new_job.add_files([video, text])
    assert window.new_job.files == [video]
    assert "clip.mp4" in window.new_job.file_list.item(0).text()


def test_subtitle_editor_updates_text(qtbot):
    from quietcaption.domain import SubtitleSegment, SubtitleTrack
    from quietcaption.ui.editor import SubtitleEditor
    track = SubtitleTrack("en", [SubtitleSegment("a", 0, 1, "old")])
    editor = SubtitleEditor(track); qtbot.addWidget(editor)
    editor.table.item(0, 2).setText("new")
    assert editor.track.segments[0].text == "new"


def test_demo_job_runs_in_background_and_opens_editor(qtbot, tmp_path):
    video = tmp_path / "clip.mp4"; video.write_bytes(b"x")
    window = MainWindow(demo=True, output_directory=tmp_path / "out"); qtbot.addWidget(window)
    window.new_job.add_files([video])
    qtbot.mouseClick(window.new_job.generate, Qt.LeftButton)
    qtbot.waitUntil(lambda: (tmp_path / "out" / "clip.qcp").exists(), timeout=5000)
    qtbot.waitUntil(lambda: window.pages.currentWidget().objectName() == "editor", timeout=5000)


def test_demo_job_uses_saved_output_directory(qtbot, tmp_path):
    video = tmp_path / "clip.mp4"; video.write_bytes(b"x")
    output = tmp_path / "saved-output"
    store = SettingsStore(tmp_path / "settings.json")
    store.save(AppSettings(output_directory=str(output)))
    window = MainWindow(demo=True, settings_store=store); qtbot.addWidget(window)
    window.new_job.add_files([video])

    qtbot.mouseClick(window.new_job.generate, Qt.LeftButton)

    qtbot.waitUntil(lambda: (output / "clip.qcp").exists(), timeout=5000)


def test_multiple_dropped_files_run_through_the_queue(qtbot, tmp_path):
    first = tmp_path / "first.mp4"; first.write_bytes(b"a")
    second = tmp_path / "second.mp4"; second.write_bytes(b"b")
    output = tmp_path / "output"
    window = MainWindow(demo=True, output_directory=output); qtbot.addWidget(window)
    window.new_job.add_files([first, second])

    qtbot.mouseClick(window.new_job.generate, Qt.LeftButton)

    qtbot.waitUntil(
        lambda: (output / "first.qcp").exists()
        and (output / "second.qcp").exists()
        and "2 jobs completed" in window.queue_status.text(),
        timeout=5000,
    )


def test_queue_cancel_control_marks_current_job_for_cancellation(qtbot):
    window = MainWindow(demo=True); qtbot.addWidget(window)
    window._cancel_token = type("Token", (), {"cancelled": False})()
    window.cancel_button.setEnabled(True)

    qtbot.mouseClick(window.cancel_button, Qt.LeftButton)

    assert window._cancel_token.cancelled
    assert "Cancelling" in window.queue_status.text()
