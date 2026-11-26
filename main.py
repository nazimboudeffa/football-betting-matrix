import sys
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QDialog,
    QDialogButtonBox,
)

from football_betting_matrix.strategies import StrategyCatalog, load_strategies, strategies_dir
from football_data import LeagueSpec, build_fixtures, format_fd_info, list_leagues, list_seasons
from football_betting_matrix import ai as ai_module


def format_match_label(m: dict) -> str:
    date = m.get("date", "N/A")
    time = m.get("time")
    team1 = m.get("team1", m.get("home_team", "?"))
    team2 = m.get("team2", m.get("away_team", "?"))
    score = m.get("score")

    ft = None
    if isinstance(score, dict):
        ft = score.get("ft")
    elif isinstance(score, list) and len(score) >= 2:
        ft = score[:2]

    if isinstance(ft, list) and len(ft) == 2:
        score_txt = f"{ft[0]}-{ft[1]}"
    else:
        score_txt = "vs"

    round_name = m.get("round")
    prefix = f"[{round_name}] " if round_name else ""
    dt = f"{date} {time}" if time else date
    return f"{prefix}{dt}  |  {team1} {score_txt} {team2}"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Football Betting Matrix (PyQt6) - football-data.co.uk")
        self.resize(1200, 720)

        self.fixtures: List[dict] = []
        self.current_match: Optional[dict] = None
        self.catalog: StrategyCatalog = load_strategies(strategies_dir(Path(__file__).resolve().parent))

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # Controls (top bar)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Saison:"))
        self.season_combo = QComboBox()
        self.season_combo.addItems(list_seasons())
        controls.addWidget(self.season_combo)

        controls.addWidget(QLabel("Ligue:"))
        self.league_combo = QComboBox()
        controls.addWidget(self.league_combo)

        controls.addStretch(1)
        root.addLayout(controls)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: matches list
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Matchs (sélectionne un match):"))
        self.matches_list = QListWidget()
        left_layout.addWidget(self.matches_list)
        splitter.addWidget(left)

        # Right: odds table + strategy controls
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 8, 8, 8)

        strat_row = QHBoxLayout()
        strat_row.addWidget(QLabel("Stratégie:"))
        self.strategy_combo = QComboBox()
        if self.catalog.strategies:
            for s in self.catalog.strategies:
                self.strategy_combo.addItem(s.name, s.id)
        else:
            self.strategy_combo.addItem("(aucune stratégie trouvée)", "")
        strat_row.addWidget(self.strategy_combo, 1)
        self.btn_ai = QPushButton("Analyser avec l'IA (Llama App)")
        strat_row.addWidget(self.btn_ai)
        right_layout.addLayout(strat_row)

        right_splitter = QSplitter(Qt.Orientation.Vertical)

        odds_panel = QWidget()
        odds_layout = QVBoxLayout(odds_panel)
        odds_layout.setContentsMargins(0, 0, 0, 0)
        odds_layout.addWidget(QLabel("Cotes modèle / bookmakers:"))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Marché", "Proba", "Cote juste", "Cote bookmaker", "Signal"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(80)
        odds_layout.addWidget(self.table, 1)

        self.details_label = QLabel("Choisis une saison, une ligue, un match, puis une stratégie.")
        self.details_label.setWordWrap(True)
        self.details_label.setMaximumHeight(50)
        odds_layout.addWidget(self.details_label)
        right_splitter.addWidget(odds_panel)

        fd_panel = QWidget()
        fd_layout = QVBoxLayout(fd_panel)
        fd_layout.setContentsMargins(0, 0, 0, 0)
        fd_layout.addWidget(QLabel("Infos bookmakers / stats (football-data.co.uk) :"))
        self.fd_table = QTableWidget(0, 2)
        self.fd_table.setHorizontalHeaderLabels(["Info", "Valeur"])
        self.fd_table.horizontalHeader().setStretchLastSection(True)
        self.fd_table.setMinimumHeight(80)
        self.fd_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        fd_layout.addWidget(self.fd_table, 1)
        right_splitter.addWidget(fd_panel)

        right_splitter.setStretchFactor(0, 2)
        right_splitter.setStretchFactor(1, 1)
        right_layout.addWidget(right_splitter, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter, 1)

        self.status_label = QLabel("Prêt.")
        root.addWidget(self.status_label)

        # Signals
        self.season_combo.currentTextChanged.connect(self.on_season_changed)
        self.league_combo.currentTextChanged.connect(self._on_league_combo_changed)
        self.matches_list.currentRowChanged.connect(self.on_match_selected)
        self.btn_ai.clicked.connect(self.on_analyze_ai)
        self.strategy_combo.currentIndexChanged.connect(lambda _: self.on_strategy_changed())

        # Init
        self.on_season_changed(self.season_combo.currentText())

    def set_status(self, text: str):
        self.status_label.setText(text)

    def on_season_changed(self, season: str):
        self.league_combo.blockSignals(True)
        self.league_combo.clear()
        for spec in list_leagues():
            self.league_combo.addItem(spec.name, spec)
        self.league_combo.setEnabled(True)
        self.league_combo.blockSignals(False)
        self._on_league_combo_changed()

    def _on_league_combo_changed(self):
        spec = self.league_combo.currentData()
        if not isinstance(spec, LeagueSpec):
            return
        self.on_league_changed(spec)

    def on_league_changed(self, spec: LeagueSpec):
        season = self.season_combo.currentText()
        self.set_status(f"Chargement: football-data.co.uk — {spec.name} {season} ...")
        QApplication.processEvents()

        try:
            fixtures = build_fixtures(spec, season)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Erreur de chargement",
                f"Impossible de charger {spec.name} {season} depuis football-data.co.uk :\n\n{e}",
            )
            self.set_status("Échec du chargement.")
            return

        self.fixtures = fixtures
        self.matches_list.clear()
        for match in fixtures:
            self.matches_list.addItem(QListWidgetItem(format_match_label(match)))

        if fixtures:
            # Les prochains matchs sont en fin de liste : on sélectionne le premier
            # match à venir pour afficher directement ses cotes bookmaker.
            first_upcoming = next(
                (index for index, match in enumerate(fixtures) if not match.get("played")),
                0,
            )
            self.matches_list.setCurrentRow(first_upcoming)
        else:
            self.current_match = None
            self.table.setRowCount(0)
            self.fd_table.setRowCount(0)
            self.fd_table.insertRow(0)
            self.fd_table.setItem(0, 0, QTableWidgetItem("football-data.co.uk"))
            self.fd_table.setItem(0, 1, QTableWidgetItem("Aucun match pour cette ligue/saison."))

        played = sum(1 for match in fixtures if match.get("played"))
        self.set_status(
            f"{spec.name} {season} — {len(fixtures)} match(s) "
            f"({played} joués, {len(fixtures) - played} à venir)."
        )

    def on_match_selected(self, row: int):
        if row < 0 or row >= len(self.fixtures):
            self.current_match = None
            self.fd_table.setRowCount(0)
            self.fd_table.insertRow(0)
            self.fd_table.setItem(0, 0, QTableWidgetItem("Football-data.co.uk"))
            self.fd_table.setItem(0, 1, QTableWidgetItem("Sélectionne un match."))
            self.table.setRowCount(0)
            return
        self.current_match = self.fixtures[row]
        self.update_football_data_panel()
        self.update_odds_table()

    def on_strategy_changed(self):
        if self.current_match is None:
            return
        self.update_odds_table()

    def update_football_data_panel(self):
        """Affiche la ligne CSV brute du match sélectionné (déjà chargée)."""
        self.fd_table.setRowCount(0)
        if not self.current_match:
            self._add_fd_row("football-data.co.uk", "Sélectionne un match.")
            return
        spec = self.league_combo.currentData()
        season = self.season_combo.currentText()
        source = f"football-data.co.uk — {spec.name if spec else ''} {season}".strip()
        self._add_fd_row("Source", source)

        items = format_fd_info(self.current_match.get("fd_row") or {})
        if not items:
            self._add_fd_row("Info", "Aucune statistique disponible pour ce match.")
            return
        for key, value in items:
            self._add_fd_row(str(key), str(value))

    def _add_fd_row(self, key: str, value: str):
        row = self.fd_table.rowCount()
        self.fd_table.insertRow(row)
        self.fd_table.setItem(row, 0, QTableWidgetItem(key))
        self.fd_table.setItem(row, 1, QTableWidgetItem(value))

    def _analysis_for_current_match(self):
        """Calcule les probabilités du modèle avec les vrais IDs d'équipe."""
        prob_strategy = self.catalog.probability_model()
        if not (prob_strategy and prob_strategy.analyze):
            return None, None, "Aucune stratégie d'analyse (analyze)."
        m = self.current_match
        teams = m.get("teams") or {}
        home = teams.get("home") or {}
        away = teams.get("away") or {}
        try:
            analysis = prob_strategy.analyze(
                fixtures=self.fixtures,
                home_id=home.get("id"),
                away_id=away.get("id"),
                home_name=m.get("team1") or home.get("name") or "Home",
                away_name=m.get("team2") or away.get("name") or "Away",
                before_date=m.get("date"),
            )
        except Exception as e:
            return None, None, str(e)
        return analysis, prob_strategy, None

    def update_odds_table(self):
        self.table.setRowCount(0)
        if not self.current_match or not self.catalog.strategies:
            return
        strategy_id = self.strategy_combo.currentData()
        strategy = self.catalog.get(strategy_id) if strategy_id else self.catalog.probability_model()
        if strategy is None:
            return

        analysis, prob_strategy, error = self._analysis_for_current_match()
        if error:
            self._add_odds_error(error)
            return
        probs = analysis.get("probabilities") if isinstance(analysis, dict) else None
        if not probs:
            return

        m = self.current_match
        try:
            rows = strategy.run(probs, context={"match": m, "odds": m.get("odds") or {}})
        except Exception as e:
            self._add_odds_error(str(e))
            return

        market_odds = m.get("odds") or {}
        for row in rows:
            key = row.get("key")
            best = (market_odds.get(key) or {}).get("best") if key else None
            bookmaker = best[0] if best else "-"
            market_odd = row.get("market_odd") or (best[1] if best else None)
            signal = str(row.get("signal") or "")
            if market_odd and "value" not in signal.lower() and "VALUE" not in signal:
                edge = float(row["prob"]) * float(market_odd) - 1
                signal = f"{signal + ' — ' if signal else ''}{edge:+.1%}"
            idx = self.table.rowCount()
            self.table.insertRow(idx)
            self.table.setItem(idx, 0, QTableWidgetItem(str(row.get("label", ""))))
            try:
                prob_text = f"{float(row['prob']):.2%}"
            except (TypeError, ValueError, KeyError):
                prob_text = "-"
            self.table.setItem(idx, 1, QTableWidgetItem(prob_text))
            self.table.setItem(idx, 2, QTableWidgetItem(str(row.get("odd", ""))))
            self.table.setItem(idx, 3, QTableWidgetItem(f"{market_odd} ({bookmaker})" if market_odd else "-"))
            self.table.setItem(idx, 4, QTableWidgetItem(signal))

        known = "modèle" if analysis.get("known_home") and analysis.get("known_away") else "moyennes de ligue"
        self.details_label.setText(
            f"{m.get('team1')} vs {m.get('team2')} ({m.get('date')}) — "
            f"{prob_strategy.name} → {strategy.name} — probabilités: {known}"
        )

    def _add_odds_error(self, message: str):
        self.table.insertRow(0)
        for column in range(5):
            self.table.setItem(0, column, QTableWidgetItem("-" if column < 4 else message))

    def _build_ai_analysis_payload(self) -> Optional[dict]:
        if not self.current_match:
            QMessageBox.information(self, "Info", "Sélectionne un match d'abord.")
            return None
        if not self.catalog.strategies:
            QMessageBox.warning(self, "Aucune stratégie", "Aucune stratégie trouvée dans user_strategies/.")
            return None

        strategy_id = self.strategy_combo.currentData()
        strategy = self.catalog.get(strategy_id) if strategy_id else self.catalog.probability_model()
        if strategy is None:
            QMessageBox.warning(self, "Stratégie", "Aucune stratégie disponible.")
            return None

        m = self.current_match
        teams = m.get("teams") or {}
        home = teams.get("home") or {}
        away = teams.get("away") or {}
        home_name = m.get("team1") or home.get("name") or "Home"
        away_name = m.get("team2") or away.get("name") or "Away"
        date = m.get("date")

        analysis, _, error = self._analysis_for_current_match()
        if error:
            QMessageBox.warning(self, "Erreur analyse", f"Erreur lors du calcul des probabilités:\n{error}")
            return None
        probs = analysis.get("probabilities") if isinstance(analysis, dict) else None
        if not probs:
            QMessageBox.warning(self, "Probabilités", "Impossible de calculer les probabilités pour ce match.")
            return None

        market_odds = m.get("odds") or {}
        try:
            rows = strategy.run(probs, context={"match": m, "odds": market_odds})
        except Exception as e:
            QMessageBox.warning(self, "Erreur stratégie", f"Erreur lors de l'évaluation:\n{e}")
            return None

        payload = {
            "match": {"home": home_name, "away": away_name, "date": date, "league": m.get("league")},
            "model": analysis,
            "strategy": {"id": strategy.id, "name": strategy.name, "rows": rows},
            "market_odds": {
                key: {"best": value.get("best"), "avg": value.get("avg")}
                for key, value in market_odds.items()
            },
            "league": self.league_combo.currentText(),
            "season": self.season_combo.currentText(),
        }
        # Explicit extras to help the AI
        home_info = (analysis or {}).get("home") or {}
        away_info = (analysis or {}).get("away") or {}
        payload["teams_form"] = {
            "home": {"name": home_name, "form": home_info.get("form", []), "rank": home_info.get("rank"), "played": home_info.get("played")},
            "away": {"name": away_name, "form": away_info.get("form", []), "rank": away_info.get("rank"), "played": away_info.get("played")},
        }
        # Standings snapshot from model if present
        if "n_teams" in (analysis or {}):
            payload["standings_context"] = {
                "n_teams": analysis.get("n_teams"),
                "reliability": analysis.get("reliability"),
                "sample_matches": analysis.get("sample_matches"),
                "league_rates": analysis.get("league_rates"),
            }
        return payload

    def on_analyze_ai(self):
        payload = self._build_ai_analysis_payload()
        if payload is None:
            return

        try:
            models = ai_module.list_models()
        except Exception as e:
            QMessageBox.warning(self, "Llama App", str(e))
            return
        if not models:
            QMessageBox.warning(
                self,
                "Llama App",
                "Aucun modèle Llama App trouvé. Installe un modèle dans l'application "
                "et charge-le avant de relancer l'analyse.",
            )
            return

        context = ai_module.build_context(payload)
        default_prompt = ai_module.DEFAULT_PROMPT + "\n\n--- DONNEES ---\n" + context

        dlg = QDialog(self)
        dlg.setWindowTitle("Analyse IA (Llama App)")
        dlg.resize(900, 700)
        layout = QVBoxLayout(dlg)

        layout.addWidget(QLabel("Modèle Llama App:"))
        model_cb = QComboBox()
        model_cb.addItems(models)
        layout.addWidget(model_cb)

        layout.addWidget(QLabel("Prompt:"))
        prompt_edit = QTextEdit()
        prompt_edit.setPlainText(default_prompt)
        prompt_edit.setMinimumHeight(180)
        layout.addWidget(prompt_edit)

        layout.addWidget(QLabel("Raisonnement / Résultat:"))
        result_edit = QTextEdit()
        result_edit.setReadOnly(True)
        result_edit.setPlaceholderText("Le résultat de l'analyse s'affichera ici.")
        layout.addWidget(result_edit, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_cancel = QPushButton("Annuler")
        btn_run = QPushButton("Lancer l'analyse")
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_run)
        layout.addLayout(btn_row)

        def do_run():
            model = model_cb.currentText().strip()
            prompt = prompt_edit.toPlainText().strip()
            if not model:
                QMessageBox.warning(dlg, "Llama App", "Choisis un modèle.")
                return
            if not prompt:
                QMessageBox.warning(dlg, "Prompt", "Le prompt est vide.")
                return
            result_edit.setPlainText("Analyse en cours (Llama App)...")
            btn_run.setEnabled(False)
            btn_cancel.setEnabled(False)
            QApplication.processEvents()
            try:
                result = ai_module.ask_llama_app(prompt, model=model)
                result_edit.setPlainText(result)
                self.details_label.setText(
                    f"{payload['match']['home']} vs {payload['match']['away']} — Analyse IA terminée ({model})."
                )
                self.set_status("Analyse IA terminée.")
            except Exception as e:
                result_edit.setPlainText(f"Erreur IA: {e}")
                QMessageBox.warning(dlg, "Erreur IA", str(e))
            finally:
                btn_run.setEnabled(True)
                btn_cancel.setEnabled(True)

        btn_run.clicked.connect(do_run)
        btn_cancel.clicked.connect(dlg.reject)

        dlg.exec()


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
