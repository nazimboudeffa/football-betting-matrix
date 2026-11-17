"""Page Ligues : gestion des competitions suivies via les sources gratuites."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ...service import DataService
from ...theme import ACCENT, MUTED
from ..base import BasePage
from ..common import configure_table
from ..widgets import Banner, Card, EmptyState, SmallButton, TeamBadge, table_item


class LeaguesPage(BasePage):
    leagues_changed = pyqtSignal()

    def __init__(self, service: DataService, parent=None):
        super().__init__(service, parent)
        self._adding = False

        self.banner = Banner(
            "Sources gratuites : football-data.co.uk (resultats, cotes, xG), "
            "OpenFootball, OpenLigaDB et TheSportsDB. Aucune cle API "
            "personnelle n'est necessaire.",
            "info",
        )
        self.root.addWidget(self.banner)

        tracked_card = Card(
            "Competitions suivies",
            "Les matchs, classements et analyses s'appuient sur cette liste",
        )
        self.reset_button = QPushButton("Restaurer les 6 ligues par defaut")
        self.reset_button.setObjectName("ghost")
        self.reset_button.clicked.connect(self._restore_defaults)
        tracked_card.add_header_widget(self.reset_button)

        self.tracked_table = QTableWidget()
        configure_table(
            self.tracked_table,
            ["Competition", "Pays", "ID", "Source", ""],
            stretch_columns=[0],
            row_height=44,
        )
        tracked_card.add(self.tracked_table, 1)
        self.root.addWidget(tracked_card, 3)

        available_card = Card(
            "Ligues disponibles",
            "Ajoutez une ligue : elle apparait en haut de la liste suivie. "
            "Une ligue retiree revient ici en bas.",
        )
        self.available_banner = Banner()
        available_card.add(self.available_banner)

        self.available_stack = QStackedWidget()
        self.available_table = QTableWidget()
        configure_table(
            self.available_table,
            ["Competition", "Pays", "ID", ""],
            stretch_columns=[0],
            row_height=42,
        )
        self.available_stack.addWidget(self.available_table)
        self.available_empty = QWidget()
        self.available_empty_layout = QVBoxLayout(self.available_empty)
        self.available_empty_layout.setContentsMargins(0, 0, 0, 0)
        self.available_stack.addWidget(self.available_empty)
        available_card.add(self.available_stack, 1)
        self.root.addWidget(available_card, 4)

        self._refresh()

    # ------------------------------------------------------------------ data

    def on_show(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        self._render_tracked()
        self._render_available()

    def _render_tracked(self) -> None:
        leagues = self.service.tracked_leagues()
        self.tracked_table.setRowCount(len(leagues))
        for row, league in enumerate(leagues):
            self.tracked_table.setCellWidget(
                row,
                0,
                TeamBadge(league.get("name") or "—", league.get("logo") or "", size=20),
            )
            self.tracked_table.setItem(row, 1, table_item(league.get("country") or "—", color=MUTED))
            self.tracked_table.setItem(row, 2, table_item(str(league.get("id")), color=MUTED))
            source_text, source_color = "Gratuite", ACCENT
            if league.get("default"):
                source_text = "Gratuite • defaut"
            self.tracked_table.setItem(row, 3, table_item(source_text, color=source_color))
            remove_button = SmallButton("Retirer")
            remove_button.setObjectName("danger")
            remove_button.clicked.connect(
                lambda _checked=False, league_id=int(league.get("id")): self._remove(league_id)
            )
            wrapper = QWidget()
            wrap_layout = QHBoxLayout(wrapper)
            wrap_layout.setContentsMargins(2, 2, 2, 2)
            wrap_layout.addWidget(remove_button)
            self.tracked_table.setCellWidget(row, 4, wrapper)

    def _render_available(self) -> None:
        leagues = self.service.available_leagues()
        if not leagues:
            self._set_available_empty(
                "Toutes les ligues sont suivies",
                "Retirez une ligue de la liste du haut pour la retrouver ici en bas.",
            )
            return

        self.available_stack.setCurrentIndex(0)
        self.available_table.setRowCount(len(leagues))
        for row, league in enumerate(leagues):
            self.available_table.setCellWidget(
                row,
                0,
                TeamBadge(league.get("name") or "—", league.get("logo") or "", size=20),
            )
            self.available_table.setItem(
                row, 1, table_item(league.get("country") or "—", color=MUTED)
            )
            self.available_table.setItem(row, 2, table_item(str(league.get("id")), color=MUTED))
            button = SmallButton("Ajouter", primary=True)
            button.clicked.connect(
                lambda _checked=False, item=dict(league): self._add_league(item)
            )
            wrapper = QWidget()
            wrap_layout = QHBoxLayout(wrapper)
            wrap_layout.setContentsMargins(2, 2, 2, 2)
            wrap_layout.addWidget(button)
            self.available_table.setCellWidget(row, 3, wrapper)

    # ---------------------------------------------------------------- actions

    def _add_league(self, league: dict) -> None:
        if self._adding:
            return
        self._adding = True
        try:
            self.service.add_league(league)
        finally:
            self._adding = False
        name = league.get("name") or f"Ligue {league.get('id')}"
        self.available_banner.set_message(f"Ligue ajoutee : {name}.", "success")
        self.toast.emit(f"Ligue ajoutee : {name} ({league.get('country')})")
        self._refresh()
        self.leagues_changed.emit()

    def _remove(self, league_id: int) -> None:
        league = next(
            (item for item in self.service.tracked_leagues() if int(item.get("id")) == league_id),
            None,
        )
        name = league.get("name") if league else f"Ligue {league_id}"
        if not self.confirm(
            "Retirer la ligue",
            f"Retirer « {name} » des competitions suivies ?\n"
            "Les matchs et classements de cette ligue ne seront plus affiches.",
        ):
            return
        self.service.remove_league(league_id)
        self.available_banner.set_message(
            f"Ligue retiree : {name}. Elle est de nouveau disponible en bas de liste.",
            "info",
        )
        self.toast.emit(f"Ligue retiree : {name}")
        self._refresh()
        self.leagues_changed.emit()

    def _restore_defaults(self) -> None:
        if not self.confirm(
            "Restaurer les ligues par defaut",
            "Remplacer la liste actuelle par La Liga, Premier League, "
            "Bundesliga, Serie A, Ligue 1 et Ligue des Champions ?",
        ):
            return
        self.service.restore_default_leagues()
        self.available_banner.set_message("Ligues par defaut restaurees.", "success")
        self.toast.emit("Ligues par defaut restaurees.")
        self._refresh()
        self.leagues_changed.emit()

    # ------------------------------------------------------------------ utils

    def _set_available_empty(self, title: str, text: str = "") -> None:
        while self.available_empty_layout.count():
            item = self.available_empty_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.available_empty_layout.addWidget(EmptyState(title, text))
        self.available_stack.setCurrentIndex(1)
