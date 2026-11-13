"""Page Classements."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...service import DataService
from ...theme import ACCENT, AMBER, BLUE, MUTED, PURPLE, RED, TEXT
from ..base import BasePage
from ..common import configure_table, populate_leagues, populate_seasons
from ..widgets import Badge, Banner, EmptyState, FormBadges, SmallButton, TeamBadge, table_item


class StandingsPage(BasePage):
    def __init__(self, service: DataService, parent=None):
        super().__init__(service, parent)
        self._loading = False
        self._loaded = False
        self._key: tuple[int, int] | None = None
        self._groups: list[dict] = []

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.addWidget(QLabel("Ligue"))
        self.league_combo = QComboBox()
        self.league_combo.setMinimumWidth(190)
        self.league_combo.currentIndexChanged.connect(lambda _i: self._selection_changed())
        toolbar.addWidget(self.league_combo)

        toolbar.addWidget(QLabel("Saison"))
        self.season_combo = QComboBox()
        populate_seasons(
            self.season_combo,
            self.service.config.seasons,
            self.service.settings().get("default_season"),
        )
        self.season_combo.currentIndexChanged.connect(lambda _i: self._selection_changed())
        toolbar.addWidget(self.season_combo)

        self.group_label = QLabel("Groupe")
        toolbar.addWidget(self.group_label)
        self.group_combo = QComboBox()
        self.group_combo.setMinimumWidth(150)
        self.group_combo.currentIndexChanged.connect(lambda _i: self._render())
        toolbar.addWidget(self.group_combo)
        self.group_label.setVisible(False)
        self.group_combo.setVisible(False)

        toolbar.addStretch()
        self.status_label = QLabel("—")
        self.status_label.setObjectName("small")
        toolbar.addWidget(self.status_label)
        refresh = QPushButton("Actualiser")
        refresh.clicked.connect(self._refresh_clicked)
        toolbar.addWidget(refresh)
        self.root.addLayout(toolbar)

        self.banner = Banner(
            "Classements calcules a partir des resultats gratuits "
            "(football-data.co.uk, OpenFootball, OpenLigaDB, TheSportsDB).",
            "info",
        )
        self.root.addWidget(self.banner)

        self.stack = QStackedWidget()
        self.table = QTableWidget()
        configure_table(
            self.table,
            [
                "#",
                "Equipe",
                "Groupe",
                "MJ",
                "V",
                "N",
                "D",
                "BP",
                "BC",
                "Diff",
                "Pts",
                "Forme",
                "Statut",
            ],
            stretch_columns=[1],
            row_height=42,
        )
        self.stack.addWidget(self.table)
        self.empty_holder = QWidget()
        self.empty_layout = QVBoxLayout(self.empty_holder)
        self.empty_layout.setContentsMargins(0, 0, 0, 0)
        self.stack.addWidget(self.empty_holder)
        self.root.addWidget(self.stack, 1)

        self._refresh_leagues()

    # ------------------------------------------------------------- lifecycle

    def on_show(self) -> None:
        if not self._loaded and not self._loading:
            self._load()

    def refresh_leagues(self) -> None:
        self._refresh_leagues()
        self._loaded = False
        self._key = None
        if self.isVisible():
            self._load()

    def refresh(self) -> None:
        self._refresh_clicked()

    def _refresh_clicked(self) -> None:
        self._key = None
        self._load()

    def refresh_after_warmup(self) -> None:
        self._loaded = False
        self._key = None
        if self.isVisible():
            self._load()

    # --------------------------------------------------------------- chargement

    def _refresh_leagues(self) -> None:
        populate_leagues(self.league_combo, self.service.tracked_leagues(), include_all=False)
        if self.league_combo.count() == 0:
            self._show_empty(
                "Aucune ligue suivie",
                "Ajoutez une competition depuis la page Ligues pour afficher son classement.",
            )
            self.status_label.setText("Aucune ligue")

    def _selection_changed(self) -> None:
        self._key = None
        if self.isVisible():
            self._load()

    def _load(self) -> None:
        if self._loading:
            return
        league_id = self.league_combo.currentData()
        season = self.season_combo.currentData()
        if league_id is None or season is None:
            return
        key = (int(league_id), int(season))
        if self._key == key and self._loaded:
            return
        self._loading = True
        self.status_label.setText("Chargement...")
        self.banner.set_message("")
        self._show_empty(
            "Chargement du classement...",
            "La premiere requete peut prendre quelques secondes (telechargement CSV).",
        )

        self.run_task(
            lambda _progress: self.service.standings(int(league_id), int(season)),
            lambda result: self._on_loaded(result, key),
            self._on_error,
            busy_text=f"Chargement du classement {season}...",
        )

    def _on_loaded(self, result: dict, key: tuple[int, int]) -> None:
        self._loading = False
        self._loaded = True
        self._key = key
        self._groups = result.get("groups") or []
        moment = (
            datetime.fromtimestamp(result.get("fetched_at")).strftime("%H:%M")
            if result.get("fetched_at")
            else "—"
        )
        source = result.get("source") or (
            "cache" if result.get("cached") else "Sources gratuites"
        )
        total_rows = sum(len(group.get("rows") or []) for group in self._groups)
        league_name = (result.get("league") or {}).get("name") or "Classement"
        self.status_label.setText(
            f"{league_name} • {total_rows} equipe(s) • {source} • maj {moment}"
        )
        if result.get("warning"):
            self.banner.set_message(result["warning"], "warning")
        else:
            self.banner.set_message("")

        multiple = len(self._groups) > 1
        self.group_label.setVisible(multiple)
        self.group_combo.setVisible(multiple)
        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        if multiple:
            self.group_combo.addItem("Tous les groupes", None)
            for group in self._groups:
                self.group_combo.addItem(group.get("name") or "Groupe", group.get("name"))
        self.group_combo.blockSignals(False)
        self.table.setColumnHidden(2, not multiple)
        self._render()

    def _on_error(self, code: str, message: str) -> None:
        self._loading = False
        self.status_label.setText("Erreur")
        self.banner.set_message(message, "error")
        self._show_empty("Classement indisponible", message, "Reessayer", self._load)
        self.stack.setCurrentIndex(1)
        self.show_source_error(code, message)

    # ---------------------------------------------------------------- rendu

    def _render(self) -> None:
        if not self._groups:
            self._show_empty("Aucun classement", "La source n'a renvoye aucune ligne.")
            return
        group_filter = self.group_combo.currentData() if self.group_combo.isVisible() else None
        rows: list[dict] = []
        for group in self._groups:
            if group_filter and group.get("name") != group_filter:
                continue
            rows.extend(group.get("rows") or [])
        if not rows:
            self._show_empty("Aucune equipe", "Essayez un autre groupe ou une autre saison.")
            return

        self.stack.setCurrentIndex(0)
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            rank_item = table_item(str(row.get("rank") or "—"), bold=True)
            rank_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_index, 0, rank_item)

            team = row.get("team") or {}
            self.table.setCellWidget(
                row_index, 1, TeamBadge(team.get("name") or "—", team.get("logo") or "")
            )

            group_item = table_item(row.get("group") or "—", color=MUTED)
            self.table.setItem(row_index, 2, group_item)

            stats = row.get("all") or {}
            goals = stats.get("goals") or {}
            played = stats.get("played")
            wins = stats.get("win")
            draws = stats.get("draw")
            losses = stats.get("lose")
            self.table.setItem(row_index, 3, table_item(played if played is not None else "—", align_right=True))
            self.table.setItem(row_index, 4, table_item(wins if wins is not None else "—", align_right=True))
            self.table.setItem(row_index, 5, table_item(draws if draws is not None else "—", align_right=True))
            self.table.setItem(row_index, 6, table_item(losses if losses is not None else "—", align_right=True))
            self.table.setItem(row_index, 7, table_item(goals.get("for", "—"), align_right=True))
            self.table.setItem(row_index, 8, table_item(goals.get("against", "—"), align_right=True))

            diff = row.get("goals_diff")
            diff_color = ACCENT if isinstance(diff, int) and diff > 0 else (RED if isinstance(diff, int) and diff < 0 else MUTED)
            self.table.setItem(
                row_index,
                9,
                table_item(f"{diff:+d}" if isinstance(diff, int) else "—", align_right=True, color=diff_color),
            )

            points_item = table_item(row.get("points") if row.get("points") is not None else "—", align_right=True, bold=True)
            self.table.setItem(row_index, 10, points_item)

            form_widget = FormBadges(row.get("form") or "")
            form_cell = QWidget()
            form_layout = QHBoxLayout(form_cell)
            form_layout.setContentsMargins(4, 0, 4, 0)
            form_layout.addWidget(form_widget)
            form_layout.addStretch()
            self.table.setCellWidget(row_index, 11, form_cell)

            description = row.get("description") or ""
            self.table.setItem(row_index, 12, self._status_item(description))

        self.table.setColumnHidden(2, not (len(self._groups) > 1))

    def _status_item(self, description: str) -> QTableWidgetItem:
        if not description:
            return table_item("—", color=MUTED)
        lowered = description.lower()
        if "relegation" in lowered:
            color = RED
        elif "champions" in lowered or "promotion" in lowered:
            color = ACCENT
        elif "europa" in lowered:
            color = BLUE
        elif "conference" in lowered:
            color = PURPLE
        else:
            color = AMBER
        return table_item(description, color=color)

    # ------------------------------------------------------------------ empty

    def _show_empty(
        self,
        title: str,
        text: str = "",
        action_text: str | None = None,
        callback=None,
    ) -> None:
        while self.empty_layout.count():
            item = self.empty_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        empty = EmptyState(title, text, action_text)
        if empty.button and callback:
            empty.button.clicked.connect(callback)
        self.empty_layout.addWidget(empty)
        self.stack.setCurrentIndex(1)
