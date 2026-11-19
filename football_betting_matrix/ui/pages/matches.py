"""Page Matchs : direct (autour d'aujourd'hui) + archive des saisons accessibles."""

from __future__ import annotations

from datetime import date, datetime

from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...service import DataService
from ...theme import AMBER, BLUE, MUTED, TEXT
from ..base import BasePage
from ..common import (
    configure_table,
    fit_widget_column,
    format_odd,
    populate_leagues,
    populate_seasons,
    score_text,
    status_badge,
)
from ..widgets import Banner, EmptyState, SmallButton, TeamBadge, make_mono_label


def _time_label(iso_date: str | None) -> str:
    if not iso_date:
        return "—"
    try:
        return datetime.fromisoformat(iso_date).astimezone().strftime("%d/%m %H:%M")
    except (ValueError, TypeError):
        return iso_date[:16].replace("T", " ")


def _short_round(value: str) -> str:
    text = value or "—"
    for prefix, replacement in (
        ("Regular Season - ", "J"),
        ("League Stage - ", "J"),
        ("Group Stage - ", "Gr. "),
        ("Round of 16", "8es"),
        ("Quarter-finals", "Quarts"),
        ("Semi-finals", "Demies"),
        ("Final", "Finale"),
    ):
        if text.startswith(prefix):
            return replacement + text[len(prefix) :]
    return text


