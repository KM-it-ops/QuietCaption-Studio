from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget

from ..setup import FindingStatus, RecommendationEngine, SetupScanner


class SetupPanel(QWidget):
    automatedRequested = Signal(object)
    customRequested = Signal(object)

    def __init__(self, scanner=None, parent=None):
        super().__init__(parent)
        self.scan = (scanner or SetupScanner()).scan()
        self.plan = RecommendationEngine().recommend(self.scan)
        layout = QVBoxLayout(self)
        heading = QLabel("Hardware findings"); heading.setStyleSheet("font-size: 18px; font-weight: 600")
        self.findings_list = QListWidget(); self.findings_list.setAccessibleName("Hardware findings")
        self.findings_list.setWordWrap(True); self.findings_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.findings_list.setMinimumHeight(235); self.findings_list.setMaximumHeight(245)
        symbols = {FindingStatus.READY: "Ready", FindingStatus.ACTION: "Action", FindingStatus.BLOCKING: "Blocking"}
        for finding in self.scan.findings:
            self.findings_list.addItem(QListWidgetItem(f"{symbols[finding.status]} · {finding.summary}\n{finding.detail}"))
        recommendation = QLabel(f"Recommended: {self.plan.transcription_model} + {self.plan.translation_model} · {self.plan.download_gb:g} GB download")
        recommendation.setWordWrap(True)
        actions = QHBoxLayout(); self.automated_button = QPushButton("Automated setup"); self.automated_button.setObjectName("primary")
        self.custom_button = QPushButton("Custom setup")
        self.automated_button.clicked.connect(lambda: self.automatedRequested.emit(self.plan))
        self.custom_button.clicked.connect(lambda: self.customRequested.emit(self.scan))
        actions.addWidget(self.automated_button); actions.addWidget(self.custom_button); actions.addStretch()
        layout.addWidget(heading); layout.addWidget(self.findings_list); layout.addWidget(recommendation); layout.addLayout(actions)
