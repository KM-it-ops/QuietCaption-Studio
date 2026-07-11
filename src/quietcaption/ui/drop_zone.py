from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout


class DropZone(QFrame):
    filesDropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self); layout.setAlignment(Qt.AlignCenter); layout.setSpacing(8)
        title = QLabel("Drop video or audio here"); title.setStyleSheet("font-size: 20px; font-weight: 600")
        subtitle = QLabel("or choose files from your computer"); subtitle.setObjectName("muted")
        self.browse = QPushButton("Browse files")
        for widget in (title, subtitle, self.browse):
            widget.setAlignment(Qt.AlignCenter) if isinstance(widget, QLabel) else None
            layout.addWidget(widget, 0, Qt.AlignCenter)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self.setProperty("dragActive", True); self.style().polish(self); event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.setProperty("dragActive", False); self.style().polish(self)

    def dropEvent(self, event):
        self.setProperty("dragActive", False); self.style().polish(self)
        self.filesDropped.emit([Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()])
        event.acceptProposedAction()