class MatchesPage(BasePage):
    open_analysis = pyqtSignal(object)

    def __init__(self, service: DataService, parent=None):
        super().__init__(service, parent)
        self._live_loaded = False
        self._live_loading = False
        self._live_items: list[dict] = []
        self._archive_loading = False
        self._archive_key: tuple[int, int] | None = None
        self._archive_items: list[dict] = []

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_live_tab(), "Autour d'aujourd'hui")
        self.tabs.addTab(self._build_archive_tab(), "Archive des saisons")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.root.addWidget(self.tabs, 1)
        self._refresh_league_combos()

    # ------------------------------------------------------------------ UI

    def _build_live_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)

        info = Banner(
            "Sources gratuites : calendriers OpenFootball / OpenLigaDB / TheSportsDB et "
            "resultats-cotes football-data.co.uk. Aucune cle personnelle requise.",
            "info",
        )
        layout.addWidget(info)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        date_label = QLabel("Date")
        date_label.setStyleSheet(f"color: {MUTED};")
        toolbar.addWidget(date_label)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        today = date.today()
        self.date_edit.setDateRange(
            QDate(today.year, today.month, today.day).addDays(-730),
            QDate(today.year, today.month, today.day).addDays(120),
        )
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.dateChanged.connect(lambda _d: self.load_live())
        toolbar.addWidget(self.date_edit)

        self.live_league_combo = QComboBox()
        self.live_league_combo.setMinimumWidth(180)
        self.live_league_combo.currentIndexChanged.connect(lambda _i: self._render_live())
        toolbar.addWidget(self.live_league_combo)

        toolbar.addStretch()
        self.live_status_label = QLabel("—")
        self.live_status_label.setObjectName("small")
        toolbar.addWidget(self.live_status_label)

        refresh = QPushButton("Actualiser")
        refresh.clicked.connect(lambda: self.load_live(force=True))
        toolbar.addWidget(refresh)
        layout.addLayout(toolbar)

        self.live_banner = Banner()
        layout.addWidget(self.live_banner)

        self.live_stack = QStackedWidget()
        self.live_table = QTableWidget()
        configure_table(
            self.live_table,
            ["Heure", "Competition", "Domicile", "Score", "Exterieur", "Statut", ""],
            stretch_columns=[2, 4],
            row_height=44,
        )
        header = self.live_table.horizontalHeader()
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(5, 130)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(6, 96)
        self.live_table.cellDoubleClicked.connect(self._on_live_double_click)
        self.live_stack.addWidget(self.live_table)
        self.live_empty_holder = QWidget()
        self.live_empty_layout = QVBoxLayout(self.live_empty_holder)
        self.live_empty_layout.setContentsMargins(0, 0, 0, 0)
        self.live_stack.addWidget(self.live_empty_holder)
        layout.addWidget(self.live_stack, 1)

        return page

    def _build_archive_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)

        info = Banner(
            "Archive 2025-2026 : resultats et cotes CSV gratuits, calendriers OpenFootball / "
            "OpenLigaDB / TheSportsDB.",
            "info",
        )
        layout.addWidget(info)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.addWidget(QLabel("Ligue"))
        self.archive_league_combo = QComboBox()
        self.archive_league_combo.setMinimumWidth(170)
        self.archive_league_combo.currentIndexChanged.connect(lambda _i: self._archive_selection_changed())
        toolbar.addWidget(self.archive_league_combo)

        toolbar.addWidget(QLabel("Saison"))
        self.archive_season_combo = QComboBox()
        populate_seasons(self.archive_season_combo, self.service.config.seasons, self.service.settings().get("default_season"))
        self.archive_season_combo.currentIndexChanged.connect(lambda _i: self._archive_selection_changed())
        toolbar.addWidget(self.archive_season_combo)

        self.archive_search = QLineEdit()
        self.archive_search.setPlaceholderText("Filtrer par equipe...")
        self.archive_search.setClearButtonEnabled(True)
        self.archive_search.setMinimumWidth(200)
        self.archive_search.textChanged.connect(lambda _t: self._render_archive())
        toolbar.addWidget(self.archive_search, 1)

        self.archive_status_label = QLabel("—")
        self.archive_status_label.setObjectName("small")
        toolbar.addWidget(self.archive_status_label)

        refresh = QPushButton("Actualiser")
        refresh.clicked.connect(lambda: self._load_archive(force=True))
        toolbar.addWidget(refresh)
        layout.addLayout(toolbar)

        self.archive_banner = Banner()
        layout.addWidget(self.archive_banner)

        self.archive_stack = QStackedWidget()
        self.archive_table = QTableWidget()
        configure_table(
            self.archive_table,
            ["Date", "Journee", "Domicile", "Score", "Exterieur", ""],
            stretch_columns=[2, 4],
            row_height=44,
        )
        header = self.archive_table.horizontalHeader()
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(5, 96)
        self.archive_table.cellDoubleClicked.connect(self._on_archive_double_click)
        self.archive_stack.addWidget(self.archive_table)
        self.archive_empty_holder = QWidget()
        self.archive_empty_layout = QVBoxLayout(self.archive_empty_holder)
        self.archive_empty_layout.setContentsMargins(0, 0, 0, 0)
        self.archive_stack.addWidget(self.archive_empty_holder)
        layout.addWidget(self.archive_stack, 1)

        self._refresh_league_combos()
        return page

    # ------------------------------------------------------------ navigation

    def on_show(self) -> None:
        if not self._live_loaded and not self._live_loading:
            self.load_live()
        if self.tabs.currentIndex() == 1 and self._archive_key is None:
            self._load_archive()

    def _on_tab_changed(self, index: int) -> None:
        if index == 1:
            if self._archive_key is None:
                self._load_archive()

    def show_archive(self) -> None:
        self.tabs.setCurrentIndex(1)
        if self._archive_key is None:
            self._load_archive()

    def set_date(self, value: date) -> None:
        self.tabs.setCurrentIndex(0)
        self.date_edit.setDate(QDate(value.year, value.month, value.day))

    # -------------------------------------------------------------- live data

    def load_live(self, force: bool = False) -> None:
        if self._live_loading:
            return
        self._live_loading = True
        self.live_status_label.setText("Chargement...")
        self.live_banner.set_message("")
        date_str = self.date_edit.date().toString("yyyy-MM-dd")

        self.run_task(
            lambda _progress: self.service.fixtures_by_date(date_str, force=force),
            self._on_live_loaded,
            lambda code, message: self._on_live_error(code, message),
            busy_text=f"Recuperation des matchs du {date_str}...",
        )

    def _on_live_loaded(self, result: dict) -> None:
        self._live_loading = False
        self._live_loaded = True
        self._live_items = result.get("items") or []
        cached = result.get("cached")
        fetched = result.get("fetched_at")
        moment = datetime.fromtimestamp(fetched).strftime("%H:%M") if fetched else "—"
        source = result.get("source") or ("cache" if cached else "Sources gratuites")
        self.live_status_label.setText(
            f"{len(self._live_items)} match(s) • {source} • maj {moment}"
        )
        if result.get("warning"):
            self.live_banner.set_message(result["warning"], "warning")
        elif result.get("stale"):
            self.live_banner.set_message(
                "Donnees en cache legerement perimees : cliquez sur Actualiser.", "warning"
            )
        else:
            self.live_banner.set_message("")
        self._render_live()

    def _on_live_error(self, code: str, message: str) -> None:
        self._live_loading = False
        self.live_status_label.setText("Erreur")
        self.live_banner.set_message(message, "error")
        self._set_empty(
            self.live_empty_layout,
            "Impossible de charger les matchs",
            message,
            "Reessayer",
            lambda: self.load_live(force=True),
        )
        self.live_stack.setCurrentIndex(1)

    def _render_live(self) -> None:
        table = self.live_table
        table.setRowCount(0)
        league_id = self.live_league_combo.currentData()
        items = [
            fixture
            for fixture in self._live_items
            if league_id is None or int(fixture["league"].get("id") or -1) == int(league_id)
        ]
        items.sort(key=lambda item: item.get("date") or "")

        if not items:
            if self._live_items:
                title = "Aucun match pour cette competition"
                text = "Changez de ligue ou choisissez une autre date."
                action = None
                callback = None
            elif not self.service.tracked_leagues():
                title = "Aucune ligue suivie"
                text = "Ajoutez une competition depuis la page Ligues."
                action = "Gerer les ligues"
                callback = None
            else:
                title = "Aucun match dans vos ligues a cette date"
                text = (
                    "Les sources gratuites ne couvrent pas encore cette date. "
                    "Essayez une date proche ou explorez l'archive des saisons."
                )
                action = "Ouvrir l'archive"
                callback = self.show_archive
            self._set_empty(self.live_empty_layout, title, text, action, callback)
            self.live_stack.setCurrentIndex(1)
            return

        self.live_stack.setCurrentIndex(0)
        table.setRowCount(len(items))
        for row, fixture in enumerate(items):
            self._fill_live_row(table, row, fixture)
        fit_widget_column(table, 5)

    def _fill_live_row(self, table: QTableWidget, row: int, fixture: dict) -> None:
        time_item = QTableWidgetItem(_time_label(fixture.get("date")))
        time_item.setData(Qt.ItemDataRole.UserRole, fixture)
        time_item.setToolTip(fixture["league"].get("round") or "")
        table.setItem(row, 0, time_item)

        league_item = QTableWidgetItem(fixture["league"].get("name") or "—")
        league_item.setForeground(Qt.GlobalColor.gray)
        league_item.setToolTip(
            f"{fixture['league'].get('country') or ''} • {fixture['league'].get('round') or ''}"
        )
        table.setItem(row, 1, league_item)

        table.setCellWidget(row, 2, TeamBadge(fixture["home"]["name"], fixture["home"].get("logo")))
        score_item = QTableWidgetItem(score_text(fixture))
        score_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        score_item.setForeground(Qt.GlobalColor.white)
        font = score_item.font()
        font.setFamily("Cascadia Mono")
        font.setBold(True)
        score_item.setFont(font)
        table.setItem(row, 3, score_item)
        table.setCellWidget(row, 4, TeamBadge(fixture["away"]["name"], fixture["away"].get("logo")))

        badge = status_badge(fixture)
        wrapper = QWidget()
        wrap_layout = QHBoxLayout(wrapper)
        wrap_layout.setContentsMargins(4, 0, 4, 0)
        wrap_layout.addStretch()
        wrap_layout.addWidget(badge)
        wrap_layout.addStretch()
        table.setCellWidget(row, 5, wrapper)

        actions = QWidget()
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(2, 2, 2, 2)
        action_layout.setSpacing(5)
        analyze = SmallButton("Analyser", primary=True)
        analyze.clicked.connect(lambda _checked=False, f=fixture: self.open_analysis.emit(f))
        action_layout.addWidget(analyze)
        table.setCellWidget(row, 6, actions)

    def _on_live_double_click(self, row: int, _column: int) -> None:
        item = self.live_table.item(row, 0)
        if item:
            fixture = item.data(Qt.ItemDataRole.UserRole)
            if fixture:
                self.open_analysis.emit(fixture)

    # ----------------------------------------------------------- archive data

    def _archive_selection_changed(self) -> None:
        self._archive_key = None
        if self.tabs.currentIndex() == 1:
            self._load_archive()

    def _load_archive(self, force: bool = False) -> None:
        if self._archive_loading:
            return
        league_id = self.archive_league_combo.currentData()
        season = self.archive_season_combo.currentData()
        if league_id is None or season is None:
            self._set_empty(
                self.archive_empty_layout,
                "Aucune ligue selectionnee",
                "Ajoutez une ligue suivie depuis la page Ligues.",
            )
            self.archive_stack.setCurrentIndex(1)
            return
        key = (int(league_id), int(season))
        if self._archive_key == key and not force:
            self._render_archive()
            return
        self._archive_loading = True
        self.archive_status_label.setText("Chargement...")
        self.archive_banner.set_message("")
        self._set_empty(
            self.archive_empty_layout,
            "Chargement de l'archive...",
            "La premiere requete peut prendre quelques secondes (telechargement CSV).",
        )
        self.archive_stack.setCurrentIndex(1)

        self.run_task(
            lambda _progress: self.service.season_fixtures(league_id, season, force=force),
            lambda result: self._on_archive_loaded(result, key),
            self._on_archive_error,
            busy_text=f"Chargement de la saison {season}...",
        )

    def _on_archive_loaded(self, result: dict, key: tuple[int, int]) -> None:
        self._archive_loading = False
        self._archive_key = key
        self._archive_items = result.get("items") or []
        moment = (
            datetime.fromtimestamp(result.get("fetched_at")).strftime("%d/%m %H:%M")
            if result.get("fetched_at")
            else "—"
        )
        source = result.get("source") or (
            "cache" if result.get("cached") else "Sources gratuites"
        )
        self.archive_status_label.setText(
            f"{len(self._archive_items)} match(s) • {source} • maj {moment}"
        )
        if result.get("warning"):
            self.archive_banner.set_message(result["warning"], "warning")
        else:
            self.archive_banner.set_message("")
        self._render_archive()

    def _on_archive_error(self, code: str, message: str) -> None:
        self._archive_loading = False
        self.archive_status_label.setText("Erreur")
        self.archive_banner.set_message(message, "error")
        self._set_empty(
            self.archive_empty_layout,
            "Archive indisponible",
            message,
            "Reessayer",
            lambda: self._load_archive(force=True),
        )
        self.archive_stack.setCurrentIndex(1)

    def _render_archive(self) -> None:
        table = self.archive_table
        table.setRowCount(0)
        query = self.archive_search.text().strip().lower()
        items = [
            fixture
            for fixture in self._archive_items
            if not query
            or query in (fixture["home"].get("name") or "").lower()
            or query in (fixture["away"].get("name") or "").lower()
            or query in (fixture["league"].get("round") or "").lower()
        ]
        items.sort(key=lambda item: item.get("date") or "", reverse=True)
        if not items:
            if self._archive_items and query:
                self._set_empty(
                    self.archive_empty_layout,
                    "Aucun match trouve",
                    "Modifiez votre filtre ou effacez la recherche.",
                )
            else:
                self._set_empty(
                    self.archive_empty_layout,
                    "Aucun match dans cette saison",
                    "Essayez une autre saison ou verifiez les sources gratuites.",
                )
            self.archive_stack.setCurrentIndex(1)
            return
        self.archive_stack.setCurrentIndex(0)
        table.setRowCount(len(items))
        for row, fixture in enumerate(items):
            date_item = QTableWidgetItem(_time_label(fixture.get("date")))
            date_item.setData(Qt.ItemDataRole.UserRole, fixture)
            table.setItem(row, 0, date_item)
            round_text = _short_round(fixture["league"].get("round") or "")
            round_item = QTableWidgetItem(round_text)
            round_item.setForeground(Qt.GlobalColor.gray)
            round_item.setToolTip(fixture["league"].get("round") or "")
            table.setItem(row, 1, round_item)
            table.setCellWidget(row, 2, TeamBadge(fixture["home"]["name"], fixture["home"].get("logo")))
            score_item = QTableWidgetItem(score_text(fixture))
            score_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            font = score_item.font()
            font.setFamily("Cascadia Mono")
            font.setBold(True)
            score_item.setFont(font)
            table.setItem(row, 3, score_item)
            table.setCellWidget(row, 4, TeamBadge(fixture["away"]["name"], fixture["away"].get("logo")))

            actions = QWidget()
            action_layout = QHBoxLayout(actions)
            action_layout.setContentsMargins(2, 2, 2, 2)
            action_layout.setSpacing(5)
            analyze = SmallButton("Analyser", primary=True)
            analyze.clicked.connect(lambda _checked=False, f=fixture: self.open_analysis.emit(f))
            action_layout.addWidget(analyze)
            table.setCellWidget(row, 5, actions)

    def _on_archive_double_click(self, row: int, _column: int) -> None:
        item = self.archive_table.item(row, 0)
        if item:
            fixture = item.data(Qt.ItemDataRole.UserRole)
            if fixture:
                self.open_analysis.emit(fixture)

    # ------------------------------------------------------------------ utils

    def _refresh_league_combos(self) -> None:
        leagues = self.service.tracked_leagues()
        populate_leagues(self.live_league_combo, leagues, include_all=True)
        populate_leagues(self.archive_league_combo, leagues, include_all=False)
        if self.archive_league_combo.count() == 0:
            self.archive_status_label.setText("Aucune ligue")

    def refresh_leagues(self) -> None:
        self._refresh_league_combos()
        self._archive_key = None
        self._live_loaded = False
        if self.isVisible():
            if self.tabs.currentIndex() == 1:
                self._load_archive()
            else:
                self.load_live()

    def refresh_after_warmup(self) -> None:
        self._live_loaded = False
        self._archive_key = None
        if self.isVisible():
            if self.tabs.currentIndex() == 1:
                self._load_archive()
            else:
                self.load_live(force=False)

    def _set_empty(
        self,
        layout: QVBoxLayout,
        title: str,
        text: str = "",
        action_text: str | None = None,
        callback=None,
    ) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        empty = EmptyState(title, text, action_text)
        if empty.button and callback:
            empty.button.clicked.connect(callback)
        layout.addWidget(empty)
