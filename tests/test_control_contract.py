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


def test_beam_control_preserves_its_value_across_interface_modes(qtbot):
    window = MainWindow(demo=True); qtbot.addWidget(window)
    beam = window.new_job.beam_size

    assert (beam.minimum(), beam.maximum(), beam.value()) == (1, 20, 5)
    beam.setValue(11)
    window.new_job.set_interface_mode("everyday")
    window.new_job.set_interface_mode("technical")

    assert beam.value() == 11
