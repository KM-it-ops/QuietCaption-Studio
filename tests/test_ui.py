from pathlib import Path

from PySide6.QtCore import QMimeData, QUrl, Qt
from PySide6.QtGui import QDropEvent

from quietcaption.ui.main_window import MainWindow


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
