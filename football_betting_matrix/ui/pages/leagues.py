"""Page Ligues : gestion des competitions suivies via les sources gratuites."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...config import DEFAULT_LEAGUES
from ...service import DataService
from ...theme import ACCENT, MUTED, TEXT
from ..base import BasePage
from ..common import configure_table
from ..widgets import Badge, Banner, Card, EmptyState, SmallButton, TeamBadge, table_item


class LeaguesPage(BasePage):
    leagues_changed = pyqtSignal()

    def __init__(self, service: DataService, parent=None):
        super().__init__(service, parent)
        self._search_results: list[dict] = []
        self._searching = False
        self._adding = False

        self.banner = Banner(
            "Sources gratuites : La Liga (140), Premier League (39), "
            "Bundesliga (78), Serie A (135), Ligue 1 (61) et Ligue des "
            "Champions (2, calendrier partiel). Aucune cle API personnelle "
            "n'est necessaire.",
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

        add_card = Card(
            "Ajouter une ligue",
            "Recherchez parmi les competitions gratuites ou saisissez un ID",
        )
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Rechercher une competition (2 caracteres minimum)...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.returnPressed.connect(self._search)
        search_row.addWidget(self.search_edit, 1)
        search_button = QPushButton("Rechercher")
        search_button.setObjectName("primary")
        search_button.clicked.connect(self._search)
        search_row.addWidget(search_button)
        add_card.add_layout(search_row)

        direct_row = QHBoxLayout()
        direct_row.setSpacing(8)
        direct_label = QLabel("Ou par ID :")
        direct_label.setStyleSheet(f"color: {MUTED};")
        direct_row.addWidget(direct_label)
        self.id_spin = QSpinBox()
        self.id_spin.setRange(1, 100000)
        self.id_spin.setValue(135)
        self.id_spin.setFixedWidth(100)
        direct_row.addWidget(self.id_spin)
        self.add_id_button = QPushButton("Ajouter cet ID")
        self.add_id_button.clicked.connect(self._add_by_id)
        direct_row.addWidget(self.add_id_button)
        direct_row.addStretch()
        add_card.add_layout(direct_row)

        self.search_banner = Banner()
        add_card.add(self.search_banner)

        self.results_stack = QStackedWidget()
        self.results_table = QTableWidget()
        configure_table(
            self.results_table,
            ["Competition", "Pays", "Type", "ID", ""],
            stretch_columns=[0],
            row_height=42,
        )
        self.results_stack.addWidget(self.results_table)
        self.results_empty = QWidget()
        self.results_empty_layout = QVBoxLayout(self.results_empty)
        self.results_empty_layout.setContentsMargins(0, 0, 0, 0)
        self.results_stack.addWidget(self.results_empty)
        add_card.add(self.results_stack, 1)
        self.root.addWidget(add_card, 4)

        self._refresh_tracked()
        self._set_results_empty(
            "Recherchez une competition",
            "La recherche se limite aux competitions couvertes par les sources "
            "gratuites (140, 39, 78, 135, 61, 2).",
        )

    # ------------------------------------------------------------------ data

    def on_show(self) -> None:
        self._refresh_tracked()

    def _tracked_ids(self) -> set[int]:
        return {int(league.get("id", -1)) for league in self.service.tracked_leagues()}

    def _refresh_tracked(self) -> None:
        leagues = self.service.tracked_leagues()
        self.tracked_table.setRowCount(len(leagues))
        tracked_ids = self._tracked_ids()
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
            self.tracked_table.setItem(
                row, 3, table_item(source_text, color=source_color)
            )
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

        # Met a jour les boutons des resultats si la recherche est affichee.
        if self._search_results:
            self._render_results(self._search_results)

    def _remove(self, league_id: int) -> None:
        league = next(
            (l for l in self.service.tracked_leagues() if int(l.get("id")) == league_id), None
        )
        name = league.get("name") if league else f"Ligue {league_id}"
        if not self.confirm(
            "Retirer la ligue",
            f"Retirer « {name} » des competitions suivies ?\n"
            "Les matchs et classements de cette ligue ne seront plus affiches.",
        ):
            return
        self.service.remove_league(league_id)
        self.toast.emit(f"Ligue retiree : {name}")
        self._refresh_tracked()
        self.leagues_changed.emit()

    def _restore_defaults(self) -> None:
        if not self.confirm(
            "Restaurer les ligues par defaut",
            "Remplacer la liste actuelle par La Liga, Premier League, "
            "Bundesliga, Serie A, Ligue 1 et Ligue des Champions ?",
        ):
            return
        settings = self.service.settings()
        settings["tracked_leagues"] = [dict(league) for league in DEFAULT_LEAGUES]
        self.service.save_settings(settings)
        self.toast.emit("Ligues par defaut restaurees.")
        self._refresh_tracked()
        self.leagues_changed.emit()

    # --------------------------------------------------------------- recherche

    def _search(self) -> None:
        query = self.search_edit.text().strip()
        if len(query) < 2:
            self.search_banner.set_message("Saisissez au moins 2 caracteres.", "warning")
            return
        if self._searching:
            return
        self._searching = True
        self.search_banner.set_message("Recherche en cours...", "info")
        self._set_results_empty("Recherche...", "Interrogation du cache local.")
        self.run_task(
            lambda _progress: self.service.search_leagues(query),
            self._on_search_loaded,
            self._on_search_error,
            busy_text=f"Recherche de « {query} »...",
        )

    def _on_search_loaded(self, results: list[dict]) -> None:
        self._searching = False
        self._search_results = results or []
        if not self._search_results:
            self.search_banner.set_message(
                "Aucune competition trouvee. Essayez un autre nom ou un ID direct.", "warning"
            )
            self._set_results_empty(
                "Aucun resultat",
                "Verifiez l'orthographe ou utilisez l'ajout par ID.",
            )
            return
        self.search_banner.set_message(
            f"{len(self._search_results)} competition(s) trouvee(s). "
            "Cliquez sur Ajouter pour suivre une ligue.",
            "success",
        )
        self._render_results(self._search_results)

    def _on_search_error(self, code: str, message: str) -> None:
        self._searching = False
        self.search_banner.set_message(message, "error")
        self._set_results_empty("Recherche impossible", message)
        self.show_source_error(code, message)

    def _render_results(self, results: list[dict]) -> None:
        tracked = self._tracked_ids()
        self.results_stack.setCurrentIndex(0)
        limit = 120
        self.results_table.setRowCount(min(len(results), limit))
        for row, league in enumerate(results[:limit]):
            self.results_table.setCellWidget(
                row,
                0,
                TeamBadge(league.get("name") or "—", league.get("logo") or "", size=20),
            )
            self.results_table.setItem(
                row, 1, table_item(league.get("country") or "—", color=MUTED)
            )
            self.results_table.setItem(
                row, 2, table_item(league.get("type") or "—", color=MUTED)
            )
            self.results_table.setItem(row, 3, table_item(str(league.get("id")), color=MUTED))
            is_tracked = int(league.get("id", -1)) in tracked
            button = SmallButton("Suivie" if is_tracked else "Ajouter", primary=not is_tracked)
            button.setEnabled(not is_tracked)
            if not is_tracked:
                button.clicked.connect(
                    lambda _checked=False, item=dict(league): self._add_league(item)
                )
            wrapper = QWidget()
            wrap_layout = QHBoxLayout(wrapper)
            wrap_layout.setContentsMargins(2, 2, 2, 2)
            wrap_layout.addWidget(button)
            self.results_table.setCellWidget(row, 4, wrapper)

    def _add_league(self, league: dict) -> None:
        if self._adding:
            return
        self._adding = True
        self.service.add_league(league)
        self._adding = False
        self.toast.emit(f"Ligue ajoutee : {league.get('name')} ({league.get('country')})")
        self._refresh_tracked()
        self.leagues_changed.emit()

    def _add_by_id(self) -> None:
        if self._adding:
            return
        league_id = int(self.id_spin.value())
        if league_id in self._tracked_ids():
            self.toast.emit(f"La ligue {league_id} est deja suivie.")
            return
        self._adding = True
        self.add_id_button.setEnabled(False)
        self.add_id_button.setText("Ajout...")
        self.run_task(
            lambda _progress: self.service.league_info(league_id),
            self._on_league_info_loaded,
            self._on_league_info_error,
            busy_text=f"Recherche de la ligue {league_id}...",
        )

    def _on_league_info_loaded(self, league: dict | None) -> None:
        self._adding = False
        self.add_id_button.setEnabled(True)
        self.add_id_button.setText("Ajouter cet ID")
        if not league:
            self.search_banner.set_message(
                f"Aucune ligue trouvee pour l'ID {self.id_spin.value()}.", "warning"
            )
            return
        self._add_league(league)
        self.search_banner.set_message(
            f"Ligue ajoutee : {league.get('name')} ({league.get('country')}).", "success"
        )

    def _on_league_info_error(self, code: str, message: str) -> None:
        self._adding = False
        self.add_id_button.setEnabled(True)
        self.add_id_button.setText("Ajouter cet ID")
        self.search_banner.set_message(message, "error")
        self.show_source_error(code, message)

    # ------------------------------------------------------------------ utils

    def _set_results_empty(self, title: str, text: str = "") -> None:
        while self.results_empty_layout.count():
            item = self.results_empty_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.results_empty_layout.addWidget(EmptyState(title, text))
        self.results_stack.setCurrentIndex(1)
