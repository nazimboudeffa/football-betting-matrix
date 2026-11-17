"""Fenetre principale de Betting Matrix."""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import QSettings, QTimer, Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QProgressBar,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import APP_NAME, APP_VERSION
from ..service import DataService
from ..theme import ACCENT, AMBER, MUTED, TEXT_SOFT
from .pages.analysis import AnalysisPage
from .pages.dashboard import DashboardPage
from .pages.leagues import LeaguesPage
from .pages.matches import MatchesPage
from .pages.settings import SettingsPage

WEEKDAYS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
MONTHS = [
    "janv.",
    "fevr.",
    "mars",
    "avr.",
    "mai",
    "juin",
    "juil.",
    "aout",
    "sept.",
    "oct.",
    "nov.",
    "dec.",
]

PAGES = [
    ("dashboard", "Tableau de bord", "Vue d'ensemble des matchs, des sources et du cache"),
    ("matches", "Matchs", "Matchs, navigation par date et archive des saisons"),
    ("analysis", "Analyse", "Classement et cotes calculees par strategie"),
    ("leagues", "Ligues", "Gerez les competitions suivies"),
    ("settings", "Reglages", "Configuration, sources gratuites et cache"),
]


def _chip_style(color: str, background: str) -> str:
    return (
        f"color: {color}; background: {background}; border: 1px solid {color}40; "
        "border-radius: 8px; padding: 4px 10px; font-size: 8.5pt; font-weight: 600;"
    )


