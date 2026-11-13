"""Tableau de bord : pronostics suivis, matchs a venir, sources et cache."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...service import DataService
from ...theme import ACCENT, AMBER, BLUE, MUTED, RED, TEXT, TEXT_SOFT
from ..base import BasePage
from ..common import configure_table, score_text, status_badge
from ..widgets import (
    Badge,
    Banner,
    Card,
    EmptyState,
    LogoLabel,
    SmallButton,
    StatCard,
    table_item,
)


class DashboardPage(BasePage):
    navigate = pyqtSignal(str, object)
    open_analysis = pyqtSignal(object)

    def __init__(self, service: DataService, parent=None):
        super().__init__(service, parent)
        self._fixtures_loaded = False
        self._fixtures_loading = False
        self._fixtures: list[dict] = []
        self._loaded_day = date.today()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        content.setMinimumWidth(940)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 8)
        layout.setSpacing(14)
        scroll.setWidget(content)
        self.root.addWidget(scroll, 1)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        self.card_total = StatCard("Pronostics", "—", "Suivis localement", ACCENT, "▦")
        self.card_pending = StatCard("En attente", "—", "Resultat a renseigner", AMBER, "◷")
        self.card_winrate = StatCard("Reussite", "—", "Gagnes / decides", BLUE, "✓")
        self.card_edge = StatCard("Edge moyen", "—", "Modele face aux cotes", ACCENT, "↗")
        for card in (self.card_total, self.card_pending, self.card_winrate, self.card_edge):
            stats_row.addWidget(card, 1)
        layout.addLayout(stats_row)

        main_row = QHBoxLayout()
        main_row.setSpacing(14)
        main_row.addWidget(self._build_matches_card(), 2)
        main_row.addWidget(self._build_predictions_card(), 1)
        layout.addLayout(main_row)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(14)
        bottom_row.addWidget(self._build_sources_card(), 1)
        bottom_row.addWidget(self._build_cache_card(), 1)
        bottom_row.addWidget(self._build_responsible_card(), 1)
        layout.addLayout(bottom_row)
        layout.addStretch()

        self.refresh_stats()
        self.refresh_cache()
        self.refresh_predictions()

    # ------------------------------------------------------------------- UI

    def _build_matches_card(self) -> Card:
        card = Card(
            "Matchs a venir",
            "Vos competitions suivies, sources gratuites autour d'aujourd'hui",
        )
        self.matches_badge = Badge("—", "gray")
        card.add_header_widget(self.matches_badge)
        view_all = QPushButton("Tout voir")
        view_all.setObjectName("ghost")
        view_all.clicked.connect(lambda: self.navigate.emit("matches", None))
        card.add_header_widget(view_all)

        self.matches_banner = Banner()
        card.add(self.matches_banner)

        self.matches_holder = QWidget()
        self.matches_layout = QVBoxLayout(self.matches_holder)
        self.matches_layout.setContentsMargins(0, 0, 0, 0)
        self.matches_layout.setSpacing(8)
        card.add(self.matches_holder, 1)

        footer = QHBoxLayout()
        archive = QPushButton("Explorer l'archive des saisons")
        archive.setObjectName("link")
        archive.clicked.connect(lambda: self.navigate.emit("matches_archive", None))
        footer.addWidget(archive)
        footer.addStretch()
        card.add_layout(footer)
        return card

    def _build_predictions_card(self) -> Card:
        card = Card("Derniers pronostics", "Suivi local, sans mise ni bankroll")
        view_all = QPushButton("Tout voir")
        view_all.setObjectName("ghost")
        view_all.clicked.connect(lambda: self.navigate.emit("predictions", None))
        card.add_header_widget(view_all)

        self.predictions_table = QTableWidget()
        configure_table(
            self.predictions_table,
            ["Match", "Selection", "Cote", "Statut"],
            stretch_columns=[0],
            row_height=38,
        )
        self.predictions_table.setMinimumHeight(250)
        card.add(self.predictions_table)
        self.predictions_empty = QLabel("Aucun pronostic enregistre pour le moment.")
        self.predictions_empty.setObjectName("small")
        self.predictions_empty.setWordWrap(True)
        self.predictions_empty.setVisible(False)
        card.add(self.predictions_empty)
        return card

    def _build_sources_card(self) -> Card:
        card = Card("Sources gratuites", "Aucune cle API personnelle requise")
        text = QLabel(
            "football-data.co.uk : resultats et cotes 1X2 / Over-Under.\n"
            "OpenFootball et OpenLigaDB : calendriers et journees.\n"
            "TheSportsDB : Ligue des Champions (calendrier partiel)."
        )
        text.setObjectName("small")
        text.setWordWrap(True)
        card.add(text)
        button = QPushButton("Gerer les ligues")
        button.clicked.connect(lambda: self.navigate.emit("leagues", None))
        card.add(button)
        return card

    def _build_cache_card(self) -> Card:
        card = Card(
            "Cache persistant",
            "Donnees gratuites conservees entre les sessions",
        )
        self.cache_value = QLabel("—")
        self.cache_value.setObjectName("valueMedium")
        card.add(self.cache_value)
        self.cache_hint = QLabel("—")
        self.cache_hint.setObjectName("small")
        self.cache_hint.setWordWrap(True)
        card.add(self.cache_hint)
        button = QPushButton("Gerer le cache")
        button.clicked.connect(lambda: self.navigate.emit("settings", None))
        card.add(button)
        return card

    def _build_responsible_card(self) -> Card:
        card = Card("Analyse responsable", "Outil de pronostics, pas de gestion de capital")
        text = QLabel(
            "L'application ne suit ni bankroll ni mises. Les probabilites du modele sont "
            "informatives et ne garantissent aucun resultat."
        )
        text.setObjectName("small")
        text.setWordWrap(True)
        card.add(text)
        button = QPushButton("Avertissement complet")
        button.clicked.connect(self.show_disclaimer)
        card.add(button)
        return card

    # ------------------------------------------------------------- lifecycle

    def on_show(self) -> None:
        self.refresh_stats()
        self.refresh_predictions()
        self.refresh_cache()
        if self._loaded_day != date.today():
            self._fixtures_loaded = False
            self._loaded_day = date.today()
        if not self._fixtures_loaded and not self._fixtures_loading:
            self._load_fixtures()

    def refresh_after_leagues(self) -> None:
        self._fixtures_loaded = False
        if self.isVisible():
            self._load_fixtures()

    # ------------------------------------------------------------------ data

    def _load_fixtures(self) -> None:
        if self._fixtures_loading:
            return
        if not self.service.tracked_leagues():
            self._show_matches_message(
                "Aucune ligue suivie",
                "Ajoutez La Liga, Bundesliga, Serie A, Ligue 1 ou la Ligue des Champions.",
            )
            self.matches_badge.setText("0 LIGUE")
            self.matches_badge.set_kind("amber")
            return
        self._fixtures_loading = True
        self._show_matches_message("Chargement...", "Recuperation des matchs du jour.")
        today = date.today().isoformat()
        self.run_task(
            lambda _progress: self.service.fixtures_by_date(today),
            self._on_fixtures_loaded,
            self._on_fixtures_error,
            busy_text="Recuperation des matchs du jour...",
        )

    def _on_fixtures_loaded(self, result: dict) -> None:
        self._fixtures_loading = False
        self._fixtures_loaded = True
        self._fixtures = result.get("items") or []
        self._render_matches()
        if result.get("warning"):
            self.matches_banner.set_message(result["warning"], "warning")
        else:
            self.matches_banner.set_message("")

    def _on_fixtures_error(self, code: str, message: str) -> None:
        self._fixtures_loading = False
        self.matches_badge.setText("ERREUR")
        self.matches_badge.set_kind("red")
        self.matches_banner.set_message(message, "error")
        self._show_matches_message(
            "Impossible de charger les matchs",
            message,
            retry=True,
        )

    def _render_matches(self) -> None:
        self._clear_matches()
        items = self._fixtures[:6]
        self.matches_badge.setText(f"{len(self._fixtures)} MATCH(S)")
        self.matches_badge.set_kind("green" if self._fixtures else "gray")
        if not items:
            self._show_matches_message(
                "Aucun match aujourd'hui dans vos ligues",
                "Les sources gratuites ne publient pas encore de match pour cette date. "
                "Explorez les autres dates ou l'archive des saisons 2025-2026.",
                tomorrow=True,
            )
            return
        for fixture in items:
            self.matches_layout.addWidget(self._build_match_row(fixture))
        self.matches_layout.addStretch()

    def _build_match_row(self, fixture: dict) -> QWidget:
        row = QWidget()
        row.setStyleSheet("QWidget { background: transparent; }")
        layout = QVBoxLayout(row)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(7)
        row.setObjectName("innerCard")
        row.setStyleSheet(
            "QWidget#innerCard { background: #0d1520; border: 1px solid #182538; border-radius: 10px; }"
        )

        top = QHBoxLayout()
        top.setSpacing(8)
        league = QLabel(fixture["league"].get("name") or "—")
        league.setStyleSheet(f"color: {MUTED}; font-size: 8.5pt; font-weight: 600;")
        top.addWidget(league)
        round_label = QLabel(fixture["league"].get("round") or "")
        round_label.setObjectName("small")
        top.addWidget(round_label)
        top.addStretch()
        badge = status_badge(fixture)
        top.addWidget(badge)
        layout.addLayout(top)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        time_label = QLabel(self._time(fixture.get("date")))
        time_label.setStyleSheet(
            "color: #b9c7db; font-family: 'Cascadia Mono', Consolas, monospace; font-size: 8.5pt;"
        )
        bottom.addWidget(time_label)
        bottom.addWidget(LogoLabel(fixture["home"].get("logo") or "", 18))
        home = QLabel(fixture["home"].get("name") or "—")
        home.setStyleSheet(f"color: {TEXT}; font-weight: 600;")
        bottom.addWidget(home)
        if fixture.get("status", {}).get("short") in {"FT", "AET", "PEN"}:
            score = QLabel(score_text(fixture))
            score.setStyleSheet(
                "color: #28d17c; font-family: 'Cascadia Mono', Consolas, monospace; font-weight: 700;"
            )
            bottom.addWidget(score)
        else:
            vs = QLabel("vs")
            vs.setStyleSheet(f"color: {MUTED};")
            bottom.addWidget(vs)
        bottom.addWidget(LogoLabel(fixture["away"].get("logo") or "", 18))
        away = QLabel(fixture["away"].get("name") or "—")
        away.setStyleSheet(f"color: {TEXT}; font-weight: 600;")
        bottom.addWidget(away)
        bottom.addStretch()
        analyze = SmallButton("Analyser", primary=True)
        analyze.clicked.connect(lambda _checked=False, f=fixture: self.open_analysis.emit(f))
        bottom.addWidget(analyze)
        layout.addLayout(bottom)
        return row

    def _show_matches_message(
        self,
        title: str,
        text: str = "",
        retry: bool = False,
        tomorrow: bool = False,
    ) -> None:
        self._clear_matches()
        empty = EmptyState(title, text)
        self.matches_layout.addWidget(empty)
        buttons = QHBoxLayout()
        buttons.addStretch()
        if tomorrow:
            tomorrow_button = QPushButton("Voir demain")
            tomorrow_button.setObjectName("primary")
            tomorrow_button.clicked.connect(
                lambda: self.navigate.emit(
                    "matches", date.today() + timedelta(days=1)
                )
            )
            buttons.addWidget(tomorrow_button)
        if retry:
            retry_button = QPushButton("Reessayer")
            retry_button.clicked.connect(self._load_fixtures)
            buttons.addWidget(retry_button)
        archive = QPushButton("Ouvrir l'archive")
        archive.clicked.connect(lambda: self.navigate.emit("matches_archive", None))
        buttons.addWidget(archive)
        buttons.addStretch()
        self.matches_layout.addLayout(buttons)
        self.matches_layout.addStretch()

    def _clear_matches(self) -> None:
        while self.matches_layout.count():
            item = self.matches_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            elif item.layout():
                layout = item.layout()
                while layout.count():
                    child = layout.takeAt(0)
                    child_widget = child.widget()
                    if child_widget:
                        child_widget.deleteLater()
                layout.deleteLater()

    # ---------------------------------------------------------------- stats

    def refresh_stats(self) -> None:
        stats = self.service.prediction_stats()
        self.card_total.set_value(
            str(stats["total"]),
            f"{stats['settled']} regle(s) • {stats['value_count']} edge positif",
        )
        self.card_pending.set_value(
            str(stats["pending"]),
            "Resultat a renseigner",
        )
        self.card_winrate.set_value(
            f"{stats['win_rate'] * 100:.0f} %",
            f"{stats['won']} gagne(s) / {stats['lost']} perdu(s)",
        )
        average_edge = stats["average_edge"] * 100
        self.card_edge.set_value(
            f"{average_edge:+.1f} %",
            f"Cote moyenne : {stats['average_odds']:.2f}" if stats["average_odds"] else "Aucune cote",
            ACCENT if average_edge >= 0 else RED,
        )

    def refresh_predictions(self) -> None:
        predictions = self.service.db.list_predictions()[:6]
        self.predictions_table.setRowCount(0)
        if not predictions:
            self.predictions_table.setVisible(False)
            self.predictions_empty.setVisible(True)
            return
        self.predictions_table.setVisible(True)
        self.predictions_empty.setVisible(False)
        self.predictions_table.setRowCount(len(predictions))
        for row, prediction in enumerate(predictions):
            match_item = table_item(
                f"{prediction['home']} — {prediction['away']}", bold=True
            )
            match_item.setToolTip(prediction.get("note") or "")
            self.predictions_table.setItem(row, 0, match_item)
            self.predictions_table.setItem(row, 1, table_item(prediction["selection"]))
            odd = prediction.get("odds")
            self.predictions_table.setItem(
                row,
                2,
                table_item(f"{odd:.2f}" if odd is not None else "—", align_right=True),
            )
            kind = {"pending": "blue", "won": "green", "lost": "red", "void": "gray"}.get(
                prediction["status"], "gray"
            )
            labels = {"pending": "En cours", "won": "Gagne", "lost": "Perdu", "void": "Annule"}
            badge = Badge(labels.get(prediction["status"], prediction["status"]), kind)
            wrapper = QWidget()
            wrap_layout = QHBoxLayout(wrapper)
            wrap_layout.setContentsMargins(2, 0, 2, 0)
            wrap_layout.addStretch()
            wrap_layout.addWidget(badge)
            self.predictions_table.setCellWidget(row, 3, wrapper)

    def refresh_cache(self) -> None:
        stats = self.service.cache_stats()
        self.cache_value.setText(
            f"{stats['entries']} reponse(s)"
        )
        self.cache_hint.setText(
            f"{stats['bytes'] / 1024:.0f} Ko • {stats['fresh']} fraiche(s), "
            f"{stats['stale']} perimee(s) • succes session : {stats['hit_rate'] * 100:.0f} %"
        )

    @staticmethod
    def _time(value: str | None) -> str:
        if not value:
            return "—"
        try:
            return datetime.fromisoformat(value).astimezone().strftime("%H:%M")
        except (ValueError, TypeError):
            return "—"
