"""Page Analyse : strategies utilisateur et cotes calculees."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...service import DataService
from ...theme import (
    ACCENT,
    AMBER,
    BLUE,
    MUTED,
    PURPLE,
    RED,
    TEXT,
    TEXT_SOFT,
)
from ..ai_dialog import AiAnalysisDialog
from ..base import BasePage
from ..common import configure_table, populate_leagues, populate_seasons
from ..widgets import (
    Badge,
    Banner,
    Card,
    EmptyState,
    FormBadges,
    LogoLabel,
    TeamBadge,
    make_mono_label,
    table_item,
)


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{float(value) * 100:.1f} %"


def _format_stat(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def _odd_text(value: object) -> str:
    if value is None:
        return "—"
    return f"{float(value):.2f}"


def latest_played_fixture(items: list[dict]) -> dict | None:
    """Renvoie le match termine le plus recent d'une liste deja triee."""
    return next(
        (
            fixture
            for fixture in items
            if (fixture.get("status") or {}).get("finished")
            and (fixture.get("goals") or {}).get("home") is not None
            and (fixture.get("goals") or {}).get("away") is not None
        ),
        None,
    )


class AnalysisPage(BasePage):

    def __init__(self, service: DataService, parent=None):
        super().__init__(service, parent)
        self.fixture: dict | None = None
        self.model: dict | None = None
        self._analysis_loading = False
        self._fixture_list_loading = False
        self._current_odds: list[dict] = []
        self._standings_loading = False
        self._standings_loaded = False
        self._standings_key: tuple[int, int] | None = None
        self._standings_groups: list[dict] = []
        self._standings_data: dict | None = None
        self._ai_standings_loading = False

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        content.setMinimumWidth(980)
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(0, 0, 8, 8)
        self.content_layout.setSpacing(14)
        scroll.setWidget(content)
        self.root.addWidget(scroll, 1)

        self.content_layout.addWidget(self._build_selector())
        self.content_layout.addWidget(self._build_match_card())
        self.analysis_banner = Banner()
        self.content_layout.addWidget(self.analysis_banner)
        self.content_layout.addWidget(self._build_data_card())

        odds_row = QHBoxLayout()
        odds_row.setSpacing(14)
        odds_row.addWidget(self._build_odds_card(), 1)
        odds_row.addWidget(self._build_market_card(), 1)
        self.content_layout.addLayout(odds_row)

        columns = QHBoxLayout()
        columns.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(14)
        right = QVBoxLayout()
        right.setSpacing(14)
        left.addWidget(self._build_standings_card())
        right.addWidget(self._build_team_card())
        columns.addLayout(left, 3)
        columns.addLayout(right, 2)
        self.content_layout.addLayout(columns)
        self.content_layout.addWidget(
            Banner(
                "Analyse informative : le modele ne remplace pas votre jugement et ne garantit "
                "aucun resultat. Comparer les cotes estimees (gauche) aux cotes de marche du CSV "
                "(droite). Jouez de facon responsable.",
                "info",
            )
        )
        self.content_layout.addStretch()

        self._refresh_league_combos()
        self._set_controls_enabled(False)

    # ------------------------------------------------------------------- UI

    def _build_selector(self) -> Card:
        card = Card(
            "Choisir un match",
            "Saisons gratuites configurees : aucune cle API requise",
        )
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("Ligue"))
        self.league_combo = QComboBox()
        self.league_combo.setMinimumWidth(160)
        self.league_combo.currentIndexChanged.connect(
            lambda _i: self._on_general_selection_changed()
        )
        row.addWidget(self.league_combo)

        row.addWidget(QLabel("Saison"))
        self.season_combo = QComboBox()
        populate_seasons(
            self.season_combo,
            self.service.config.seasons,
            self.service.settings().get("default_season"),
        )
        self.season_combo.currentIndexChanged.connect(
            lambda _i: self._on_general_selection_changed()
        )
        row.addWidget(self.season_combo)

        row.addWidget(QLabel("Match"))
        self.fixture_combo = QComboBox()
        self.fixture_combo.setMinimumWidth(320)
        self.fixture_combo.setMaxVisibleItems(18)
        self.fixture_combo.currentIndexChanged.connect(self._on_fixture_combo_changed)
        row.addWidget(self.fixture_combo, 1)

        self.load_button = QPushButton("Charger la saison")
        self.load_button.setMinimumWidth(self.load_button.sizeHint().width())
        self.load_button.clicked.connect(lambda: self._load_fixture_list(force=True))
        row.addWidget(self.load_button)
        card.add_layout(row)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addStretch()
        self.ai_button = QPushButton("Analyser avec l'IA")
        self.ai_button.setObjectName("primary")
        self.ai_button.setMinimumWidth(self.ai_button.sizeHint().width())
        self.ai_button.setToolTip(
            "Ouvrir une fenetre pour interroger Ollama avec l'analyse courante"
        )
        self.ai_button.clicked.connect(self._open_ai_dialog)
        self.ai_button.setEnabled(False)
        action_row.addWidget(self.ai_button)
        card.add_layout(action_row)

        hint = QLabel(
            "Pour un match recent, cliquez sur « Analyser » depuis la page Matchs. "
            "Le modele utilise les resultats de la saison choisie."
        )
        hint.setObjectName("small")
        hint.setWordWrap(True)
        card.add(hint)
        return card

    def _build_match_card(self) -> Card:
        card = Card()
        layout = QHBoxLayout()
        layout.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(3)

        self.match_league_label = QLabel("Aucun match selectionne")
        self.match_league_label.setObjectName("small")
        left.addWidget(self.match_league_label)

        teams_row = QHBoxLayout()
        teams_row.setSpacing(10)
        self.home_logo = LogoLabel("", 34)
        teams_row.addWidget(self.home_logo)
        self.home_name = QLabel("—")
        self.home_name.setStyleSheet(f"color: {TEXT}; font-size: 14pt; font-weight: 700;")
        teams_row.addWidget(self.home_name)
        self.vs_label = QLabel("vs")
        self.vs_label.setStyleSheet(f"color: {MUTED}; font-weight: 600;")
        teams_row.addWidget(self.vs_label)
        self.away_name = QLabel("—")
        self.away_name.setStyleSheet(f"color: {TEXT}; font-size: 14pt; font-weight: 700;")
        teams_row.addWidget(self.away_name)
        self.away_logo = LogoLabel("", 34)
        teams_row.addWidget(self.away_logo)
        teams_row.addStretch()
        left.addLayout(teams_row)

        self.match_meta_label = QLabel("Selectionnez un match dans la liste ci-dessus.")
        self.match_meta_label.setObjectName("small")
        left.addWidget(self.match_meta_label)

        layout.addLayout(left, 1)
        right = QVBoxLayout()
        right.setSpacing(8)
        self.match_status_holder = QHBoxLayout()
        self.match_status_holder.addStretch()
        right.addLayout(self.match_status_holder)
        layout.addLayout(right)
        card.add_layout(layout)
        return card

    # --------------------------------------------------------- donnees du match

    def _build_data_card(self) -> Card:
        card = Card(
            "Donnees du match",
            "Statistiques, xG et cotes de marche fournies par football-data.co.uk",
        )
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        header_home = QLabel("Domicile")
        header_home.setStyleSheet(f"color: {TEXT}; font-weight: 700;")
        header_away = QLabel("Exterieur")
        header_away.setStyleSheet(f"color: {TEXT}; font-weight: 700;")
        grid.addWidget(QLabel(""), 0, 0)
        grid.addWidget(header_home, 0, 1, Qt.AlignmentFlag.AlignRight)
        grid.addWidget(header_away, 0, 2, Qt.AlignmentFlag.AlignRight)

        self.data_values: dict[str, tuple[QLabel, QLabel]] = {}
        rows = [
            ("xg", "xG"),
            ("halftime", "Score mi-temps"),
            ("shots", "Tirs"),
            ("shots_on_target", "Tirs cadres"),
            ("corners", "Corners"),
            ("yellow_cards", "Cartons jaunes"),
            ("red_cards", "Cartons rouges"),
        ]
        for index, (key, label) in enumerate(rows, start=1):
            grid.addWidget(QLabel(label), index, 0)
            home_value = QLabel("—")
            away_value = QLabel("—")
            home_value.setAlignment(Qt.AlignmentFlag.AlignRight)
            away_value.setAlignment(Qt.AlignmentFlag.AlignRight)
            grid.addWidget(home_value, index, 1)
            grid.addWidget(away_value, index, 2)
            self.data_values[key] = (home_value, away_value)
        card.add_layout(grid)

        self.market_label = QLabel("Marche : —")
        self.market_label.setObjectName("small")
        self.market_label.setWordWrap(True)
        card.add(self.market_label)
        self.referee_label = QLabel("Arbitre : —")
        self.referee_label.setObjectName("small")
        self.referee_label.setWordWrap(True)
        card.add(self.referee_label)
        self.data_banner = Banner()
        card.add(self.data_banner)
        return card

    def _set_data_values(self, values: dict[str, dict | None]) -> None:
        for key, (home_label, away_label) in self.data_values.items():
            side = values.get(key) or {}
            home_label.setText(_format_stat(side.get("home")))
            away_label.setText(_format_stat(side.get("away")))

    def _reset_data(self) -> None:
        self._set_data_values({})
        self.market_label.setText("Marche : —")
        self.referee_label.setText("Arbitre : —")
        self.data_banner.set_message("")
        self._reset_market()

    def _render_data(self) -> None:
        context = (self.model or {}).get("context") or {}
        stats = dict(context.get("stats") or {})
        xg = context.get("xg") or {}
        stats["xg"] = xg
        self._set_data_values(stats)

        market = context.get("market") or {}
        if market:
            reference = market.get("reference") or "cloture"
            probs = market.get("probabilities") or {}
            closing = market.get("closing") or {}
            opening = market.get("opening") or {}
            asian = market.get("asian") or {}
            parts = [f"Reference : {reference}"]
            for key, label in (("home", "1"), ("draw", "N"), ("away", "2")):
                if closing.get(key) is not None:
                    part = f"{label} {closing[key]:.2f}"
                    if opening.get(key) is not None:
                        part += f" (ouv. {opening[key]:.2f})"
                    if probs.get(key) is not None:
                        part += f" · {_pct(probs[key])}"
                    parts.append(part)
            if asian.get("line") is not None:
                handicap = asian["line"]
                parts.append(
                    f"AH {handicap:+.2f}"
                    if handicap
                    else f"AH {handicap:.2f}"
                )
            self.market_label.setText("Marche : " + " · ".join(parts))
        else:
            self.market_label.setText("Marche : cotes non disponibles dans le CSV.")

        referee = context.get("referee") or {}
        if referee:
            details = []
            for key, label in (
                ("yellow_per_game", "cartons jaunes"),
                ("red_per_game", "cartons rouges"),
                ("fouls_per_game", "fautes"),
            ):
                if referee.get(key) is not None:
                    details.append(f"{referee[key]:.2f} {label}/match")
            self.referee_label.setText(
                f"Arbitre : {referee.get('name') or '—'} · "
                f"{referee.get('matches', 0)} matchs · " + ", ".join(details)
            )
        else:
            self.referee_label.setText("Arbitre : historique indisponible.")

        if not xg.get("home") and not xg.get("away"):
            self.data_banner.set_message(
                "xG non fournis pour cette saison : football-data.co.uk ne les "
                "publie que depuis la saison 2026-27.",
                "warning",
            )
        else:
            self.data_banner.set_message("")
        self._render_market()

    # -------------------------------------------------------------- classement

    def _build_standings_card(self) -> Card:
        card = Card("Classement", "Ligue et saison selectionnees en haut de page")
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        self.standings_group_label = QLabel("Groupe")
        toolbar.addWidget(self.standings_group_label)
        self.standings_group_combo = QComboBox()
        self.standings_group_combo.setMinimumWidth(120)
        self.standings_group_combo.currentIndexChanged.connect(
            lambda _i: self._render_standings()
        )
        toolbar.addWidget(self.standings_group_combo)
        self.standings_group_label.setVisible(False)
        self.standings_group_combo.setVisible(False)

        toolbar.addStretch()
        refresh = QPushButton("Actualiser")
        refresh.clicked.connect(self._refresh_standings)
        toolbar.addWidget(refresh)
        card.add_layout(toolbar)

        self.standings_status = QLabel("—")
        self.standings_status.setObjectName("small")
        card.add(self.standings_status)

        self.standings_banner = Banner()
        card.add(self.standings_banner)

        self.standings_stack = QStackedWidget()
        self.standings_table = QTableWidget()
        configure_table(
            self.standings_table,
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
            row_height=38,
        )
        self.standings_table.setMinimumHeight(320)
        self.standings_stack.addWidget(self.standings_table)

        self.standings_empty_holder = QWidget()
        self.standings_empty_layout = QVBoxLayout(self.standings_empty_holder)
        self.standings_empty_layout.setContentsMargins(0, 0, 0, 0)
        self.standings_stack.addWidget(self.standings_empty_holder)

        card.add(self.standings_stack, 1)
        return card

    def _standings_target_key(self) -> tuple[int, int] | None:
        """Ligue et saison courantes du choix general (en haut de page)."""
        league_id = self.league_combo.currentData()
        season = self.season_combo.currentData()
        if league_id is None or season is None:
            return None
        return (int(league_id), int(season))

    def _standings_selection_changed(self) -> None:
        self._standings_loaded = False
        self._standings_key = None
        self._standings_data = None
        if self.isVisible():
            self._load_standings()

    def _refresh_standings(self) -> None:
        self._standings_key = None
        self._load_standings()

    def _load_standings(self) -> None:
        if self._standings_loading:
            return
        key = self._standings_target_key()
        if key is None:
            self.standings_status.setText("Aucune ligue")
            self._show_standings_empty(
                "Aucune ligue selectionnee",
                "Choisissez une ligue et une saison en haut de page.",
            )
            return
        if key == self._standings_key and self._standings_loaded:
            return
        self._standings_loading = True
        self.standings_status.setText("Chargement...")
        self.standings_banner.set_message("")
        self._show_standings_empty(
            "Chargement du classement...",
            "La premiere requete peut prendre quelques secondes.",
        )
        league_id, season = key
        self.run_task(
            lambda _progress: self.service.standings(league_id, season),
            lambda result: self._on_standings_loaded(result, key),
            lambda code, message: self._on_standings_error(code, message, key),
            busy_text=f"Chargement du classement {season}...",
        )

    def _on_standings_loaded(self, result: dict, key: tuple[int, int]) -> None:
        self._standings_loading = False
        if key != self._standings_target_key():
            # Le choix general a change pendant le chargement : on recharge le bon classement.
            self._load_standings()
            return
        self._standings_loaded = True
        self._standings_key = key
        self._standings_data = result
        self._standings_groups = result.get("groups") or []
        moment = (
            datetime.fromtimestamp(result["fetched_at"]).strftime("%H:%M")
            if result.get("fetched_at")
            else "—"
        )
        source = result.get("source") or ("cache" if result.get("cached") else "Sources gratuites")
        total = sum(len(group.get("rows") or []) for group in self._standings_groups)
        league_name = (result.get("league") or {}).get("name") or "Classement"
        self.standings_status.setText(
            f"{league_name} • {total} equipe(s) • {source} • maj {moment}"
        )
        self.standings_banner.set_message(result.get("warning") or "", "warning")
        self._render_standings()

    def _on_standings_error(
        self, _code: str, message: str, key: tuple[int, int] | None = None
    ) -> None:
        self._standings_loading = False
        if key is not None and key != self._standings_target_key():
            self._load_standings()
            return
        self._standings_data = None
        self.standings_status.setText("Erreur")
        self.standings_banner.set_message(message, "error")
        self._show_standings_empty("Classement indisponible", message)

    def _render_standings(self) -> None:
        if not self._standings_groups:
            self._show_standings_empty("Aucun classement", "La source n'a renvoye aucune ligne.")
            return
        group_filter = (
            self.standings_group_combo.currentData()
            if self.standings_group_combo.isVisible()
            else None
        )
        rows: list[dict] = []
        for group in self._standings_groups:
            if group_filter and group.get("name") != group_filter:
                continue
            rows.extend(group.get("rows") or [])
        if not rows:
            self._show_standings_empty("Aucune equipe", "Essayez un autre groupe ou une autre saison.")
            return

        multiple = len(self._standings_groups) > 1
        self.standings_group_label.setVisible(multiple)
        self.standings_group_combo.setVisible(multiple)
        self.standings_group_combo.blockSignals(True)
        self.standings_group_combo.clear()
        if multiple:
            self.standings_group_combo.addItem("Tous les groupes", None)
            for group in self._standings_groups:
                self.standings_group_combo.addItem(group.get("name") or "Groupe", group.get("name"))
        self.standings_group_combo.blockSignals(False)

        self.standings_stack.setCurrentIndex(0)
        self.standings_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            rank_item = table_item(str(row.get("rank") or "—"), bold=True)
            rank_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.standings_table.setItem(row_index, 0, rank_item)

            team = row.get("team") or {}
            self.standings_table.setCellWidget(
                row_index, 1, TeamBadge(team.get("name") or "—", team.get("logo") or "")
            )
            self.standings_table.setItem(
                row_index, 2, table_item(row.get("group") or "—", color=MUTED)
            )

            stats = row.get("all") or {}
            goals = stats.get("goals") or {}
            values = (
                stats.get("played"),
                stats.get("win"),
                stats.get("draw"),
                stats.get("lose"),
                goals.get("for", "—"),
                goals.get("against", "—"),
            )
            for column, value in enumerate(values, start=3):
                self.standings_table.setItem(
                    row_index, column, table_item(value if value is not None else "—", align_right=True)
                )

            diff = row.get("goals_diff")
            diff_color = (
                ACCENT if isinstance(diff, int) and diff > 0 else RED if isinstance(diff, int) and diff < 0 else MUTED
            )
            self.standings_table.setItem(
                row_index,
                9,
                table_item(
                    f"{diff:+d}" if isinstance(diff, int) else "—",
                    align_right=True,
                    color=diff_color,
                ),
            )
            self.standings_table.setItem(
                row_index,
                10,
                table_item(
                    row.get("points") if row.get("points") is not None else "—",
                    align_right=True,
                    bold=True,
                ),
            )

            form_cell = QWidget()
            form_layout = QHBoxLayout(form_cell)
            form_layout.setContentsMargins(4, 0, 4, 0)
            form_layout.addWidget(FormBadges(row.get("form") or ""))
            form_layout.addStretch()
            self.standings_table.setCellWidget(row_index, 11, form_cell)
            self.standings_table.setItem(
                row_index, 12, self._standings_status_item(row.get("description") or "")
            )

        self.standings_table.setColumnHidden(2, not multiple)

    @staticmethod
    def _standings_status_item(description: str) -> QTableWidgetItem:
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

    def _show_standings_empty(
        self,
        title: str,
        text: str = "",
        action_text: str | None = None,
        callback=None,
    ) -> None:
        while self.standings_empty_layout.count():
            item = self.standings_empty_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        empty = EmptyState(title, text, action_text)
        if empty.button and callback:
            empty.button.clicked.connect(callback)
        self.standings_empty_layout.addWidget(empty)
        self.standings_stack.setCurrentIndex(1)

    def _build_odds_card(self) -> Card:
        card = Card("Cotes modele", "Cotes estimees par la strategie")
        self.odds_badge = Badge("—", "gray")
        card.add_header_widget(self.odds_badge)
        self.odds_banner = Banner()
        card.add(self.odds_banner)

        strategy_row = QHBoxLayout()
        strategy_row.setSpacing(6)
        strategy_row.addWidget(QLabel("Strategie"))
        self.strategy_combo = QComboBox()
        self.strategy_combo.setMinimumWidth(210)
        self.strategy_combo.currentIndexChanged.connect(self._on_strategy_changed)
        strategy_row.addWidget(self.strategy_combo, 1)
        reload_button = QPushButton("Recharger")
        reload_button.setToolTip("Relire les fichiers du dossier user_strategies")
        reload_button.clicked.connect(self._reload_strategies)
        strategy_row.addWidget(reload_button)
        card.add_layout(strategy_row)

        self.strategy_info = QLabel("")
        self.strategy_info.setObjectName("small")
        self.strategy_info.setWordWrap(True)
        card.add(self.strategy_info)
        self._populate_strategies()

        self.odds_empty = QLabel(
            "Selectionnez un match et lancez l'analyse pour afficher les cotes "
            "calculees par le modele."
        )
        self.odds_empty.setWordWrap(True)
        self.odds_empty.setObjectName("small")
        card.add(self.odds_empty)

        self.odds_table = QTableWidget()
        configure_table(
            self.odds_table,
            ["Marche", "Cote calculee", "Proba", "Cote juste", "Signal"],
            stretch_columns=[0],
            row_height=36,
        )
        self.odds_table.setMinimumHeight(270)
        self.odds_table.setVisible(False)
        card.add(self.odds_table)
        return card

    # --------------------------------------------------------- cotes du marche

    def _build_market_card(self) -> Card:
        card = Card(
            "Cotes marche",
            "1X2 et Over/Under reels du CSV (ouverture, cloture, bookmakers)",
        )
        self.market_banner = Banner()
        card.add(self.market_banner)

        self.market_empty = QLabel(
            "Selectionnez un match et lancez l'analyse pour afficher les cotes "
            "de marche 1X2 et Over/Under."
        )
        self.market_empty.setWordWrap(True)
        self.market_empty.setObjectName("small")
        card.add(self.market_empty)

        self.market_1x2_table = QTableWidget()
        configure_table(
            self.market_1x2_table,
            ["Source", "1", "N", "2"],
            stretch_columns=[0],
            row_height=32,
        )
        self.market_1x2_table.setMinimumHeight(190)
        self.market_1x2_table.setVisible(False)
        card.add(self.market_1x2_table)

        self.market_ou_table = QTableWidget()
        configure_table(
            self.market_ou_table,
            ["Source", "Over 2.5", "Under 2.5"],
            stretch_columns=[0],
            row_height=32,
        )
        self.market_ou_table.setMinimumHeight(150)
        self.market_ou_table.setVisible(False)
        card.add(self.market_ou_table)

        self.market_summary_label = QLabel("")
        self.market_summary_label.setObjectName("small")
        self.market_summary_label.setWordWrap(True)
        card.add(self.market_summary_label)
        return card

    def _reset_market(self) -> None:
        self.market_banner.set_message("")
        self.market_empty.setVisible(True)
        self.market_1x2_table.setVisible(False)
        self.market_1x2_table.setRowCount(0)
        self.market_ou_table.setVisible(False)
        self.market_ou_table.setRowCount(0)
        self.market_summary_label.setText("")

    def _render_market(self) -> None:
        market = ((self.model or {}).get("context") or {}).get("market") or {}
        if not market:
            self._reset_market()
            self.market_banner.set_message(
                "Cotes de marche indisponibles pour ce match dans le CSV.", "warning"
            )
            return

        sources = (
            ("opening", "Ouverture"),
            ("closing", "Cloture"),
            ("pinnacle", "Pinnacle"),
            ("consensus", "Consensus"),
            ("best", "Meilleur prix"),
        )
        one_two_x_rows = []
        for key, label in sources:
            odds = market.get(key) or {}
            if any(odds.get(side) is not None for side in ("home", "draw", "away")):
                one_two_x_rows.append(
                    (
                        label,
                        _odd_text(odds.get("home")),
                        _odd_text(odds.get("draw")),
                        _odd_text(odds.get("away")),
                    )
                )
        totals = market.get("totals") or {}
        totals_rows = []
        for key, label in sources:
            odds = totals.get(key) or {}
            if any(odds.get(side) is not None for side in ("over25", "under25")):
                totals_rows.append(
                    (
                        label,
                        _odd_text(odds.get("over25")),
                        _odd_text(odds.get("under25")),
                    )
                )

        self.market_empty.setVisible(False)
        self.market_1x2_table.setRowCount(len(one_two_x_rows))
        for row, values in enumerate(one_two_x_rows):
            for column, value in enumerate(values):
                self.market_1x2_table.setItem(
                    row, column, table_item(value, color=TEXT if column == 0 else MUTED)
                )
        self.market_1x2_table.setVisible(bool(one_two_x_rows))

        self.market_ou_table.setRowCount(len(totals_rows))
        for row, values in enumerate(totals_rows):
            for column, value in enumerate(values):
                self.market_ou_table.setItem(
                    row, column, table_item(value, color=TEXT if column == 0 else MUTED)
                )
        self.market_ou_table.setVisible(bool(totals_rows))

        reference = market.get("reference") or "cloture"
        probabilities = market.get("probabilities") or {}
        margin = market.get("margin")
        parts = [f"Reference : {reference}"]
        for key, label in (("home", "1"), ("draw", "N"), ("away", "2")):
            if probabilities.get(key) is not None:
                parts.append(f"{label} {_pct(probabilities[key])}")
        if margin is not None:
            parts.append(f"marge {_pct(margin)}")
        movement = market.get("movement") or {}
        if movement:
            moves = [
                f"{label} {float(value) * 100:+.1f} %"
                for key, label in (("home", "1"), ("draw", "N"), ("away", "2"))
                if (value := movement.get(key)) is not None
            ]
            if moves:
                parts.append("mouvement Ouverture -> Cloture : " + ", ".join(moves))
        self.market_summary_label.setText(" · ".join(parts))
        self.market_banner.set_message(
            "Cotes observees sur le marche, distinctes des cotes estimees par les strategies.",
            "info",
        )

    # ------------------------------------------------------------- strategies

    def _populate_strategies(self) -> None:
        selected = self.service.value_strategy_id()
        self.strategy_combo.blockSignals(True)
        self.strategy_combo.clear()
        for strategy in self.service.strategies.strategies:
            self.strategy_combo.addItem(strategy.name, strategy.id)
        index = self.strategy_combo.findData(selected)
        if index >= 0:
            self.strategy_combo.setCurrentIndex(index)
        self.strategy_combo.setEnabled(self.strategy_combo.count() > 0)
        self.strategy_combo.blockSignals(False)
        if index < 0 and self.strategy_combo.count() > 0:
            self.service.set_value_strategy(self.strategy_combo.currentData())
        self._update_strategy_info()

    def _update_strategy_info(self) -> None:
        strategy = self.service.strategies.get(self.service.value_strategy_id())
        if strategy is None:
            self.strategy_info.setText("Aucune strategie trouvee dans le dossier user_strategies/.")
            self.strategy_info.setStyleSheet(f"color: {AMBER};")
            return
        text = strategy.description or strategy.name
        errors = self.service.strategies.errors
        if errors:
            text += f" • {len(errors)} strategie(s) ignoree(s)"
        self.strategy_info.setText(text)
        self.strategy_info.setStyleSheet(
            f"color: {AMBER};" if errors else f"color: {TEXT_SOFT};"
        )

    def _on_strategy_changed(self, _index: int) -> None:
        strategy_id = self.strategy_combo.currentData()
        if not strategy_id:
            return
        self.service.set_value_strategy(strategy_id)
        self._update_strategy_info()
        # La strategie peut fournir son propre modele de probabilites.
        if self.fixture is not None:
            self._run_analysis()
        else:
            self._recompute_odds()

    def _reload_strategies(self) -> None:
        self.service.reload_strategies()
        self._populate_strategies()
        self._recompute_odds()
        self.toast.emit("Strategies rechargees depuis user_strategies/.")

    def _recompute_odds(self) -> None:
        if not self.model:
            return
        strategy = self.service.strategies.get(self.service.value_strategy_id())
        if strategy is None:
            self.odds_banner.set_message(
                "Aucune strategie disponible dans le dossier user_strategies/.", "warning"
            )
            self._render_odds([])
            return
        try:
            rows = strategy.run(self.model["probabilities"])
        except Exception as exc:  # une strategie utilisateur ne doit pas casser l'UI
            self.odds_banner.set_message(
                f"Strategie « {strategy.name} » en erreur : {exc}", "error"
            )
            rows = []
        else:
            self.odds_banner.set_message(
                f"Cotes estimees avec la strategie « {strategy.name} ». "
                "Ce ne sont pas des cotes de bookmaker.",
                "info",
            )
        self._current_odds = rows
        self._render_odds(rows)

    def _reset_odds(self) -> None:
        self._current_odds = []
        self.odds_banner.set_message("")
        self.odds_table.setVisible(False)
        self.odds_table.setRowCount(0)
        self.odds_empty.setVisible(True)
        self.odds_badge.setText("—")
        self.odds_badge.set_kind("gray")

    def _open_ai_dialog(self) -> None:
        if not self.model or not self.fixture:
            self.analysis_banner.set_message(
                "Lancez d'abord l'analyse du match avant d'utiliser l'IA.", "warning"
            )
            return

        selected_id = self.service.value_strategy_id()
        strategy = self.service.strategies.get(selected_id)
        selected_strategy: dict = {}
        if strategy is not None:
            try:
                rows = strategy.run(self.model["probabilities"])
            except Exception:  # une strategie utilisateur ne doit pas bloquer l'IA
                rows = []
            selected_strategy = {
                "id": strategy.id,
                "name": strategy.name,
                "description": strategy.description,
                "rows": rows,
            }

        payload = {
            "fixture": self.fixture,
            "model": self.model,
            "context": (self.model or {}).get("context") or {},
            "selected_strategy": selected_id,
            "strategie": selected_strategy,
        }
        standings = self._ai_standings_for_fixture(self.fixture)
        if standings is not None:
            self._show_ai_dialog(payload, standings)
            return

        key = self._fixture_standings_key(self.fixture)
        if key is None:
            self.analysis_banner.set_message(
                "Saison du match inconnue : le classement ne peut pas etre joint a l'analyse IA.",
                "warning",
            )
            self._show_ai_dialog(payload)
            return
        if self._ai_standings_loading:
            return
        self._ai_standings_loading = True
        self.run_task(
            lambda _progress: self.service.standings(key[0], key[1]),
            lambda result: self._show_ai_dialog(payload, result),
            lambda _code, message: self._show_ai_dialog(payload, warning=message),
            busy_text="Chargement du classement pour l'analyse IA...",
        )

    @staticmethod
    def _fixture_standings_key(fixture: dict) -> tuple[int, int] | None:
        league = fixture.get("league") or {}
        try:
            return int(league["id"]), int(league["season"])
        except (KeyError, TypeError, ValueError):
            return None

    def _ai_standings_for_fixture(self, fixture: dict) -> dict | None:
        """Ne joint que le classement de la ligue et de la saison du match analyse."""
        data = self._standings_data
        key = self._fixture_standings_key(fixture)
        if not data or key is None:
            return None
        source = data.get("league") or {}
        try:
            source_key = (int(source["id"]), int(source["season"]))
        except (KeyError, TypeError, ValueError):
            return None
        return data if source_key == key else None

    def _show_ai_dialog(
        self, payload: dict, standings: dict | None = None, warning: str | None = None
    ) -> None:
        self._ai_standings_loading = False
        if standings is not None:
            payload["standings"] = standings
        elif warning:
            self.analysis_banner.set_message(
                f"Classement indisponible pour l'analyse IA : {warning}", "warning"
            )
        dialog = AiAnalysisDialog(self.service, payload, self)
        dialog.exec()

    def _build_team_card(self) -> Card:
        card = Card("Forme & statistiques", "Splits domicile / exterieur de la saison")
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(7)
        self.team_home_header = QLabel("Domicile")
        self.team_home_header.setStyleSheet(f"color: {TEXT}; font-weight: 700;")
        self.team_away_header = QLabel("Exterieur")
        self.team_away_header.setStyleSheet(f"color: {TEXT}; font-weight: 700;")
        grid.addWidget(QLabel(""), 0, 0)
        grid.addWidget(self.team_home_header, 0, 1, Qt.AlignmentFlag.AlignRight)
        grid.addWidget(self.team_away_header, 0, 2, Qt.AlignmentFlag.AlignRight)

        self.team_values: dict[str, tuple[QLabel, QLabel]] = {}
        rows = [
            ("played", "Matchs joues"),
            ("goals_for", "Buts marques"),
            ("goals_against", "Buts encaisses"),
            ("venue", "Domicile / exterieur"),
            ("attack", "Force offensive"),
            ("defense", "Force defensive"),
        ]
        for index, (key, label) in enumerate(rows, start=1):
            label_widget = QLabel(label)
            label_widget.setStyleSheet(f"color: {MUTED};")
            grid.addWidget(label_widget, index, 0)
            home_value = QLabel("—")
            home_value.setAlignment(Qt.AlignmentFlag.AlignRight)
            home_value.setStyleSheet(f"color: {TEXT_SOFT}; font-weight: 600;")
            away_value = QLabel("—")
            away_value.setAlignment(Qt.AlignmentFlag.AlignRight)
            away_value.setStyleSheet(f"color: {TEXT_SOFT}; font-weight: 600;")
            grid.addWidget(home_value, index, 1)
            grid.addWidget(away_value, index, 2)
            self.team_values[key] = (home_value, away_value)

        form_row = len(rows) + 1
        grid.addWidget(QLabel("Forme (5 derniers)"), form_row, 0)
        self.home_form = FormBadges("")
        self.away_form = FormBadges("")
        grid.addWidget(self.home_form, form_row, 1)
        grid.addWidget(self.away_form, form_row, 2)
        card.add_layout(grid)

        self.team_banner = Banner()
        card.add(self.team_banner)
        return card

    # ------------------------------------------------------------- navigation

    def on_show(self) -> None:
        if not self.fixture and self.league_combo.count() > 0 and self.fixture_combo.count() == 0:
            self._load_fixture_list()
        if not self._standings_loaded and not self._standings_loading:
            self._load_standings()

    def _on_general_selection_changed(self) -> None:
        """Le choix general (ligue/saison) pilote les matchs et le classement."""
        self._load_fixture_list()
        self._standings_selection_changed()

    def refresh_league_combos(self) -> None:
        self._refresh_league_combos()
        self._standings_selection_changed()
        if self.isVisible() and self.fixture is None and self.fixture_combo.count() == 0:
            self._load_fixture_list()

    def refresh_after_warmup(self) -> None:
        if self.fixture is not None and not self._analysis_loading:
            self._run_analysis()
        self._standings_loaded = False
        self._standings_key = None
        self._refresh_standings()

    def _refresh_league_combos(self) -> None:
        leagues = self.service.tracked_leagues()
        populate_leagues(self.league_combo, leagues, include_all=False)
        if self.league_combo.count() == 0:
            self.fixture_combo.clear()

    def load_fixture(self, fixture: dict) -> None:
        """Appele depuis la page Matchs ou le tableau de bord."""
        self.fixture = fixture
        self.model = None
        self.analysis_banner.set_message("")
        self._reset_odds()
        self._reset_data()

        league = fixture.get("league", {})
        league_id = league.get("id")
        # Selectionne la ligue si elle est suivie, sinon ajoute une entree temporaire.
        index = self.league_combo.findData(int(league_id)) if league_id is not None else -1
        if index < 0 and league_id is not None:
            self.league_combo.blockSignals(True)
            self.league_combo.addItem(league.get("name") or f"Ligue {league_id}", int(league_id))
            self.league_combo.setCurrentIndex(self.league_combo.count() - 1)
            self.league_combo.blockSignals(False)
        elif index >= 0:
            self.league_combo.blockSignals(True)
            self.league_combo.setCurrentIndex(index)
            self.league_combo.blockSignals(False)

        season = self.service.settings().get("default_season") or self.service.config.default_season
        fixture_season = league.get("season")
        if fixture_season in self.service.config.seasons:
            season = int(fixture_season)
        season_index = self.season_combo.findData(int(season))
        if season_index >= 0:
            self.season_combo.blockSignals(True)
            self.season_combo.setCurrentIndex(season_index)
            self.season_combo.blockSignals(False)

        self._render_header()
        self._set_controls_enabled(True)
        self._standings_selection_changed()
        self._run_analysis()

    # -------------------------------------------------------------- saison

    def _load_fixture_list(self, force: bool = False) -> None:
        if self._fixture_list_loading:
            return
        league_id = self.league_combo.currentData()
        season = self.season_combo.currentData()
        if league_id is None or season is None:
            return
        self._fixture_list_loading = True
        self.load_button.setEnabled(False)
        self.fixture_combo.blockSignals(True)
        self.fixture_combo.clear()
        self.fixture_combo.addItem("Chargement de la saison...", None)
        self.fixture_combo.blockSignals(False)

        self.run_task(
            lambda _progress: self.service.season_fixtures(int(league_id), int(season), force=force),
            self._on_fixture_list_loaded,
            self._on_fixture_list_error,
            busy_text=f"Chargement de la saison {season}...",
        )

    def _on_fixture_list_loaded(self, result: dict) -> None:
        self._fixture_list_loading = False
        self.load_button.setEnabled(True)
        items = result.get("items") or []
        self.fixture_combo.blockSignals(True)
        self.fixture_combo.clear()
        if not items:
            self.fixture_combo.addItem("Aucun match disponible", None)
            self.fixture_combo.blockSignals(False)
            self.analysis_banner.set_message(
                "Aucun match pour cette saison. Essayez une autre saison ou verifiez "
                "les sources gratuites.",
                "warning",
            )
            return
        ordered = sorted(items, key=lambda item: item.get("date") or "", reverse=True)
        latest_played = latest_played_fixture(ordered)
        selected_index = 0
        for index, fixture in enumerate(ordered):
            goals = fixture.get("goals") or {}
            score = ""
            if (fixture.get("status") or {}).get("finished") and goals.get("home") is not None:
                score = f"  [{goals.get('home')}-{goals.get('away')}]"
            label = (
                f"{self.service.format_kickoff(fixture.get('date'))}  •  "
                f"{fixture['home']['name']} - {fixture['away']['name']}{score}"
            )
            self.fixture_combo.addItem(label, fixture)
            if fixture is latest_played:
                selected_index = index
        self.fixture_combo.blockSignals(False)
        if result.get("warning"):
            self.analysis_banner.set_message(result["warning"], "warning")
        elif latest_played:
            self.analysis_banner.set_message(
                "Dernier match joue selectionne automatiquement.", "info"
            )
        else:
            self.analysis_banner.set_message("")
        self.fixture_combo.setCurrentIndex(selected_index)
        self._on_fixture_combo_changed(selected_index)

    def _on_fixture_list_error(self, code: str, message: str) -> None:
        self._fixture_list_loading = False
        self.load_button.setEnabled(True)
        self.fixture_combo.blockSignals(True)
        self.fixture_combo.clear()
        self.fixture_combo.addItem("Erreur de chargement", None)
        self.fixture_combo.blockSignals(False)
        self.analysis_banner.set_message(message, "error")
        self.show_source_error(code, message)

    def _on_fixture_combo_changed(self, _index: int) -> None:
        fixture = self.fixture_combo.currentData()
        if not isinstance(fixture, dict):
            return
        self.fixture = fixture
        self.model = None
        self._reset_odds()
        self._reset_data()
        self._render_header()
        self._set_controls_enabled(True)
        self._run_analysis()

    # -------------------------------------------------------------- analyse

    def _run_analysis(self, force: bool = False) -> None:
        if self.fixture is None or self._analysis_loading:
            return
        self._analysis_loading = True
        self.analysis_banner.set_message("Calcul du modele...", "info")
        season = int(self.season_combo.currentData() or self.service.config.default_season)
        fixture = self.fixture

        self.run_task(
            lambda _progress: self.service.analyze_fixture(fixture, season, force=force),
            self._on_analysis_loaded,
            self._on_analysis_error,
            busy_text="Calcul du modele...",
        )

    def _on_analysis_loaded(self, model: dict) -> None:
        self._analysis_loading = False
        self.model = model
        warning = (model.get("_meta") or {}).get("warning")
        self.analysis_banner.set_message(warning or "", "warning" if warning else "info")
        self._render_teams()
        self._render_data()
        self._recompute_odds()

    def _on_analysis_error(self, code: str, message: str) -> None:
        self._analysis_loading = False
        self.analysis_banner.set_message(message, "error")
        self.model = None
        self._reset_odds()
        self._reset_data()

    def _render_teams(self) -> None:
        if not self.model:
            return
        home = self.model["home"]
        away = self.model["away"]
        self.team_home_header.setText(home.get("name") or "Domicile")
        self.team_away_header.setText(away.get("name") or "Exterieur")
        self.team_values["played"][0].setText(str(home.get("played", 0)))
        self.team_values["played"][1].setText(str(away.get("played", 0)))
        self.team_values["goals_for"][0].setText(str(home.get("goals_for", 0)))
        self.team_values["goals_for"][1].setText(str(away.get("goals_for", 0)))
        self.team_values["goals_against"][0].setText(str(home.get("goals_against", 0)))
        self.team_values["goals_against"][1].setText(str(away.get("goals_against", 0)))
        self.team_values["venue"][0].setText(
            f"{home.get('home_played', 0)} dom. / {home.get('away_played', 0)} ext."
        )
        self.team_values["venue"][1].setText(
            f"{away.get('home_played', 0)} dom. / {away.get('away_played', 0)} ext."
        )
        self.team_values["attack"][0].setText(f"{home.get('attack_home', 1.0):.2f}")
        self.team_values["attack"][1].setText(f"{away.get('attack_away', 1.0):.2f}")
        self.team_values["defense"][0].setText(f"{home.get('defense_home', 1.0):.2f}")
        self.team_values["defense"][1].setText(f"{away.get('defense_away', 1.0):.2f}")
        self.home_form.set_form("".join(home.get("form") or []))
        self.away_form.set_form("".join(away.get("form") or []))
        if not home.get("known") or not away.get("known"):
            self.team_banner.set_message(
                "Une equipe est absente de la saison de reference : ses forces sont neutres.",
                "warning",
            )
        else:
            self.team_banner.set_message("")

    # ---------------------------------------------------------------- cotes

    def _render_odds(self, rows: list[dict]) -> None:
        self.odds_table.setRowCount(0)
        if not rows:
            self.odds_empty.setVisible(True)
            self.odds_table.setVisible(False)
            self.odds_badge.setText("—")
            self.odds_badge.set_kind("gray")
            return
        self.odds_empty.setVisible(False)
        self.odds_table.setVisible(True)
        self.odds_badge.setText(f"{len(rows)} COTES")
        self.odds_badge.set_kind("blue")
        self.odds_table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            highlight = bool(item.get("highlight"))
            color = ACCENT if highlight else TEXT
            self.odds_table.setItem(
                row, 0, table_item(str(item["label"]), bold=highlight, color=color)
            )
            self.odds_table.setItem(
                row, 1, table_item(f"{item['odd']:.2f}", align_right=True, color=color)
            )
            self.odds_table.setItem(row, 2, table_item(_pct(item["prob"]), align_right=True))
            fair = item.get("fair_odd")
            self.odds_table.setItem(
                row,
                3,
                table_item(
                    f"{fair:.2f}" if fair is not None else "—",
                    align_right=True,
                    color=MUTED,
                ),
            )
            signal = str(item.get("signal") or "—")
            self.odds_table.setItem(
                row, 4, table_item(signal, color=ACCENT if highlight else TEXT_SOFT)
            )

    # -------------------------------------------------------------- entete

    def _render_header(self) -> None:
        fixture = self.fixture
        if not fixture:
            return
        league = fixture["league"]
        source = fixture.get("source") or ""
        source_part = f" • {source}" if source else ""
        self.match_league_label.setText(
            f"{league.get('name')} • {league.get('round') or ''} • "
            f"{self.service.format_kickoff(fixture.get('date'))}{source_part}"
        )
        self.home_name.setText(fixture["home"].get("name") or "—")
        self.away_name.setText(fixture["away"].get("name") or "—")
        goals = fixture.get("goals") or {}
        home_goals = goals.get("home")
        away_goals = goals.get("away")
        if home_goals is not None and away_goals is not None:
            self.vs_label.setText(f"{home_goals} - {away_goals}")
            self.vs_label.setStyleSheet(
                f"color: {ACCENT}; font-size: 15pt; font-weight: 700;"
            )
        else:
            self.vs_label.setText("vs")
            self.vs_label.setStyleSheet(f"color: {MUTED}; font-weight: 600;")
        self.home_logo.setVisible(False)
        self.away_logo.setVisible(False)
        # Les logos sont recharges en recreant des labels pour eviter les restes.
        self._set_logo(self.home_logo, fixture["home"].get("logo"))
        self._set_logo(self.away_logo, fixture["away"].get("logo"))
        venue = fixture.get("venue") or {}
        meta_parts = [part for part in [venue.get("name"), venue.get("city")] if part]
        meta = " • ".join(meta_parts) if meta_parts else "Stade non renseigne"
        if fixture.get("referee"):
            meta += f" • Arbitre : {fixture['referee']}"
        self.match_meta_label.setText(meta)

        while self.match_status_holder.count():
            item = self.match_status_holder.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        from ..common import status_badge

        badge = status_badge(fixture)
        self.match_status_holder.addWidget(badge)
        self.match_status_holder.addStretch()

    def _set_logo(self, label: LogoLabel, url: str | None) -> None:
        from ..widgets import load_image

        label.clear()
        label.setVisible(bool(url))
        if url:
            load_image(label, url, 34)

    def _set_controls_enabled(self, enabled: bool) -> None:
        self.ai_button.setEnabled(enabled)
        if not enabled:
            self.analysis_banner.set_message(
                "Selectionnez un match dans la liste ou cliquez sur Analyser depuis la page Matchs.",
                "info",
            )
