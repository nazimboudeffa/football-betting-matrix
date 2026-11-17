"""Page Analyse : modele Poisson, cotes calculees et strategies utilisateur."""

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
    FormBadges,
    InfoRow,
    LogoLabel,
    ProbabilityBar,
    make_mono_label,
    table_item,
)


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{float(value) * 100:.1f} %"


class AnalysisPage(BasePage):

    def __init__(self, service: DataService, parent=None):
        super().__init__(service, parent)
        self.fixture: dict | None = None
        self.model: dict | None = None
        self._analysis_loading = False
        self._fixture_list_loading = False
        self._current_odds: list[dict] = []

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
        right.addWidget(self._build_odds_card())
        right.addWidget(self._build_team_card())
        columns.addLayout(left, 3)
        columns.addLayout(right, 2)
        self.content_layout.addLayout(columns)
        self.content_layout.addWidget(
            Banner(
                "Analyse informative : le modele ne remplace pas votre jugement et ne garantit "
                "aucun resultat. Les cotes affichees sont estimees, pas des cotes de bookmaker. "
                "Jouez de facon responsable.",
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

        self.ai_button = QPushButton("Analyser avec l'IA")
        self.ai_button.setToolTip(
            "Ouvrir une fenetre pour interroger Ollama avec l'analyse courante"
        )
        self.ai_button.clicked.connect(self._open_ai_dialog)
        self.ai_button.setEnabled(False)
        row.addWidget(self.ai_button)
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

    def _build_odds_card(self) -> Card:
        card = Card("Cotes calculees", "Cotes estimees par le modele selon la strategie")
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

        strategies: list[dict] = []
        for strategy in self.service.strategies.strategies:
            try:
                rows = strategy.run(self.model["probabilities"])
            except Exception:  # une strategie utilisateur ne doit pas bloquer l'IA
                rows = []
            strategies.append(
                {
                    "id": strategy.id,
                    "name": strategy.name,
                    "description": strategy.description,
                    "rows": rows,
                }
            )

        payload = {
            "fixture": self.fixture,
            "model": self.model,
            "selected_strategy": self.service.value_strategy_id(),
            "strategies": strategies,
        }
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
        self.analysis_banner.set_message("")
        self._reset_odds()

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
        self._reset_odds()
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
        self._recompute_odds()

    def _on_analysis_error(self, code: str, message: str) -> None:
        self._analysis_loading = False
        self.analysis_banner.set_message(message, "error")
        self.model = None
        self._reset_odds()

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

    # ----------------------------------------------------------------- utils

    @staticmethod
    def _format_date(value: str) -> str:
        try:
            return datetime.fromisoformat(value).strftime("%d/%m/%Y")
        except (ValueError, TypeError):
            return value
