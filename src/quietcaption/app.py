from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow
from .ui.theme import STYLESHEET


def create_application(argv=None, demo=False):
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName("QuietCaption Studio"); app.setOrganizationName("QuietCaption")
    app.setStyle("Fusion"); app.setStyleSheet(STYLESHEET)
    window = MainWindow(demo=demo)
    return app, window


def main(argv=None):
    parser = argparse.ArgumentParser(description="Private offline subtitle studio")
    parser.add_argument("--demo", action="store_true", help="Use deterministic offline demo adapters")
    args = parser.parse_args(argv)
    app, window = create_application(demo=args.demo); window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

