"""Page Reglages : preferences d'analyse, sources gratuites, cache memoire et prechargement."""

from __future__ import annotations

import json
from datetime import datetime

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ...config import APP_NAME, APP_VERSION, DISCLAIMER
from ...service import DataService
from ...theme import ACCENT, AMBER, MUTED, TEXT
from ..base import BasePage
from ..common import configure_table, populate_seasons
from ..widgets import Badge, Banner, Card, table_item


def _human_size(size: int) -> str:
    if size < 1024:
        return f"{size} o"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} Ko"
    return f"{size / (1024 * 1024):.2f} Mo"


def _human_age(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min"
    if seconds < 86400:
        return f"{seconds // 3600} h"
    return f"{seconds // 86400} j"


class SettingsPage(BasePage):
    settings_changed = pyqtSignal()
    data_warmed = pyqtSignal()

    def __init__(self, service: DataService, parent=None):
        super().__init__(service, parent)
        self._warmup_running = False

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        content.setMinimumWidth(820)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 8)
        layout.setSpacing(14)
        scroll.setWidget(content)
        self.root.addWidget(scroll, 1)

        layout.addWidget(self._build_preferences())
        layout.addWidget(self._build_sources_card())
        layout.addWidget(self._build_cache_card())
        layout.addWidget(self._build_about())
        layout.addStretch()

        self._load_settings()
        self.refresh_cache()

    # ------------------------------------------------------------------- UI

    def _build_preferences(self) -> Card:
        card = Card("Preferences", "Saison de reference pour les analyses et le modele")
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.season_combo = QComboBox()
        populate_seasons(self.season_combo, self.service.config.seasons)
        form.addRow("Saison de reference", self.season_combo)

        self.ollama_edit = QLineEdit()
        self.ollama_edit.setPlaceholderText("http://127.0.0.1:11434")
        form.addRow("Serveur Ollama", self.ollama_edit)

        card.add_layout(form)
        note = QLabel(
            "Ces preferences sont conservees dans le fichier settings.json du dossier "
            "de donnees. Le serveur Ollama sert a la fenetre « Analyser avec l'IA ». "
            "Aucune base de donnees n'est utilisee."
        )
        note.setObjectName("small")
        note.setWordWrap(True)
        card.add(note)
        row = QHBoxLayout()
        save = QPushButton("Enregistrer les preferences")
        save.setObjectName("primary")
        save.clicked.connect(self._save_settings)
        row.addWidget(save)
        row.addStretch()
        card.add_layout(row)
        return card

    def _build_sources_card(self) -> Card:
        card = Card(
            "Sources de donnees",
            "Gratuites et sans cle personnelle",
        )
        text = QLabel(
            "Resultats et cotes : football-data.co.uk (CSV).\n"
            "Calendriers : OpenFootball (La Liga, Premier League, Bundesliga, "
            "Serie A, Ligue 1), OpenLigaDB (Bundesliga) et TheSportsDB (cle "
            "publique de demonstration, Ligue des Champions partielle).\n"
            "Aucune cle API personnelle n'est necessaire."
        )
        text.setWordWrap(True)
        text.setObjectName("small")
        card.add(text)
        note = QLabel(
            "La Ligue des Champions ne dispose que d'un calendrier partiel via la cle "
            "publique TheSportsDB, pour la saison en cours : le classement est calcule "
            "sur les matchs disponibles."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {AMBER};")
        card.add(note)
        return card

    def _build_cache_card(self) -> Card:
        card = Card(
            "Cache session",
            "Les reponses des sources sont gardees en memoire, sans base de donnees",
        )
        self.cache_banner = Banner()
        card.add(self.cache_banner)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(18)
        self.cache_entries_label = QLabel("—")
        self.cache_size_label = QLabel("—")
        self.cache_hit_label = QLabel("—")
        self.cache_state_label = QLabel("—")
        for label, widget in (
            ("Entrees", self.cache_entries_label),
            ("Taille", self.cache_size_label),
            ("Taux de succes (session)", self.cache_hit_label),
            ("Etat", self.cache_state_label),
        ):
            box = QVBoxLayout()
            caption = QLabel(label.upper())
            caption.setStyleSheet(
                f"color: {MUTED}; font-size: 7.5pt; font-weight: 700; letter-spacing: 1px;"
            )
            widget.setStyleSheet(
                f"color: {TEXT}; font-family: 'Cascadia Mono', Consolas, monospace; "
                f"font-size: 11pt; font-weight: 700;"
            )
            box.addWidget(caption)
            box.addWidget(widget)
            stats_row.addLayout(box, 1)
        card.add_layout(stats_row)

        self.cache_table = QTableWidget()
        configure_table(
            self.cache_table,
            ["Contenu", "Endpoint", "Age", "Expire", "Taille", "Etat"],
            stretch_columns=[0],
            row_height=30,
        )
        self.cache_table.setMinimumHeight(240)
        card.add(self.cache_table)

        ttl_label = QLabel(
            "Duree de cache : 6 a 12 h pour la saison en cours, 30 j pour les saisons passees. "
            "Le cache est vide a chaque redemarrage de l'application."
        )
        ttl_label.setObjectName("small")
        ttl_label.setWordWrap(True)
        card.add(ttl_label)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        refresh = QPushButton("Rafraichir les statistiques")
        refresh.clicked.connect(self._refresh_cache_only)
        actions.addWidget(refresh)
        clear = QPushButton("Vider le cache")
        clear.setObjectName("danger")
        clear.clicked.connect(self._clear_cache)
        actions.addWidget(clear)
        actions.addStretch()
        self.warmup_button = QPushButton("Precharger les donnees")
        self.warmup_button.setObjectName("primary")
        self.warmup_button.clicked.connect(self._warmup)
        actions.addWidget(self.warmup_button)
        card.add_layout(actions)

        self.warmup_status = QLabel("—")
        self.warmup_status.setObjectName("small")
        self.warmup_status.setWordWrap(True)
        card.add(self.warmup_status)
        self.warmup_progress = QProgressBar()
        self.warmup_progress.setRange(0, 100)
        self.warmup_progress.setValue(0)
        self.warmup_progress.setTextVisible(False)
        self.warmup_progress.setVisible(False)
        card.add(self.warmup_progress)
        return card

    def _build_about(self) -> Card:
        card = Card("A propos", f"{APP_NAME} v{APP_VERSION}")
        about = QLabel(
            "Application desktop d'analyse football alimentee par des sources gratuites "
            "(football-data.co.uk, OpenFootball, OpenLigaDB, TheSportsDB). Les reglages "
            "sont dans data/settings.json et le cache des reponses est conserve en memoire."
        )
        about.setWordWrap(True)
        about.setObjectName("small")
        card.add(about)

        link = QLabel(
            '<a href="https://github.com/openfootball/football.json" style="color:#28d17c;">'
            "Calendriers OpenFootball</a>"
        )
        link.setOpenExternalLinks(True)
        card.add(link)

        disclaimer = QLabel(DISCLAIMER)
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet(f"color: {MUTED};")
        card.add(disclaimer)

        buttons = QHBoxLayout()
        button = QPushButton("Ouvrir le dossier des reglages")
        button.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(self.service.config.data_dir))
            )
        )
        buttons.addWidget(button)
        responsible = QPushButton("Avertissement jeu responsable")
        responsible.clicked.connect(self.show_disclaimer)
        buttons.addWidget(responsible)
        buttons.addStretch()
        card.add_layout(buttons)
        return card

    # ------------------------------------------------------------- lifecycle

    def on_show(self) -> None:
        self._load_settings()
        self.refresh_cache()

    def _load_settings(self) -> None:
        settings = self.service.settings()
        self.season_combo.blockSignals(True)
        index = self.season_combo.findData(
            int(settings.get("default_season") or self.service.config.default_season)
        )
        if index >= 0:
            self.season_combo.setCurrentIndex(index)
        self.season_combo.blockSignals(False)
        self.ollama_edit.setText(self.service.ollama_url())

    def _save_settings(self) -> None:
        self.service.update_settings(
            {
                "default_season": self.season_combo.currentData(),
                "ollama_url": self.ollama_edit.text(),
            }
        )
        self.toast.emit("Preferences enregistrees.")
        self.settings_changed.emit()

    # --------------------------------------------------------------- cache

    def refresh_cache(self) -> None:
        stats = self.service.cache_stats()
        self.cache_entries_label.setText(str(stats["entries"]))
        self.cache_size_label.setText(_human_size(stats["bytes"]))
        self.cache_hit_label.setText(f"{stats['hit_rate'] * 100:.0f} %")
        self.cache_state_label.setText(f"{stats['fresh']} frais / {stats['stale']} perimes")
        self.cache_banner.set_message(
            f"Cache session : {stats['entries']} reponse(s), {_human_size(stats['bytes'])}. "
            "Les donnees sont gardees en memoire jusqu'a la fermeture de l'application.",
            "info",
        )

        entries = self.service.cache_list(60)
        now = datetime.now().timestamp()
        self.cache_table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            label = entry.get("label") or entry.get("endpoint") or "—"
            params = entry.get("params") or {}
            if params:
                label += " • " + ", ".join(f"{k}={v}" for k, v in list(params.items())[:3])
            label_item = table_item(label)
            label_item.setToolTip(json.dumps(params, ensure_ascii=False))
            self.cache_table.setItem(row, 0, label_item)
            self.cache_table.setItem(row, 1, table_item(entry.get("endpoint") or "—", color=MUTED))
            self.cache_table.setItem(
                row, 2, table_item(_human_age(now - entry["fetched_at"]), color=MUTED)
            )
            remaining = entry["expires_at"] - now
            expire_text = f"dans {_human_age(remaining)}" if remaining > 0 else "expire"
            self.cache_table.setItem(
                row, 3, table_item(expire_text, color=ACCENT if remaining > 0 else AMBER)
            )
            self.cache_table.setItem(row, 4, table_item(_human_size(entry["size"]), align_right=True))
            badge = Badge("FRAIS" if entry["fresh"] else "PERIME", "green" if entry["fresh"] else "amber")
            wrapper = QWidget()
            wrap_layout = QHBoxLayout(wrapper)
            wrap_layout.setContentsMargins(4, 0, 4, 0)
            wrap_layout.addStretch()
            wrap_layout.addWidget(badge)
            wrap_layout.addStretch()
            self.cache_table.setCellWidget(row, 5, wrapper)

    def _refresh_cache_only(self) -> None:
        self.refresh_cache()
        self.toast.emit("Statistiques actualisees.")

    def _clear_cache(self) -> None:
        if not self.confirm(
            "Vider le cache",
            "Supprimer toutes les reponses en cache ?\n"
            "Les prochains chargements devront retelecharger les donnees.",
        ):
            return
        count = self.service.cache_clear()
        self.refresh_cache()
        self.toast.emit(f"Cache vide ({count} entree(s)).")

    # --------------------------------------------------------------- warmup

    def _warmup(self) -> None:
        if self._warmup_running:
            return
        leagues = self.service.tracked_leagues()
        seasons = list(self.service.config.free_seasons)
        estimate = 2 + 2 * len(leagues) * len(seasons)
        if not self.confirm(
            "Precharger les donnees",
            f"Cette operation va charger les matchs du jour et de demain, puis les classements "
            f"et les saisons {', '.join(str(s) for s in seasons)} de {len(leagues)} ligue(s).\n"
            f"Environ {estimate} etapes seront traitees. Aucune cle API n'est necessaire.",
        ):
            return
        self._warmup_running = True
        self.warmup_button.setEnabled(False)
        self.warmup_button.setText("Prechargement...")
        self.warmup_progress.setVisible(True)
        self.warmup_progress.setValue(0)
        self.warmup_status.setText("Preparation...")

        self.run_task(
            lambda progress: self.service.warmup(progress),
            self._on_warmup_done,
            self._on_warmup_error,
            progress=self._on_warmup_progress,
            busy_text="Prechargement des donnees...",
        )

    def _on_warmup_progress(self, index: int, total: int, label: str) -> None:
        percent = int(index / max(1, total) * 100)
        self.warmup_progress.setValue(percent)
        self.warmup_status.setText(f"[{index}/{total}] {label}")

    def _on_warmup_done(self, result: dict) -> None:
        self._warmup_running = False
        self.warmup_button.setEnabled(True)
        self.warmup_button.setText("Precharger les donnees")
        self.warmup_progress.setValue(100)
        errors = result.get("errors") or []
        if errors:
            self.warmup_status.setText(
                f"Prechargement termine avec {len(errors)} erreur(s) : " + " | ".join(errors[:3])
            )
            self.cache_banner.set_message(
                f"Prechargement partiel : {len(errors)} erreur(s). Les donnees deja en cache restent disponibles.",
                "warning",
            )
        else:
            self.warmup_status.setText(
                f"Prechargement termine : {len(result.get('steps') or [])} etape(s) traitee(s)."
            )
            self.cache_banner.set_message(
                "Prechargement termine. Les pages Matchs et Analyse sont pretes.",
                "success",
            )
        self.refresh_cache()
        self.data_warmed.emit()

    def _on_warmup_error(self, code: str, message: str) -> None:
        self._warmup_running = False
        self.warmup_button.setEnabled(True)
        self.warmup_button.setText("Precharger les donnees")
        self.warmup_progress.setVisible(False)
        self.warmup_status.setText(message)
        self.show_source_error(code, message)
