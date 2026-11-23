import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
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
from football_data import football_data_csv_url, fetch_csv_rows, find_fd_row_for_match, format_fd_info
from football_betting_matrix import ai as ai_module


BASE_RAW_URL = "https://raw.githubusercontent.com/openfootball/football.json/master"

# In-memory cache: url -> (timestamp, data)
_JSON_CACHE: Dict[str, Tuple[float, Any]] = {}
_JSON_CACHE_TTL_SECONDS = 60 * 30  # 30 minutes


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
        self.setWindowTitle("Football Betting Matrix (PyQt6) - openfootball/football.json")
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
        self.season_combo.addItems(["2025", "2025-26", "2026", "2026-27"])
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
        self.btn_ai = QPushButton("Analyser avec l'IA (Ollama)")
        strat_row.addWidget(self.btn_ai)
        right_layout.addLayout(strat_row)

        right_layout.addWidget(QLabel("Cotes calculées:"))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Marché", "Proba", "Cote", "Signal"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(80)
        right_layout.addWidget(self.table, 1)

        self.details_label = QLabel("Choisis une saison, une ligue, un match, puis une stratégie.")
        self.details_label.setWordWrap(True)
        self.details_label.setMaximumHeight(50)
        right_layout.addWidget(self.details_label)

        right_layout.addWidget(QLabel("Infos bookmakers / stats (football-data.co.uk) :"))
        self.fd_table = QTableWidget(0, 2)
        self.fd_table.setHorizontalHeaderLabels(["Info", "Valeur"])
        self.fd_table.horizontalHeader().setStretchLastSection(True)
        self.fd_table.setMinimumHeight(80)
        self.fd_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        right_layout.addWidget(self.fd_table, 1)

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
        self.matches_list.currentRowChanged.connect(self.on_match_selected)

        # Init
        self.on_season_changed(self.season_combo.currentText())

    def set_status(self, text: str):
        self.status_label.setText(text)

    def fetch_json(self, season: str, filename: str) -> Optional[dict]:
        url = f"{BASE_RAW_URL}/{season}/{filename}"
        now = time.time()
        if url in _JSON_CACHE:
            ts, data = _JSON_CACHE[url]
            if now - ts < _JSON_CACHE_TTL_SECONDS:
                return data
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            _JSON_CACHE[url] = (now, data)
            return data
        except Exception as e:
            QMessageBox.critical(self, "Erreur de chargement", f"Impossible de charger:\n{url}\n\n{e}")
            return None

    def list_leagues_from_known_set(self, season: str) -> List[Tuple[str, str]]:
        """Return list of (display_name, filename)."""
        if season == "2025":
            return [
                ("Argentina Liga Profesional", "ar.1.json"),
                ("Brazil Serie A", "br.1.json"),
                ("Brazil Serie B", "br.2.json"),
                ("China Super League", "cn.1.json"),
                ("Colombia Primera A", "co.1.json"),
                ("Copa Libertadores", "copa.l.json"),
                ("Japan J1 League", "jp.1.json"),
                ("USA MLS", "mls.json"),
            ]
        if season == "2026":
            return [("Brazil Serie A", "br.1.json")]
        if season == "2025-26":
            return [
                ("England Premier League", "en.1.json"),
                ("England Championship", "en.2.json"),
                ("England League One", "en.3.json"),
                ("England League Two", "en.4.json"),
                ("Germany Bundesliga", "de.1.json"),
                ("Germany 2. Bundesliga", "de.2.json"),
                ("Spain La Liga", "es.1.json"),
                ("Spain La Liga 2", "es.2.json"),
                ("France Ligue 1", "fr.1.json"),
                ("France Ligue 2", "fr.2.json"),
                ("Italy Serie A", "it.1.json"),
                ("Italy Serie B", "it.2.json"),
                ("Netherlands Eredivisie", "nl.1.json"),
                ("Portugal Primeira Liga", "pt.1.json"),
                ("Belgium Pro League", "be.1.json"),
                ("Greece Super League", "gr.1.json"),
                ("Scotland Premiership", "sco.1.json"),
                ("Turkey Super Lig", "tr.1.json"),
                ("Austria Bundesliga", "at.1.json"),
                ("Austria 2. Liga", "at.2.json"),
            ]
        if season == "2026-27":
            return [
                ("England Premier League", "en.1.json"),
                ("England Championship", "en.2.json"),
                ("Germany Bundesliga", "de.1.json"),
                ("Spain La Liga", "es.1.json"),
                ("France Ligue 1", "fr.1.json"),
                ("Italy Serie A", "it.1.json"),
                ("Netherlands Eredivisie", "nl.1.json"),
                ("Portugal Primeira Liga", "pt.1.json"),
            ]
        return []

    def on_season_changed(self, season: str):
        self.league_combo.blockSignals(True)
        self.league_combo.clear()
        leagues = self.list_leagues_from_known_set(season)
        if not leagues:
            self.league_combo.addItem("(aucune ligue listée)", "")
            self.league_combo.setEnabled(False)
        else:
            for name, fname in leagues:
                self.league_combo.addItem(name, fname)
            self.league_combo.setEnabled(True)
        self.league_combo.blockSignals(False)

        if leagues:
            self._on_league_combo_changed()
        else:
            self.matches_list.clear()
            self.fixtures = []
            self.set_status("Aucune ligue disponible pour cette saison.")

    def _on_league_combo_changed(self):
        league_file = self.league_combo.currentData()
        if not league_file:
            return
        self.on_league_changed(league_file)

    def on_league_changed(self, league_file: str):
        if not league_file or league_file.startswith("("):
            return
        season = self.season_combo.currentText()
        self.set_status(f"Chargement: {season}/{league_file} ...")
        QApplication.processEvents()

        data = self.fetch_json(season, league_file)
        if data is None:
            self.set_status("Échec du chargement.")
            return

        name = data.get("name", league_file)
        self.fixtures = data.get("matches", [])

        self.matches_list.clear()
        for m in self.fixtures:
            self.matches_list.addItem(QListWidgetItem(format_match_label(m)))

        if self.fixtures:
            self.matches_list.setCurrentRow(0)
        else:
            self.current_match = None
            self.fd_table.setRowCount(0)
            self.fd_table.insertRow(0)
            self.fd_table.setItem(0, 0, QTableWidgetItem("Football-data.co.uk"))
            self.fd_table.setItem(0, 1, QTableWidgetItem("Aucun match."))

        self.set_status(f"{name} — {len(self.fixtures)} match(s) chargés.")

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
        self.fd_table.setRowCount(0)
        if not self.current_match:
            self.fd_table.insertRow(0)
            self.fd_table.setItem(0, 0, QTableWidgetItem("Football-data.co.uk"))
            self.fd_table.setItem(0, 1, QTableWidgetItem("Sélectionne un match."))
            return
        season = self.season_combo.currentText()
        league_file = self.league_combo.currentData()
        if not league_file:
            self.fd_table.insertRow(0)
            self.fd_table.setItem(0, 0, QTableWidgetItem("Football-data.co.uk"))
            self.fd_table.setItem(0, 1, QTableWidgetItem("Aucune ligue sélectionnée."))
            return
        url = football_data_csv_url(season, league_file)
        if not url:
            self.fd_table.insertRow(0)
            self.fd_table.setItem(0, 0, QTableWidgetItem("Football-data.co.uk"))
            self.fd_table.setItem(0, 1, QTableWidgetItem("Non disponible pour cette ligue/saison (mapping football-data.co.uk manquant)."))
            return
        m = self.current_match
        home_name = m.get("team1") or (m.get("teams") or {}).get("home", {}).get("name") or "Home"
        away_name = m.get("team2") or (m.get("teams") or {}).get("away", {}).get("name") or "Away"
        date = m.get("date")
        self.fd_table.insertRow(0)
        self.fd_table.setItem(0, 0, QTableWidgetItem("Chargement..."))
        self.fd_table.setItem(0, 1, QTableWidgetItem(url))
        QApplication.processEvents()
        try:
            rows = fetch_csv_rows(url)
            found = find_fd_row_for_match(rows, date, home_name, away_name)
            self.fd_table.setRowCount(0)
            if not found:
                self.fd_table.insertRow(0)
                self.fd_table.setItem(0, 0, QTableWidgetItem("Football-data.co.uk"))
                self.fd_table.setItem(0, 1, QTableWidgetItem("Aucun match correspondant trouvé dans le CSV."))
                return
            items = format_fd_info(found)
            if not items:
                self.fd_table.insertRow(0)
                self.fd_table.setItem(0, 0, QTableWidgetItem("Football-data.co.uk"))
                self.fd_table.setItem(0, 1, QTableWidgetItem("Aucune info trouvée."))
                return
            for k, v in items:
                r = self.fd_table.rowCount()
                self.fd_table.insertRow(r)
                self.fd_table.setItem(r, 0, QTableWidgetItem(str(k)))
                self.fd_table.setItem(r, 1, QTableWidgetItem(str(v)))
        except Exception as e:
            self.fd_table.setRowCount(0)
            self.fd_table.insertRow(0)
            self.fd_table.setItem(0, 0, QTableWidgetItem("Erreur"))
            self.fd_table.setItem(0, 1, QTableWidgetItem(str(e)))

    def update_odds_table(self):
        self.table.setRowCount(0)
        if not self.current_match:
            return
        if not self.catalog.strategies:
            return
        strategy_id = self.strategy_combo.currentData()
        strategy = self.catalog.get(strategy_id) if strategy_id else self.catalog.probability_model()
        if strategy is None:
            return

        m = self.current_match
        home_name = m.get("team1") or (m.get("teams") or {}).get("home", {}).get("name") or "Home"
        away_name = m.get("team2") or (m.get("teams") or {}).get("away", {}).get("name") or "Away"
        date = m.get("date")
        prob_strategy = self.catalog.probability_model()
        if not (prob_strategy and prob_strategy.analyze):
            self.table.insertRow(0)
            self.table.setItem(0, 0, QTableWidgetItem("Info"))
            self.table.setItem(0, 1, QTableWidgetItem("-"))
            self.table.setItem(0, 2, QTableWidgetItem("-"))
            self.table.setItem(0, 3, QTableWidgetItem("Aucune stratégie d'analyse (analyze)."))
            return
        try:
            analysis = prob_strategy.analyze(
                fixtures=self.fixtures,
                home_id=None,
                away_id=None,
                home_name=home_name,
                away_name=away_name,
                before_date=date,
            )
        except Exception as e:
            self.table.insertRow(0)
            self.table.setItem(0, 0, QTableWidgetItem("Erreur"))
            self.table.setItem(0, 1, QTableWidgetItem("-"))
            self.table.setItem(0, 2, QTableWidgetItem("-"))
            self.table.setItem(0, 3, QTableWidgetItem(str(e)))
            return
        probs = analysis.get("probabilities") if isinstance(analysis, dict) else None
        if not probs:
            return
        try:
            rows = strategy.run(probs, context={"match": m})
        except Exception as e:
            self.table.insertRow(0)
            self.table.setItem(0, 0, QTableWidgetItem("Erreur"))
            self.table.setItem(0, 1, QTableWidgetItem("-"))
            self.table.setItem(0, 2, QTableWidgetItem("-"))
            self.table.setItem(0, 3, QTableWidgetItem(str(e)))
            return
        for r in rows:
            row_idx = self.table.rowCount()
            self.table.insertRow(row_idx)
            self.table.setItem(row_idx, 0, QTableWidgetItem(str(r.get("label", ""))))
            self.table.setItem(row_idx, 1, QTableWidgetItem(str(r.get("prob", ""))))
            self.table.setItem(row_idx, 2, QTableWidgetItem(str(r.get("odd", ""))))
            self.table.setItem(row_idx, 3, QTableWidgetItem(str(r.get("signal", "") or "")))
        self.details_label.setText(f"{home_name} vs {away_name} ({date}) — Stratégie: {strategy.name}")

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
        home_name = m.get("team1") or (m.get("teams") or {}).get("home", {}).get("name") or "Home"
        away_name = m.get("team2") or (m.get("teams") or {}).get("away", {}).get("name") or "Away"
        date = m.get("date")

        prob_strategy = self.catalog.probability_model()
        if not (prob_strategy and prob_strategy.analyze):
            QMessageBox.warning(self, "Stratégie", "Aucune stratégie avec analyze() trouvée (ex: Poisson/Ratio).")
            return None
        try:
            analysis = prob_strategy.analyze(
                fixtures=self.fixtures,
                home_id=None,
                away_id=None,
                home_name=home_name,
                away_name=away_name,
                before_date=date,
            )
        except Exception as e:
            QMessageBox.warning(self, "Erreur analyse", f"Erreur lors du calcul des probabilités:\n{e}")
            return None
        probs = analysis.get("probabilities") if isinstance(analysis, dict) else None
        if not probs:
            QMessageBox.warning(self, "Probabilités", "Impossible de calculer les probabilités pour ce match.")
            return None

        try:
            rows = strategy.run(probs, context={"match": m})
        except Exception as e:
            QMessageBox.warning(self, "Erreur stratégie", f"Erreur lors de l'évaluation:\n{e}")
            return None

        payload = {
            "match": {"home": home_name, "away": away_name, "date": date},
            "model": analysis,
            "strategy": {"id": strategy.id, "name": strategy.name, "rows": rows},
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
            QMessageBox.warning(self, "Ollama", str(e))
            return
        if not models:
            QMessageBox.warning(self, "Ollama", "Aucun modèle Ollama trouvé. Installe un modèle (ex: ollama pull llama3).")
            return

        context = ai_module.build_context(payload)
        default_prompt = ai_module.DEFAULT_PROMPT + "\n\n--- DONNEES ---\n" + context

        dlg = QDialog(self)
        dlg.setWindowTitle("Analyse IA (Ollama)")
        dlg.resize(900, 700)
        layout = QVBoxLayout(dlg)

        layout.addWidget(QLabel("Modèle Ollama:"))
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
                QMessageBox.warning(dlg, "Ollama", "Choisis un modèle.")
                return
            if not prompt:
                QMessageBox.warning(dlg, "Prompt", "Le prompt est vide.")
                return
            result_edit.setPlainText("Analyse en cours (Ollama)...")
            btn_run.setEnabled(False)
            btn_cancel.setEnabled(False)
            QApplication.processEvents()
            try:
                result = ai_module.ask_ollama(prompt, model=model)
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
