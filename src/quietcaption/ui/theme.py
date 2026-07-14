DARK_STYLESHEET = """
QMainWindow, QWidget { background: #111827; color: #e5e7eb; font-size: 14px; }
QFrame#sidebar { background: #0b1220; border-right: 1px solid #263246; }
QListWidget#navigation { background: transparent; border: 0; outline: 0; }
QListWidget#navigation::item { padding: 13px 14px; margin: 3px 7px; border-radius: 7px; }
QListWidget#navigation::item:selected { background: #6d5dfc; color: white; }
QFrame#dropZone { border: 2px dashed #4b5870; border-radius: 13px; background: #151f31; }
QFrame#dropZone[dragActive="true"] { border-color: #8b7fff; background: #1b2540; }
QPushButton { background: #263246; border: 1px solid #3a4963; border-radius: 7px; padding: 9px 14px; }
QPushButton:hover { background: #33425b; }
QPushButton:checked { background: #5145cd; border-color: #8b7fff; color: white; }
QPushButton:disabled { background: #1b2536; color: #6f7e93; border-color: #2a3548; }
QPushButton:focus, QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QListWidget:focus { border: 2px solid #a99fff; }
QPushButton#primary { background: #6d5dfc; border: 0; color: white; font-weight: 600; padding: 11px 18px; }
QLineEdit, QComboBox, QSpinBox, QTableWidget { background: #0e1728; border: 1px solid #34425a; border-radius: 6px; padding: 7px; }
QLabel#muted { color: #9aa8bd; }
QLabel#badge { background: #173c34; color: #a7f3d0; border-radius: 8px; padding: 5px 9px; }
QProgressBar { border: 1px solid #34425a; border-radius: 5px; text-align: center; }
QProgressBar::chunk { background: #6d5dfc; border-radius: 4px; }
"""

LIGHT_STYLESHEET = """
QMainWindow, QWidget { background: #f4f7fb; color: #182235; font-size: 14px; }
QFrame#sidebar { background: #e8edf5; border-right: 1px solid #c8d2e1; }
QListWidget#navigation { background: transparent; border: 0; outline: 0; }
QListWidget#navigation::item { padding: 13px 14px; margin: 3px 7px; border-radius: 7px; }
QListWidget#navigation::item:selected { background: #5b4ee8; color: white; }
QFrame#dropZone { border: 2px dashed #8795aa; border-radius: 13px; background: #ffffff; }
QFrame#dropZone[dragActive="true"] { border-color: #6658ee; background: #f0efff; }
QPushButton { background: #ffffff; border: 1px solid #b8c4d5; border-radius: 7px; padding: 9px 14px; }
QPushButton:hover { background: #e9eef6; }
QPushButton:checked { background: #5b4ee8; border-color: #5b4ee8; color: white; }
QPushButton:disabled { background: #e8edf4; color: #8795a8; border-color: #d3dbe7; }
QPushButton:focus, QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QListWidget:focus { border: 2px solid #5b4ee8; }
QPushButton#primary { background: #5b4ee8; border: 0; color: white; font-weight: 600; padding: 11px 18px; }
QLineEdit, QComboBox, QSpinBox, QTableWidget, QTabWidget::pane { background: #ffffff; border: 1px solid #bdc8d8; border-radius: 6px; padding: 7px; }
QLabel#muted { color: #5f6f84; }
QLabel#badge { background: #d9f5ea; color: #11614d; border-radius: 8px; padding: 5px 9px; }
QProgressBar { border: 1px solid #aebbd0; border-radius: 5px; text-align: center; }
QProgressBar::chunk { background: #5b4ee8; border-radius: 4px; }
"""

STYLESHEET = DARK_STYLESHEET


def stylesheet_for(theme: str) -> str:
    if theme == "light":
        return LIGHT_STYLESHEET
    if theme == "system":
        try:
            from PySide6.QtGui import QPalette
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app and app.palette().color(QPalette.Window).lightness() >= 128:
                return LIGHT_STYLESHEET
        except Exception:
            pass
    return DARK_STYLESHEET
