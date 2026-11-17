"""Fenetre d'analyse IA : prompt, contexte complet et client Ollama local."""

from __future__ import annotations

import traceback
from collections.abc import Callable

from PyQt6.QtCore import QThreadPool
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
)

from .. import ai
from ..service import DataService
from ..theme import ACCENT, AMBER, MUTED, RED
from .base import Worker
from .widgets import Card


class AiAnalysisDialog(QDialog):
    """Boite de dialogue permettant d'envoyer l'analyse courante a Ollama."""

    def __init__(self, service: DataService, analysis: dict, parent=None):
        super().__init__(parent)
        self.service = service
        self.analysis = analysis or {}
        self._workers: set[Worker] = set()
        self._busy = False
        self._saved_model = self.service.ollama_model()

        fixture = self.analysis.get("fixture") or {}
        home = (fixture.get("home") or {}).get("name") or "Domicile"
        away = (fixture.get("away") or {}).get("name") or "Exterieur"
        self.setWindowTitle(f"Analyse IA • {home} - {away}")
        self.resize(940, 760)
        self.setMinimumSize(720, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        header = QLabel(f"{home} vs {away}")
        header.setStyleSheet(f"color: {ACCENT}; font-size: 15pt; font-weight: 700;")
        root.addWidget(header)

        root.addWidget(self._build_model_card())
        root.addWidget(self._build_tabs(), 1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("small")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.close_button = QPushButton("Fermer")
        self.close_button.clicked.connect(self.reject)
        actions.addWidget(self.close_button)
        actions.addStretch()
        self.analyze_button = QPushButton("Analyser avec l'IA")
        self.analyze_button.setObjectName("primary")
        self.analyze_button.clicked.connect(self.analyze)
        actions.addWidget(self.analyze_button)
        root.addLayout(actions)

        self._set_status(
            "Ollama doit etre lance avant l'analyse (ollama serve) avec au moins un modele "
            "installe (ollama pull <modele>).",
            MUTED,
        )
        self._load_models()

    # ------------------------------------------------------------------- UI

    def _build_model_card(self) -> Card:
        card = Card("Modele Ollama", "Choisissez le modele utilise pour cette analyse")
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("Modele"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(260)
        row.addWidget(self.model_combo, 1)

        self.refresh_button = QPushButton("Actualiser les modeles")
        self.refresh_button.clicked.connect(self._load_models)
        row.addWidget(self.refresh_button)
        card.add_layout(row)

        url = QLabel(f"Serveur : {self.service.ollama_url()}")
        url.setObjectName("small")
        card.add(url)
        return card

    def _build_tabs(self) -> QTabWidget:
        tabs = QTabWidget()

        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlainText(ai.DEFAULT_PROMPT)
        self.prompt_edit.setAcceptRichText(False)
        tabs.addTab(self.prompt_edit, "Prompt")

        self.context_edit = QTextEdit()
        self.context_edit.setPlainText(ai.build_context(self.analysis))
        self.context_edit.setReadOnly(True)
        self.context_edit.setObjectName("mono")
        tabs.addTab(self.context_edit, "Donnees")

        self.result_edit = QTextEdit()
        self.result_edit.setReadOnly(True)
        self.result_edit.setPlaceholderText("La reponse d'Ollama s'affichera ici.")
        self.result_edit.setObjectName("mono")
        self.tabs = tabs
        tabs.addTab(self.result_edit, "Reponse")
        return tabs

    # ------------------------------------------------------------- traitement

    def _set_status(self, message: str, color: str = MUTED) -> None:
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {color};")

    def _update_buttons(self) -> None:
        self.analyze_button.setEnabled(not self._busy and self.model_combo.count() > 0)
        self.refresh_button.setEnabled(not self._busy)
        self.model_combo.setEnabled(not self._busy)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self._busy = busy
        self._update_buttons()
        if busy:
            self._set_status(message or "Traitement en cours...", AMBER)

    def _run(
        self,
        fn: Callable[[Callable[[int, int, str], None]], object],
        on_success: Callable[[object], None],
        on_error: Callable[[str, str], None],
        busy_text: str,
    ) -> None:
        worker = Worker(fn)
        self._workers.add(worker)

        def release() -> None:
            self._workers.discard(worker)
            self._set_busy(False)

        def success(result: object) -> None:
            release()
            try:
                on_success(result)
            except Exception as exc:  # pragma: no cover - garde-fou UI
                traceback.print_exc()
                self._set_status(f"Erreur d'affichage : {exc}", RED)

        def failure(code: str, message: str) -> None:
            release()
            on_error(code, message)

        worker.signals.finished.connect(success)
        worker.signals.failed.connect(failure)
        self._set_busy(True, busy_text)
        QThreadPool.globalInstance().start(worker)

    # ---------------------------------------------------------------- actions

    def _load_models(self) -> None:
        def on_success(result: object) -> None:
            models = [str(name) for name in (result or [])]
            current = self.model_combo.currentText().strip() or self._saved_model
            self.model_combo.blockSignals(True)
            self.model_combo.clear()
            self.model_combo.addItems(models)
            index = self.model_combo.findText(current)
            self.model_combo.setCurrentIndex(index if index >= 0 else 0)
            self.model_combo.blockSignals(False)
            self._update_buttons()
            if models:
                self._set_status(
                    f"Ollama pret • {len(models)} modele(s) disponible(s).", ACCENT
                )
            else:
                self._set_status(
                    "Aucun modele installe : lancez 'ollama pull <modele>' puis Actualiser.",
                    AMBER,
                )

        def on_error(_code: str, message: str) -> None:
            self.model_combo.clear()
            self._update_buttons()
            self._set_status(message, RED)

        self._run(
            lambda _progress: ai.list_models(self.service.ollama_url()),
            on_success,
            on_error,
            "Recherche des modeles Ollama...",
        )

    def analyze(self) -> None:
        if self._busy:
            return
        prompt = self.prompt_edit.toPlainText().strip()
        if not prompt:
            self._set_status("Saisissez un prompt avant de lancer l'analyse.", AMBER)
            self.tabs.setCurrentWidget(self.prompt_edit)
            return
        model = self.model_combo.currentText().strip()
        if not model:
            self._set_status("Choisissez un modele Ollama dans la liste.", AMBER)
            return

        full_prompt = ai.build_prompt(prompt, self.context_edit.toPlainText())
        self.service.set_ollama_model(model)

        def on_success(result: object) -> None:
            self.result_edit.setPlainText(str(result))
            self.tabs.setCurrentWidget(self.result_edit)
            self._set_status(f"Reponse recue avec le modele « {model} ».", ACCENT)

        def on_error(_code: str, message: str) -> None:
            self._set_status(message, RED)

        self._run(
            lambda _progress: ai.ask_ollama(
                full_prompt, model, self.service.ollama_url()
            ),
            on_success,
            on_error,
            f"Analyse en cours avec « {model} »...",
        )