class MainWindow(QMainWindow):
    def __init__(self, service: DataService):
        super().__init__()
        self.service = service
        self._busy: dict[str, str] = {}
        self._settings = QSettings("BettingMatrix", "BettingMatrix")

        self.setWindowTitle(f"{APP_NAME} • analyse football")
        self.setMinimumSize(1220, 800)
        self.resize(1400, 900)

        root = QWidget()
        root.setObjectName("appRoot")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        root_layout.addWidget(self._build_sidebar())

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._build_header())

        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right_layout.addWidget(self.stack, 1)
        root_layout.addWidget(right, 1)

        self.pages: dict[str, QWidget] = {}
        self.page_indices: dict[str, int] = {}
        self._build_pages()
        self._connect_signals()
        self._build_statusbar()

        self.nav.setCurrentRow(0)
        self._refresh_global_stats()
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self._refresh_global_stats)
        self._timer.start()

        geometry = self._settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self._refresh_date_chip()

    # ------------------------------------------------------------------ UI

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(238)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(12)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel("▦")
        logo.setFixedSize(38, 38)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet(
            f"color: {ACCENT}; background: rgba(40,209,124,0.12); "
            "border: 1px solid rgba(40,209,124,0.35); border-radius: 10px; "
            "font-size: 18pt; font-weight: 700;"
        )
        brand.addWidget(logo)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        title = QLabel("Betting Matrix")
        title.setObjectName("brandTitle")
        brand_text.addWidget(title)
        subtitle = QLabel("FOOTBALL ANALYTICS")
        subtitle.setObjectName("brandSub")
        brand_text.addWidget(subtitle)
        brand.addLayout(brand_text)
        brand.addStretch()
        layout.addLayout(brand)

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)

        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for key, label, _subtitle in PAGES:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.nav.addItem(item)
        self.nav.currentRowChanged.connect(self._on_nav_changed)
        layout.addWidget(self.nav, 1)

        sources_card = QFrame()
        sources_card.setObjectName("innerCard")
        sources_layout = QVBoxLayout(sources_card)
        sources_layout.setContentsMargins(12, 10, 12, 10)
        sources_layout.setSpacing(4)
        sources_title = QLabel("SOURCES GRATUITES")
        sources_title.setStyleSheet(
            f"color: {MUTED}; font-size: 7.5pt; font-weight: 700; letter-spacing: 1px;"
        )
        sources_layout.addWidget(sources_title)
        sources_text = QLabel("6 competitions\nCache en memoire")
        sources_text.setStyleSheet(f"color: {TEXT_SOFT}; font-size: 8pt;")
        sources_layout.addWidget(sources_text)
        layout.addWidget(sources_card)

        version = QLabel(f"v{APP_VERSION} • sans base de donnees")
        version.setStyleSheet(f"color: {MUTED}; font-size: 8pt;")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)
        return sidebar

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("headerBar")
        header.setFixedHeight(80)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(24, 12, 24, 12)
        layout.setSpacing(12)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.page_title = QLabel("Tableau de bord")
        self.page_title.setObjectName("pageTitle")
        titles.addWidget(self.page_title)
        self.page_subtitle = QLabel("")
        self.page_subtitle.setObjectName("pageSubtitle")
        titles.addWidget(self.page_subtitle)
        layout.addLayout(titles)
        layout.addStretch()

        self.busy_label = QLabel("")
        self.busy_label.setStyleSheet(f"color: {AMBER}; font-size: 8.5pt;")
        self.busy_label.setVisible(False)
        layout.addWidget(self.busy_label)
        self.busy_bar = QProgressBar()
        self.busy_bar.setRange(0, 0)
        self.busy_bar.setTextVisible(False)
        self.busy_bar.setFixedSize(90, 4)
        self.busy_bar.setVisible(False)
        layout.addWidget(self.busy_bar)

        self.date_chip = QLabel("—")
        self.date_chip.setStyleSheet(_chip_style(TEXT_SOFT, "rgba(130,149,176,0.09)"))
        layout.addWidget(self.date_chip)
        return header

    def _build_pages(self) -> None:
        self.dashboard = DashboardPage(self.service)
        self.matches = MatchesPage(self.service)
        self.analysis = AnalysisPage(self.service)
        self.leagues = LeaguesPage(self.service)
        self.settings = SettingsPage(self.service)
        self.pages = {
            "dashboard": self.dashboard,
            "matches": self.matches,
            "analysis": self.analysis,
            "leagues": self.leagues,
            "settings": self.settings,
        }
        for index, (key, _label, _subtitle) in enumerate(PAGES):
            self.stack.addWidget(self.pages[key])
            self.page_indices[key] = index

    def _build_statusbar(self) -> None:
        status = self.statusBar()
        status.showMessage("Pret. Sources gratuites et cache en memoire.")
        self.status_cache = QLabel("Cache : —")
        self.status_cache.setStyleSheet(f"color: {MUTED}; font-size: 8.5pt;")
        status.addPermanentWidget(self.status_cache)
        self.status_source = QLabel("Reglages JSON • cache memoire")
        self.status_source.setStyleSheet(f"color: {MUTED}; font-size: 8.5pt;")
        status.addPermanentWidget(self.status_source)

    # ------------------------------------------------------------- signaux

    def _connect_signals(self) -> None:
        self.dashboard.navigate.connect(self._handle_navigate)
        self.dashboard.open_analysis.connect(self.open_analysis)
        self.matches.open_analysis.connect(self.open_analysis)
        self.leagues.leagues_changed.connect(self._on_leagues_changed)
        self.settings.settings_changed.connect(self._on_settings_changed)
        self.settings.data_warmed.connect(self._on_data_warmed)

        for key, page in self.pages.items():
            page.busy_changed.connect(
                lambda busy, message, page_key=key: self._on_busy(page_key, busy, message)
            )
            page.toast.connect(lambda message: self.statusBar().showMessage(message, 9000))

    # ------------------------------------------------------------ navigation

    def _on_nav_changed(self, row: int) -> None:
        if row < 0 or row >= len(PAGES):
            return
        key, title, subtitle = PAGES[row]
        self.stack.setCurrentIndex(row)
        self.page_title.setText(title)
        self.page_subtitle.setText(subtitle)
        page = self.pages[key]
        page.on_show()
        self._refresh_global_stats()
        self.statusBar().showMessage(f"{title} • pret", 3500)

    def _go(self, key: str) -> None:
        index = self.page_indices.get(key)
        if index is None:
            return
        if self.nav.currentRow() == index:
            self.pages[key].on_show()
            return
        self.nav.setCurrentRow(index)

    def _handle_navigate(self, key: str, payload: object) -> None:
        if key == "matches_archive":
            self._go("matches")
            self.matches.show_archive()
            return
        self._go(key)
        if key == "matches" and isinstance(payload, date):
            self.matches.set_date(payload)

    def open_analysis(self, fixture: dict) -> None:
        if not fixture:
            return
        self.analysis.load_fixture(fixture)
        self._go("analysis")

    # ----------------------------------------------------- evenements metier

    def _on_leagues_changed(self) -> None:
        self.matches.refresh_leagues()
        self.analysis.refresh_league_combos()
        self.dashboard.refresh_after_leagues()

    def _on_settings_changed(self) -> None:
        self.dashboard.refresh_stats()
        self._refresh_global_stats()

    def _on_data_warmed(self) -> None:
        self.matches.refresh_after_warmup()
        self.analysis.refresh_after_warmup()
        self.dashboard.refresh_after_leagues()

    # -------------------------------------------------------------- etats UI

    def _on_busy(self, page_key: str, busy: bool, message: str) -> None:
        if busy:
            self._busy[page_key] = message or "Chargement..."
        else:
            self._busy.pop(page_key, None)
        if self._busy:
            self.busy_label.setText(next(reversed(self._busy.values())))
            self.busy_label.setVisible(True)
            self.busy_bar.setVisible(True)
        else:
            self.busy_label.setVisible(False)
            self.busy_bar.setVisible(False)

    def _refresh_global_stats(self) -> None:
        cache = self.service.cache_stats()
        self.status_cache.setText(
            f"Cache : {cache['entries']} entree(s) • {cache['bytes'] / 1024:.0f} Ko"
        )

    def _refresh_date_chip(self) -> None:
        today = date.today()
        self.date_chip.setText(
            f"{WEEKDAYS[today.weekday()]} {today.day} {MONTHS[today.month - 1]} {today.year}"
        )

    # --------------------------------------------------------------- fermeture

    def closeEvent(self, event) -> None:  # noqa: N802 (API Qt)
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.sync()
        super().closeEvent(event)
