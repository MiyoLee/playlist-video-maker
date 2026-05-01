from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from playlist_video_maker.ui.main_window import MainWindow


def run() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
