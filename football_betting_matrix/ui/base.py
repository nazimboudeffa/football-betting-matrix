"""Classe de base des pages + execution des taches en arriere-plan."""

from __future__ import annotations

import traceback
from collections.abc import Callable

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt6.QtWidgets import QMessageBox, QVBoxLayout, QWidget

from ..config import DISCLAIMER
from ..errors import SourceError
from ..service import DataService


class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str, str)
    progress = pyqtSignal(int, int, str)


class Worker(QRunnable):
    """Execute une fonction (telechargements + calculs) hors du thread graphique."""

    def __init__(self, fn: Callable[[Callable[[int, int, str], None]], object]):
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()
        self.setAutoDelete(False)

    def run(self) -> None:  # pragma: no cover - execute dans un thread Qt
        try:
            result = self.fn(self.signals.progress.emit)
        except SourceError as exc:
            self.signals.failed.emit(exc.code, exc.user_message())
        except Exception as exc:
            traceback.print_exc()
            self.signals.failed.emit("error", str(exc) or exc.__class__.__name__)
        else:
            self.signals.finished.emit(result)


class BasePage(QWidget):
    busy_changed = pyqtSignal(bool, str)
    toast = pyqtSignal(str)

    def __init__(self, service: DataService, parent=None):
        super().__init__(parent)
        self.service = service
        self._workers: set[Worker] = set()
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(24, 18, 24, 16)
        self.root.setSpacing(14)

    # ------------------------------------------------------------- taches

    def run_task(
        self,
        fn: Callable[[Callable[[int, int, str], None]], object],
        on_success: Callable[[object], None],
        on_error: Callable[[str, str], None] | None = None,
        progress: Callable[[int, int, str], None] | None = None,
        busy_text: str = "Chargement des donnees...",
    ) -> bool:
        worker = Worker(fn)
        self._workers.add(worker)
        self.busy_changed.emit(True, busy_text)
        if progress is not None:
            worker.signals.progress.connect(progress)

        def release() -> None:
            self._workers.discard(worker)
            if not self._workers:
                self.busy_changed.emit(False, "")

        def success(result: object) -> None:
            release()
            try:
                on_success(result)
            except Exception as exc:  # pragma: no cover - garde-fou UI
                traceback.print_exc()
                self.show_error("Erreur d'affichage", str(exc))

        def failure(code: str, message: str) -> None:
            release()
            if on_error is not None:
                on_error(code, message)
            else:
                self.show_source_error(code, message)

        worker.signals.finished.connect(success)
        worker.signals.failed.connect(failure)
        QThreadPool.globalInstance().start(worker)
        return True

    # ------------------------------------------------------------ messages

    def show_error(self, title: str, message: str, detail: str = "") -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(title)
        box.setText(message)
        if detail:
            box.setDetailedText(detail)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()

    def show_source_error(self, code: str, message: str) -> None:
        hints = {
            "rate_limit": (
                "La source gratuite est temporairement limitee. Patientez quelques "
                "instants avant de relancer la requete."
            ),
            "network": "Verifiez votre connexion Internet puis reessayez.",
            "source": (
                "La source gratuite n'a pas pu fournir ces donnees. Reessayez plus tard "
                "ou consultez les donnees deja en cache."
            ),
        }
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Betting Matrix")
        box.setText(message)
        hint = hints.get(code)
        if hint:
            box.setInformativeText(hint)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()

    def confirm(self, title: str, message: str) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(title)
        box.setText(message)
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QMessageBox.StandardButton.No)
        return box.exec() == QMessageBox.StandardButton.Yes

    def show_disclaimer(self) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Jeu responsable")
        box.setText("Analyse informative — aucun conseil de pari")
        box.setInformativeText(DISCLAIMER)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()

    # ------------------------------------------------------------ lifecycle

    def on_show(self) -> None:
        """Appelee a chaque affichage de la page."""

    def refresh(self) -> None:
        """Rechargement explicite (bouton Actualiser)."""

    def cleanup(self) -> None:
        """Libere les ressources eventuelles."""
