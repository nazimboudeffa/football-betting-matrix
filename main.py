"""Point d'entree de Betting Matrix.

Lancement :
    python main.py
"""

from __future__ import annotations

import sys

from PyQt6.QtCore import QThreadPool, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication

from betting_matrix.config import APP_NAME, APP_VERSION, load_config
from betting_matrix.service import DataService
from betting_matrix.store import JsonSettingsStore, MemoryCache
from betting_matrix.theme import STYLESHEET
from betting_matrix.ui.main_window import MainWindow


def _app_icon() -> QIcon:
    """Construit une icone simple (damier + accent) sans fichier externe."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#0b121c"))
    painter.drawRoundedRect(2, 2, 60, 60, 14, 14)
    painter.setBrush(QColor("#28d17c"))
    painter.drawRoundedRect(10, 10, 20, 20, 5, 5)
    painter.drawRoundedRect(34, 34, 20, 20, 5, 5)
    painter.setBrush(QColor("#4c8dff"))
    painter.drawRoundedRect(34, 10, 20, 20, 5, 5)
    painter.setBrush(QColor("#1e2d42"))
    painter.drawRoundedRect(10, 34, 20, 20, 5, 5)
    painter.end()
    return QIcon(pixmap)


def _set_windows_app_id() -> None:
    """Regroupe correctement l'application dans la barre des taches Windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "BettingMatrix.Desktop.1"
        )
    except Exception:
        pass


def main() -> int:
    _set_windows_app_id()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("BettingMatrix")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLESHEET)
    app.setWindowIcon(_app_icon())

    config = load_config()
    cache = MemoryCache()
    settings = JsonSettingsStore(config.settings_path)
    service = DataService(config, cache, settings)

    window = MainWindow(service)
    window.show()

    try:
        return app.exec()
    finally:
        # Laisse aux workers le temps de terminer proprement avant la fermeture.
        QThreadPool.globalInstance().waitForDone(3000)


if __name__ == "__main__":
    raise SystemExit(main())
