"""Page Analyse : modele Poisson, value bets et cotes des sources gratuites."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
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

from ...analysis import MARKET_LABELS, value_bets
from ...service import DataService
from ...theme import (
    ACCENT,
    AMBER,
    BLUE,
    BORDER,
    MUTED,
    PURPLE,
    RED,
    TEXT,
    TEXT_SOFT,
)
from ..base import BasePage
from ..common import configure_table, populate_leagues, populate_seasons
from ..dialogs import PredictionDialog
from ..widgets import (
    Badge,
    Banner,
    Card,
    FormBadges,
    InfoRow,
    LogoLabel,
    ProbabilityBar,
    SmallButton,
    make_mono_label,
    table_item,
)

VALUE_TO_BET = {
    "home": ("1X2", "Victoire domicile"),
    "draw": ("1X2", "Match nul"),
    "away": ("1X2", "Victoire exterieur"),
    "over25": ("OU25", "Plus de 2.5 buts"),
    "under25": ("OU25", "Moins de 2.5 buts"),
    "btts_yes": ("BTTS", "Les deux equipes marquent : Oui"),
    "btts_no": ("BTTS", "Les deux equipes marquent : Non"),
}


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{float(value) * 100:.1f} %"


class AnalysisPage(BasePage):
    predictions_changed = pyqtSignal()

    def __init__(self, service: DataService, parent=None):
        super().__init__(service, parent)
        self.fixture: dict | None = None
        self.model: dict | None = None
        self.odds_data: dict | None = None
        self.active_odds: dict[str, dict] = {}
        self._analysis_loading = False
        self._odds_loading = False
        self._fixture_list_loading = False
        self._pending_odds: dict[str, dict] | None = None
        self._current_value_bets: list[dict] = []

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

        columns = QHBoxLayout()
        columns.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(14)
        right = QVBoxLayout()
        right.setSpacing(14)
        left.addWidget(self._build_model_card())
        left.addWidget(self._build_markets_card())
        left.addWidget(self._build_scores_card())
        right.addWidget(self._build_value_card())
        right.addWidget(self._build_team_card())
        columns.addLayout(left, 3)
        columns.addLayout(right, 2)
        self.content_layout.addLayout(columns)
        self.content_layout.addWidget(
            Banner(
                "Analyse informative : le modele ne remplace pas votre jugement et ne garantit "
                "aucun resultat. Les cotes peuvent varier. Jouez de facon responsable.",
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
        self.league_combo.currentIndexChanged.connect(lambda _i: self._load_fixture_list())
        row.addWidget(self.league_combo)

        row.addWidget(QLabel("Saison"))
        self.season_combo = QComboBox()
        populate_seasons(
            self.season_combo,
            self.service.config.seasons,
            self.service.settings().get("default_season"),
        )
        self.season_combo.currentIndexChanged.connect(lambda _i: self._load_fixture_list())
        row.addWidget(self.season_combo)

        row.addWidget(QLabel("Match"))
        self.fixture_combo = QComboBox()
        self.fixture_combo.setMinimumWidth(320)
        self.fixture_combo.setMaxVisibleItems(18)
        self.fixture_combo.currentIndexChanged.connect(self._on_fixture_combo_changed)
        row.addWidget(self.fixture_combo, 1)

        self.load_button = QPushButton("Charger la saison")
        self.load_button.clicked.connect(lambda: self._load_fixture_list(force=True))
        row.addWidget(self.load_button)
        card.add_layout(row)

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
        vs = QLabel("vs")
        vs.setStyleSheet(f"color: {MUTED}; font-weight: 600;")
        teams_row.addWidget(vs)
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

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.odds_button = QPushButton("Charger les cotes")
        self.odds_button.setToolTip(
            "Cotes 1X2 et Over/Under 2.5 disponibles dans les CSV gratuits"
        )
        self.odds_button.clicked.connect(lambda: self.load_odds())
        buttons.addWidget(self.odds_button)
        self.bet_button = QPushButton("Suivre ce pronostic")
        self.bet_button.setObjectName("primary")
        self.bet_button.clicked.connect(self._open_prediction)
        buttons.addWidget(self.bet_button)
        right.addLayout(buttons)
        layout.addLayout(right)
        card.add_layout(layout)
        return card

    def _build_model_card(self) -> Card:
        card = Card("Modele Poisson", "Probabilites estimees a partir des resultats de la saison")
        self.reliability_badge = Badge("—", "gray")
        card.add_header_widget(self.reliability_badge)
        self.model_banner = Banner()
        card.add(self.model_banner)

        self.prob_home = ProbabilityBar("Victoire domicile", 0.0, BLUE)
        self.prob_draw = ProbabilityBar("Match nul", 0.0, AMBER)
        self.prob_away = ProbabilityBar("Victoire exterieur", 0.0, PURPLE)
        card.add(self.prob_home)
        card.add(self.prob_draw)
        card.add(self.prob_away)

        xg_row = QHBoxLayout()
        xg_row.setSpacing(14)
        xg_row.addWidget(InfoRow("xG domicile", "—", mono=True), 1)
        xg_row.addWidget(InfoRow("xG exterieur", "—", mono=True), 1)
        xg_row.addWidget(InfoRow("Total attendu", "—", mono=True), 1)
        card.add_layout(xg_row)
        self.xg_home = xg_row.itemAt(0).widget()
        self.xg_away = xg_row.itemAt(1).widget()
        self.xg_total = xg_row.itemAt(2).widget()

        self.sample_label = QLabel("En attente d'un match.")
        self.sample_label.setObjectName("small")
        self.sample_label.setWordWrap(True)
        card.add(self.sample_label)
        return card

    def _build_markets_card(self) -> Card:
        card = Card("Marches complementaires")
        self.prob_over = ProbabilityBar("Plus de 2.5 buts", 0.0, ACCENT)
        self.prob_under = ProbabilityBar("Moins de 2.5 buts", 0.0, MUTED)
        self.prob_btts = ProbabilityBar("BTTS : oui", 0.0, BLUE)
        self.prob_no_btts = ProbabilityBar("BTTS : non", 0.0, MUTED)
        card.add(self.prob_over)
        card.add(self.prob_under)
        card.add(self.prob_btts)
        card.add(self.prob_no_btts)
        return card

    def _build_scores_card(self) -> Card:
        card = Card("Scores exacts les plus probables")
        self.scores_table = QTableWidget()
        configure_table(self.scores_table, ["Score", "Probabilite"], stretch_columns=[1], row_height=30)
        self.scores_table.setMinimumHeight(220)
        self.scores_table.setMaximumHeight(250)
        card.add(self.scores_table)
        return card

    def _build_value_card(self) -> Card:
        card = Card("Value bets", "Comparez le modele aux cotes du marche")
        self.value_badge = Badge("—", "gray")
        card.add_header_widget(self.value_badge)
        self.value_banner = Banner()
        card.add(self.value_banner)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.fetch_odds_button = QPushButton("Charger les cotes")
        self.fetch_odds_button.setObjectName("primary")
        self.fetch_odds_button.clicked.connect(lambda: self.load_odds())
        actions.addWidget(self.fetch_odds_button)
        self.manual_toggle = QPushButton("Saisir mes cotes")
        self.manual_toggle.clicked.connect(self._toggle_manual)
        actions.addWidget(self.manual_toggle)
        actions.addStretch()
        self.odds_source_label = QLabel("Aucune cote chargee")
        self.odds_source_label.setObjectName("small")
        actions.addWidget(self.odds_source_label)
        card.add_layout(actions)

        self.manual_panel = self._build_manual_panel()
        self.manual_panel.setVisible(False)
        card.add(self.manual_panel)

        self.value_empty = QLabel(
            "Chargez les cotes disponibles (CSV gratuit) ou saisissez vos propres "
            "cotes pour detecter les value bets, l'edge et l'EV."
        )
        self.value_empty.setWordWrap(True)
        self.value_empty.setObjectName("small")
        card.add(self.value_empty)

        self.value_table = QTableWidget()
        configure_table(
            self.value_table,
            ["Marche", "Cote", "Book", "Proba", "Edge", "EV", "Cote juste", ""],
            stretch_columns=[0],
            row_height=36,
        )
        self.value_table.setMinimumHeight(270)
        self.value_table.setVisible(False)
        card.add(self.value_table)
        return card

    def _build_manual_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"background: #0d1520; border: 1px solid {BORDER}; border-radius: 9px;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        title = QLabel("Cotes manuelles (decimale europeenne)")
        title.setStyleSheet(f"color: {TEXT_SOFT}; font-weight: 600;")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        self.manual_spins: dict[str, QDoubleSpinBox] = {}
        fields = [
            ("home", "Domicile"),
            ("draw", "Nul"),
            ("away", "Exterieur"),
            ("over25", "Plus 2.5"),
            ("under25", "Moins 2.5"),
            ("btts_yes", "BTTS oui"),
            ("btts_no", "BTTS non"),
        ]
        for index, (key, label) in enumerate(fields):
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 1000.0)
            spin.setDecimals(2)
            spin.setSingleStep(0.05)
            spin.setSpecialValueText("—")
            self.manual_spins[key] = spin
            row, col = divmod(index, 4)
            grid.addWidget(QLabel(label), row * 2, col)
            grid.addWidget(spin, row * 2 + 1, col)
        layout.addLayout(grid)

        buttons = QHBoxLayout()
        apply_button = QPushButton("Calculer la value")
        apply_button.setObjectName("primary")
        apply_button.clicked.connect(self._apply_manual_odds)
        buttons.addWidget(apply_button)
        clear_button = QPushButton("Effacer")
        clear_button.clicked.connect(self._clear_manual_odds)
        buttons.addWidget(clear_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        return panel

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

    def refresh_league_combos(self) -> None:
        self._refresh_league_combos()
        if self.isVisible() and self.fixture is None and self.fixture_combo.count() == 0:
            self._load_fixture_list()

    def refresh_after_warmup(self) -> None:
        if self.fixture is not None and not self._analysis_loading:
            self._run_analysis()

    def _refresh_league_combos(self) -> None:
        leagues = self.service.tracked_leagues()
        populate_leagues(self.league_combo, leagues, include_all=False)
        if self.league_combo.count() == 0:
            self.fixture_combo.clear()

    def load_fixture(self, fixture: dict) -> None:
        """Appele depuis la page Matchs ou le tableau de bord."""
        self.fixture = fixture
        self.model = None
        self.odds_data = None
        self.active_odds = {}
        self._current_value_bets = []
        self._pending_odds = None
        self.analysis_banner.set_message("")
        self.value_banner.set_message("")
        self.value_table.setVisible(False)
        self.value_table.setRowCount(0)
        self.value_empty.setVisible(True)
        self.odds_source_label.setText("Aucune cote chargee")
        self.value_badge.setText("—")
        self.value_badge.set_kind("gray")
        for spin in self.manual_spins.values():
            spin.blockSignals(True)
            spin.setValue(0.0)
            spin.blockSignals(False)

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
        for fixture in ordered:
            label = (
                f"{self.service.format_kickoff(fixture.get('date'))}  •  "
                f"{fixture['home']['name']} - {fixture['away']['name']}"
            )
            self.fixture_combo.addItem(label, fixture)
        self.fixture_combo.blockSignals(False)
        if result.get("warning"):
            self.analysis_banner.set_message(result["warning"], "warning")
        else:
            self.analysis_banner.set_message("")
        self.fixture_combo.setCurrentIndex(0)
        self._on_fixture_combo_changed(0)

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
        self.odds_data = None
        self.active_odds = {}
        self._pending_odds = None
        self._current_value_bets = []
        self.value_table.setVisible(False)
        self.value_table.setRowCount(0)
        self.value_empty.setVisible(True)
        self.odds_source_label.setText("Aucune cote chargee")
        self.value_badge.setText("—")
        self.value_badge.set_kind("gray")
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
            busy_text="Calcul du modele Poisson...",
        )

    def _on_analysis_loaded(self, model: dict) -> None:
        self._analysis_loading = False
        self.model = model
        warning = (model.get("_meta") or {}).get("warning")
        self.analysis_banner.set_message(warning or "", "warning" if warning else "info")
        self._render_model()
        if self._pending_odds:
            odds = self._pending_odds
            self._pending_odds = None
            self._apply_odds(odds, self.odds_source_label.text() or "Cotes manuelles")

    def _on_analysis_error(self, code: str, message: str) -> None:
        self._analysis_loading = False
        self.analysis_banner.set_message(message, "error")
        self.model = None

    def _render_model(self) -> None:
        if not self.model:
            return
        probs = self.model["probabilities"]
        self.prob_home.set_value(probs["home"])
        self.prob_draw.set_value(probs["draw"])
        self.prob_away.set_value(probs["away"])
        self.prob_over.set_value(probs["over25"])
        self.prob_under.set_value(probs["under25"])
        self.prob_btts.set_value(probs["btts_yes"])
        self.prob_no_btts.set_value(probs["btts_no"])

        self.xg_home.set_value(f"{self.model['lambda_home']:.2f}")
        self.xg_away.set_value(f"{self.model['lambda_away']:.2f}")
        self.xg_total.set_value(f"{self.model['expected_total']:.2f}")
        reliability = self.model.get("reliability", "faible")
        kind = {"bonne": "green", "moyenne": "amber", "faible": "red"}.get(reliability, "gray")
        self.reliability_badge.setText(reliability.upper())
        self.reliability_badge.set_kind(kind)

        sample = int(self.model.get("sample_matches") or 0)
        season = self.model.get("season")
        detail = f"Base : {sample} match(s) de la saison {season}"
        if self.model.get("before_date"):
            detail += f", avant le {self._format_date(self.model['before_date'])}"
        detail += "."
        if not self.model.get("known_home") or not self.model.get("known_away"):
            missing = []
            if not self.model.get("known_home"):
                missing.append(self.model["fixture"]["home"]["name"])
            if not self.model.get("known_away"):
                missing.append(self.model["fixture"]["away"]["name"])
            self.model_banner.set_message(
                "Donnees insuffisantes pour : " + ", ".join(missing) + ". "
                "Les moyennes de la ligue sont utilisees (fiabilite faible).",
                "warning",
            )
        else:
            self.model_banner.set_message("")
        self.sample_label.setText(
            detail
            + " Les probabilites sont recalculees localement, sans appel supplementaire."
        )

        self.scores_table.setRowCount(0)
        for row, score in enumerate(self.model.get("scores") or []):
            self.scores_table.insertRow(row)
            self.scores_table.setItem(row, 0, table_item(score["score"], bold=True))
            prob_item = table_item(f"{score['prob'] * 100:.1f} %", align_right=True, color=ACCENT)
            self.scores_table.setItem(row, 1, prob_item)

        self._render_teams()

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

    def load_odds(self, force: bool = False) -> None:
        if not self.fixture or self._odds_loading:
            return
        self._odds_loading = True
        self.odds_button.setEnabled(False)
        self.fetch_odds_button.setEnabled(False)
        self.fetch_odds_button.setText("Chargement...")
        self.odds_source_label.setText("Recuperation des cotes...")
        fixture = self.fixture

        self.run_task(
            lambda _progress: self.service.odds_for_fixture(fixture, force=force),
            self._on_odds_loaded,
            self._on_odds_error,
            busy_text="Recuperation des cotes...",
        )

    def _on_odds_loaded(self, result: dict) -> None:
        self._odds_loading = False
        self.odds_button.setEnabled(True)
        self.fetch_odds_button.setEnabled(True)
        self.fetch_odds_button.setText("Charger les cotes")
        self.odds_data = result
        odds = result.get("odds") or {}
        if not odds:
            self.odds_source_label.setText("Aucune cote disponible")
            self.value_banner.set_message(
                "Aucune cote trouvee pour ce match. Les matchs a venir des sources "
                "gratuites n'ont pas encore de cotes CSV : saisissez vos cotes manuellement.",
                "warning",
            )
            self.value_empty.setVisible(True)
            self.value_table.setVisible(False)
            return
        self._fill_manual_odds(odds)
        source_name = result.get("source") or "Cotes manuelles"
        source = f"{source_name} • {result.get('bookmaker_count', 0)} source(s)"
        self.odds_source_label.setText(source)
        if result.get("warning"):
            self.value_banner.set_message(result["warning"], "warning")
        else:
            self.value_banner.set_message("")
        self._apply_odds(odds, source)

    def _on_odds_error(self, code: str, message: str) -> None:
        self._odds_loading = False
        self.odds_button.setEnabled(True)
        self.fetch_odds_button.setEnabled(True)
        self.fetch_odds_button.setText("Charger les cotes")
        self.odds_source_label.setText("Cotes indisponibles")
        self.value_banner.set_message(
            message + " Vous pouvez saisir vos cotes manuellement ci-dessous.", "warning"
        )
        self.value_empty.setVisible(True)
        self.value_table.setVisible(False)

    def _fill_manual_odds(self, odds: dict[str, dict]) -> None:
        for key, spin in self.manual_spins.items():
            entry = odds.get(key)
            if entry:
                spin.blockSignals(True)
                spin.setValue(float(entry.get("odd") or 0.0))
                spin.blockSignals(False)

    def _toggle_manual(self) -> None:
        visible = not self.manual_panel.isVisible()
        self.manual_panel.setVisible(visible)
        self.manual_toggle.setText("Masquer les cotes manuelles" if visible else "Saisir mes cotes")

    def _clear_manual_odds(self) -> None:
        for spin in self.manual_spins.values():
            spin.blockSignals(True)
            spin.setValue(0.0)
            spin.blockSignals(False)

    def _apply_manual_odds(self) -> None:
        odds = {}
        for key, spin in self.manual_spins.items():
            if spin.value() > 1.01:
                odds[key] = {"odd": round(spin.value(), 3), "bookmaker": "Manuel"}
        if not odds:
            self.value_banner.set_message("Saisissez au moins une cote superieure a 1.01.", "warning")
            return
        self.odds_source_label.setText("Cotes manuelles")
        self._apply_odds(odds, "Cotes manuelles")

    def _apply_odds(self, odds: dict[str, dict], source: str) -> None:
        if not self.model:
            self._pending_odds = odds
            self.value_banner.set_message(
                "Cotes memorisees. Le calcul sera effectue des que le modele sera pret.", "info"
            )
            return
        self.active_odds = odds
        bets = value_bets(self.model["probabilities"], odds)
        self._current_value_bets = bets
        self._render_value_bets(bets, source)

    def _render_value_bets(self, bets: list[dict], source: str) -> None:
        self.value_table.setRowCount(0)
        if not bets:
            self.value_empty.setVisible(True)
            self.value_table.setVisible(False)
            self.value_badge.setText("AUCUNE COTE")
            self.value_badge.set_kind("gray")
            return
        self.value_empty.setVisible(False)
        self.value_table.setVisible(True)
        recommended = [bet for bet in bets if bet["recommended"]]
        best = max(bets, key=lambda bet: bet["edge"])
        self.value_badge.setText(f"{len(recommended)} VALUE" if recommended else "PAS DE VALUE")
        self.value_badge.set_kind("green" if recommended else "gray")
        if recommended:
            self.value_banner.set_message(
                f"{len(recommended)} opportunite(s) positive(s) • meilleur edge : "
                f"{best['label']} ({best['edge'] * 100:+.1f} pts). "
                f"Cote juste du modele : {best['fair_odd']:.2f}.",
                "success",
            )
        else:
            self.value_banner.set_message(
                "Aucune value positive avec ces cotes : le modele estime que le marche est "
                "correctement precio ou plus prudent que lui.",
                "info",
            )

        self.value_table.setRowCount(len(bets))
        for row, bet in enumerate(bets):
            label = bet["label"]
            item = table_item(label, bold=bet["recommended"])
            if bet["recommended"]:
                item.setForeground(QColor(ACCENT))
            self.value_table.setItem(row, 0, item)
            self.value_table.setItem(row, 1, table_item(f"{bet['odd']:.2f}", align_right=True))
            self.value_table.setItem(row, 2, table_item(bet.get("bookmaker") or "—", color=MUTED))
            self.value_table.setItem(row, 3, table_item(_pct(bet["prob"]), align_right=True))
            edge_color = ACCENT if bet["edge"] > 0 else RED
            self.value_table.setItem(
                row, 4, table_item(f"{bet['edge'] * 100:+.1f} pts", align_right=True, color=edge_color)
            )
            ev_color = ACCENT if bet["ev"] > 0 else RED
            self.value_table.setItem(
                row, 5, table_item(f"{bet['ev'] * 100:+.1f} %", align_right=True, color=ev_color)
            )
            self.value_table.setItem(
                row,
                6,
                table_item(
                    f"{bet['fair_odd']:.2f}" if bet.get("fair_odd") is not None else "—",
                    align_right=True,
                    color=MUTED,
                ),
            )
            action = SmallButton("Suivre", primary=bet["recommended"])
            action.clicked.connect(lambda _checked=False, b=bet: self._open_value_bet(b))
            wrapper = QWidget()
            wrap_layout = QHBoxLayout(wrapper)
            wrap_layout.setContentsMargins(0, 0, 0, 0)
            wrap_layout.addWidget(action)
            self.value_table.setCellWidget(row, 7, wrapper)
        self.odds_source_label.setText(source)

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
        self.odds_button.setEnabled(enabled)
        self.bet_button.setEnabled(enabled)
        self.fetch_odds_button.setEnabled(enabled)
        if not enabled:
            self.analysis_banner.set_message(
                "Selectionnez un match dans la liste ou cliquez sur Analyser depuis la page Matchs.",
                "info",
            )

    # -------------------------------------------------------------- pronostic

    def _open_value_bet(self, bet: dict) -> None:
        if not self.fixture or not self.model:
            return
        market, selection = VALUE_TO_BET.get(bet["key"], ("1X2", bet["label"]))
        self._open_prediction(
            market=market,
            selection=selection,
            odds=bet["odd"],
            model_prob=bet["prob"],
            edge=bet["edge"],
        )

    def _open_prediction(
        self,
        market: str = "1X2",
        selection: str | None = None,
        odds: float | None = None,
        model_prob: float | None = None,
        edge: float | None = None,
    ) -> None:
        if not self.fixture:
            return
        fixture = self.fixture
        prefill = {
            "fixture_id": fixture.get("id"),
            "league_id": fixture["league"].get("id"),
            "league_name": fixture["league"].get("name"),
            "home": fixture["home"].get("name"),
            "away": fixture["away"].get("name"),
            "kickoff": fixture.get("date"),
            "match_label": f"{fixture['home'].get('name')} — {fixture['away'].get('name')}",
            "market": market,
            "selection": selection,
            "odds": odds,
            "model_prob": model_prob,
            "edge": edge,
        }
        dialog = PredictionDialog(self.service, prefill, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            prediction = dialog.get_prediction()
            self.service.db.add_prediction(prediction)
            odd_text = f" @ {prediction['odds']:.2f}" if prediction.get("odds") else ""
            self.toast.emit(f"Pronostic enregistre : {prediction['selection']}{odd_text}")
            self.predictions_changed.emit()

    # ----------------------------------------------------------------- utils

    @staticmethod
    def _format_date(value: str) -> str:
        try:
            return datetime.fromisoformat(value).strftime("%d/%m/%Y")
        except (ValueError, TypeError):
            return value
