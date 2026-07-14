from PySide6.QtCore import SIGNAL
from PySide6.QtWidgets import QAbstractButton, QPushButton

from quietcaption.ui.main_window import MainWindow


def test_every_enabled_button_has_connected_behavior(qtbot):
    window = MainWindow(demo=True); qtbot.addWidget(window)
    disconnected = []
    for button in window.findChildren(QPushButton):
        if button.isEnabled() and button.text().strip() and button.receivers(SIGNAL("clicked()")) == 0:
            disconnected.append(button.text())
    assert disconnected == []


def test_primary_controls_have_accessible_names(qtbot):
    window = MainWindow(demo=True); qtbot.addWidget(window)
    missing = [button.text() for button in window.findChildren(QAbstractButton) if button.isVisibleTo(window) and not (button.accessibleName() or button.text()).strip()]
    assert missing == []
