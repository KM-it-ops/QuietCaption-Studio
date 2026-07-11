from dataclasses import replace

from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from ..domain import SubtitleSegment, SubtitleTrack
from ..formats import format_timestamp


class SubtitleEditor(QWidget):
    def __init__(self, track: SubtitleTrack, parent=None):
        super().__init__(parent); self.track = track
        layout = QVBoxLayout(self); self.table = QTableWidget(len(track.segments), 3)
        self.table.setHorizontalHeaderLabels(["Start", "End", "Text"]); self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        for row, segment in enumerate(track.segments):
            self.table.setItem(row, 0, QTableWidgetItem(format_timestamp(segment.start)))
            self.table.setItem(row, 1, QTableWidgetItem(format_timestamp(segment.end)))
            self.table.setItem(row, 2, QTableWidgetItem(segment.text))
        self.table.itemChanged.connect(self._changed); layout.addWidget(self.table)

    def _changed(self, item):
        if item.column() != 2: return
        segments = list(self.track.segments); segments[item.row()] = replace(segments[item.row()], text=item.text())
        self.track = replace(self.track, segments=segments)

