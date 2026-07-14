from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..editor_session import EditorSession, SUPPORTED_FORMATS
from ..formats import format_timestamp


class SubtitleEditor(QWidget):
    dirtyChanged = Signal(bool)

    def __init__(
        self,
        session: EditorSession,
        parent=None,
        save_path_chooser=None,
        error_handler=None,
        warning_handler=None,
    ):
        super().__init__(parent)
        self.session = session
        self._save_path_chooser = save_path_chooser or self._choose_save_path
        self._error_handler = error_handler or self._show_error
        self._warning_handler = warning_handler or self._show_warning
        self._last_dirty = session.dirty

        layout = QVBoxLayout(self)
        toolbar = QToolBar("Editor actions")
        toolbar.setAccessibleName("Subtitle editor actions")
        self.save_action = QAction("Save", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.setToolTip("Save project and selected subtitle outputs")
        self.save_action.triggered.connect(lambda: self.save())
        self.save_as_action = QAction("Save As…", self)
        self.save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.save_as_action.setToolTip("Save to a new project without replacing existing files")
        self.save_as_action.triggered.connect(lambda: self.save_as())
        toolbar.addAction(self.save_action)
        toolbar.addAction(self.save_as_action)
        layout.addWidget(toolbar)

        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Regenerate outputs:"))
        self.format_checks = {}
        for extension in SUPPORTED_FORMATS:
            check = QCheckBox(extension.upper())
            check.setAccessibleName(f"Regenerate {extension.upper()} output")
            check.setChecked(extension in session.selected_formats)
            check.toggled.connect(lambda checked, value=extension: self._select_format(value, checked))
            self.format_checks[extension] = check
            output_row.addWidget(check)
        output_row.addStretch()
        self.dirty_label = QLabel()
        self.dirty_label.setAccessibleName("Save status")
        output_row.addWidget(self.dirty_label)
        layout.addLayout(output_row)

        track = session.track
        self.table = QTableWidget(len(track.segments), 3)
        self.table.setHorizontalHeaderLabels(["Start", "End", "Text"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        for row, segment in enumerate(track.segments):
            for column, value in enumerate((format_timestamp(segment.start), format_timestamp(segment.end))):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, column, item)
            self.table.setItem(row, 2, QTableWidgetItem(segment.text))
        self.table.itemChanged.connect(self._changed)
        layout.addWidget(self.table)

        self._recovery_timer = QTimer(self)
        self._recovery_timer.setSingleShot(True)
        self._recovery_timer.setInterval(500)
        self._recovery_timer.timeout.connect(self._autosave_recovery)
        self._update_dirty_status()

    @property
    def track(self):
        return self.session.track

    def is_dirty(self) -> bool:
        return self.session.dirty

    def _changed(self, item) -> None:
        if item.column() != 2:
            return
        self.session.set_segment_text(item.row(), item.text())
        self._recovery_timer.start()
        self._update_dirty_status()

    def _select_format(self, extension: str, selected: bool) -> None:
        if selected:
            self.session.selected_formats.add(extension)
        else:
            self.session.selected_formats.discard(extension)

    def _update_dirty_status(self) -> None:
        dirty = self.session.dirty
        self.dirty_label.setText("Unsaved changes" if dirty else "Saved")
        if dirty != self._last_dirty:
            self._last_dirty = dirty
            self.dirtyChanged.emit(dirty)

    def save(self) -> bool:
        try:
            self.session.save()
        except Exception as exc:
            self._report_save_failure("Save failed", exc)
            self._update_dirty_status()
            return False
        self._recovery_timer.stop()
        self._update_dirty_status()
        self._report_committed_warning()
        return True

    def save_as(self) -> bool:
        destination = self._save_path_chooser(self.session.project_path)
        if not destination:
            return False
        try:
            self.session.save_as(Path(destination))
        except Exception as exc:
            self._report_save_failure("Save As failed", exc)
            self._update_dirty_status()
            return False
        self._recovery_timer.stop()
        self._update_dirty_status()
        self._report_committed_warning()
        return True

    def stop_recovery_timer(self) -> None:
        self._recovery_timer.stop()

    def resume_recovery_timer(self) -> None:
        if self.session.dirty:
            self._recovery_timer.start()

    def _report_save_failure(self, title: str, exc: Exception) -> None:
        recovery_error = getattr(exc, "recovery_error", None)
        if recovery_error is None:
            detail = f"Your edits were written to the local recovery snapshot. {exc}"
        else:
            detail = f"{exc}. Recovery could not be written: {recovery_error}. Keep this editor open."
        self._error_handler(title, detail)

    def _report_committed_warning(self) -> None:
        if self.session.last_warning:
            self._warning_handler("Save completed with warning", self.session.last_warning)

    def _autosave_recovery(self) -> None:
        if not self.session.dirty:
            return
        try:
            self.session.write_recovery()
        except Exception as exc:
            self._error_handler("Recovery save failed", f"Keep this editor open and free local disk space. {exc}")

    def _choose_save_path(self, current: Path) -> str | None:
        path, _ = QFileDialog.getSaveFileName(self, "Save QuietCaption project as", str(current), "QuietCaption project (*.qcp)")
        return path or None

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)

    def _show_warning(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)
