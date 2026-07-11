STYLESHEET = """
QMainWindow, QWidget { background: #111827; color: #e5e7eb; font-size: 14px; }
QFrame#sidebar { background: #0b1220; border-right: 1px solid #263246; }
QListWidget#navigation { background: transparent; border: 0; outline: 0; }
QListWidget#navigation::item { padding: 13px 14px; margin: 3px 7px; border-radius: 7px; }
QListWidget#navigation::item:selected { background: #6d5dfc; color: white; }
QFrame#dropZone { border: 2px dashed #4b5870; border-radius: 13px; background: #151f31; }
QFrame#dropZone[dragActive="true"] { border-color: #8b7fff; background: #1b2540; }
QPushButton { background: #263246; border: 1px solid #3a4963; border-radius: 7px; padding: 9px 14px; }
QPushButton:hover { background: #33425b; }
QPushButton#primary { background: #6d5dfc; border: 0; color: white; font-weight: 600; padding: 11px 18px; }
QLineEdit, QComboBox, QSpinBox, QTableWidget { background: #0e1728; border: 1px solid #34425a; border-radius: 6px; padding: 7px; }
QLabel#muted { color: #9aa8bd; }
QLabel#badge { background: #173c34; color: #a7f3d0; border-radius: 8px; padding: 5px 9px; }
QProgressBar { border: 1px solid #34425a; border-radius: 5px; text-align: center; }
QProgressBar::chunk { background: #6d5dfc; border-radius: 4px; }
"""

