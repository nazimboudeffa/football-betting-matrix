"""Page Mes pronostics : suivi local des pronostics et de la performance du modele."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ...service import DataService
from ...theme import ACCENT, AMBER, BLUE, MUTED, RED
from ..base import BasePage
from ..common import configure_table
from ..dialogs import PredictionDialog
from ..widgets import Badge, EmptyState, StatCard, table_item

MARKET_SHORT = {
    "1X2": "1X2",
    "OU25": "O/U 2.5",
    "BTTS": "BTTS",
    "AUTRE": "Autre",
}

STATUS_LABELS = {
    "pending": "En attente",
    "won": "Gagne",
    "lost": "Perdu",
    "void": "Annule",
}


class PredictionsPage(BasePage):
    predictions_changed = pyqtSignal()

    def __init__(self, service: DataService, parent=None):
        super().__init__(service, parent)
        self._selected_id: str | None = None

        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        self.card_total = StatCard("Pronostics", "—", "Suivis localement", ACCENT, "▦")
        self.card_pending = StatCard("En attente", "—", "Resultat a renseigner", AMBER, "◷")
        self.card_winrate = StatCard("Reussite", "—", "Gagnes / decides", BLUE, "✓")
        self.card_edge = StatCard("Edge moyen", "—", "Modele face aux cotes", ACCENT, "↗")
        self.card_odds = StatCard("Cote moyenne", "—", "Pronostics avec cote", BLUE, "◈")
        for card in (
            self.card_total,
            self.card_pending,
            self.card_winrate,
            self.card_edge,
            self.card_odds,
        ):
            stats_row.addWidget(card, 1)
        self.root.addLayout(stats_row)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.filter_combo = QComboBox()
        for label, value in (
            ("Tous les pronostics", "all"),
            ("En attente", "pending"),
            ("Gagnes", "won"),
            ("Perdus", "lost"),
            ("Annules", "void"),
        ):
            self.filter_combo.addItem(label, value)
        self.filter_combo.currentIndexChanged.connect(lambda _i: self.refresh_data())
        toolbar.addWidget(self.filter_combo)

        toolbar.addStretch()
        self.btn_won = QPushButton("Marquer gagne")
        self.btn_won.clicked.connect(lambda: self._settle("won"))
        self.btn_lost = QPushButton("Marquer perdu")
        self.btn_lost.clicked.connect(lambda: self._settle("lost"))
        self.btn_void = QPushButton("Annuler")
        self.btn_void.clicked.connect(lambda: self._settle("void"))
        self.btn_delete = QPushButton("Supprimer")
        self.btn_delete.setObjectName("danger")
        self.btn_delete.clicked.connect(self._delete)
        for button in (self.btn_won, self.btn_lost, self.btn_void, self.btn_delete):
            toolbar.addWidget(button)
            button.setEnabled(False)

        export_button = QPushButton("Exporter CSV")
        export_button.clicked.connect(self._export_csv)
        toolbar.addWidget(export_button)
        new_button = QPushButton("Nouveau pronostic")
        new_button.setObjectName("primary")
        new_button.clicked.connect(self._new_prediction)
        toolbar.addWidget(new_button)
        self.root.addLayout(toolbar)

        self.stack = QStackedWidget()
        self.table = QTableWidget()
        configure_table(
            self.table,
            [
                "Date",
                "Match",
                "Competition",
                "Marche",
                "Selection",
                "Cote",
                "Proba modele",
                "Edge",
                "Statut",
            ],
            stretch_columns=[1, 4],
            row_height=42,
        )
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.cellDoubleClicked.connect(lambda _r, _c: self._edit_selected())
        self.stack.addWidget(self.table)
        self.empty_holder = QWidget()
        self.empty_layout = QVBoxLayout(self.empty_holder)
        self.empty_layout.setContentsMargins(0, 0, 0, 0)
        self.stack.addWidget(self.empty_holder)
        self.root.addWidget(self.stack, 1)

        self.refresh_data()

    # --------------------------------------------------------------- lifecycle

    def on_show(self) -> None:
        self.refresh_data()

    # ------------------------------------------------------------------ data

    def refresh_data(self) -> None:
        stats = self.service.prediction_stats()
        self.card_total.set_value(
            str(stats["total"]),
            f"{stats['settled']} regle(s) • {stats['value_count']} edge positif",
        )
        self.card_pending.set_value(
            str(stats["pending"]),
            "Resultat a renseigner",
        )
        self.card_winrate.set_value(
            f"{stats['win_rate'] * 100:.1f} %",
            f"{stats['won']} gagne(s) / {stats['lost']} perdu(s)",
        )
        average_edge = stats["average_edge"] * 100
        self.card_edge.set_value(
            f"{average_edge:+.1f} %",
            f"{stats['value_count']} pronostic(s) a edge positif",
            ACCENT if average_edge >= 0 else RED,
        )
        self.card_odds.set_value(
            f"{stats['average_odds']:.2f}" if stats["average_odds"] else "—",
            "Cote moyenne des pronostics",
        )

        status = self.filter_combo.currentData()
        predictions = self.service.db.list_predictions(None if status == "all" else status)
        self._render_table(predictions)
        self._selected_id = None
        self._selection_changed()

    def _render_table(self, predictions: list[dict]) -> None:
        self.table.setRowCount(0)
        if not predictions:
            all_predictions = self.service.db.list_predictions()
            if all_predictions:
                title = "Aucun pronostic pour ce filtre"
                text = "Changez le filtre ou ajoutez un nouveau pronostic."
            else:
                title = "Aucun pronostic enregistre"
                text = (
                    "Ajoutez un pronostic depuis un match ou manuellement. "
                    "L'application ne suit ni argent ni mise."
                )
            self._show_empty(
                title,
                text,
                "Ajouter un pronostic" if not all_predictions else None,
                self._new_prediction,
            )
            return
        self.stack.setCurrentIndex(0)
        self.table.setRowCount(len(predictions))
        for row, prediction in enumerate(predictions):
            moment = prediction.get("kickoff") or prediction.get("created_at")
            first = table_item(self._format_date(moment))
            first.setData(Qt.ItemDataRole.UserRole, prediction["id"])
            first.setToolTip(prediction.get("note") or "")
            self.table.setItem(row, 0, first)

            match_text = f"{prediction['home']} — {prediction['away']}"
            match_item = table_item(match_text, bold=True)
            match_item.setToolTip(prediction.get("note") or match_text)
            self.table.setItem(row, 1, match_item)
            self.table.setItem(
                row, 2, table_item(prediction.get("league_name") or "—", color=MUTED)
            )
            self.table.setItem(
                row, 3, table_item(MARKET_SHORT.get(prediction["market"], prediction["market"]))
            )
            self.table.setItem(row, 4, table_item(prediction["selection"]))
            odd = prediction.get("odds")
            self.table.setItem(
                row, 5, table_item(f"{odd:.2f}" if odd is not None else "—", align_right=True)
            )

            model_prob = prediction.get("model_prob")
            edge = prediction.get("edge")
            if model_prob is not None:
                model_text = f"{float(model_prob) * 100:.0f} %"
            else:
                model_text = "—"
            self.table.setItem(row, 6, table_item(model_text, align_right=True))
            if edge is not None:
                edge_color = ACCENT if float(edge) > 0 else RED
                edge_text = f"{float(edge) * 100:+.1f} pts"
            else:
                edge_color = MUTED
                edge_text = "—"
            self.table.setItem(
                row, 7, table_item(edge_text, align_right=True, color=edge_color)
            )

            status = prediction["status"]
            kind = {"pending": "blue", "won": "green", "lost": "red", "void": "gray"}.get(
                status, "gray"
            )
            badge = Badge(STATUS_LABELS.get(status, status), kind)
            wrapper = QWidget()
            wrap_layout = QHBoxLayout(wrapper)
            wrap_layout.setContentsMargins(4, 0, 4, 0)
            wrap_layout.addStretch()
            wrap_layout.addWidget(badge)
            wrap_layout.addStretch()
            self.table.setCellWidget(row, 8, wrapper)

    # --------------------------------------------------------------- actions

    def _selection_changed(self) -> None:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        prediction_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        self._selected_id = prediction_id
        prediction = self.service.db.get_prediction(prediction_id) if prediction_id else None
        pending = bool(prediction and prediction["status"] == "pending")
        self.btn_won.setEnabled(pending)
        self.btn_lost.setEnabled(pending)
        self.btn_void.setEnabled(pending)
        self.btn_delete.setEnabled(bool(prediction))

    def _settle(self, status: str) -> None:
        if not self._selected_id:
            return
        prediction = self.service.db.update_prediction(self._selected_id, {"status": status})
        if prediction:
            self.toast.emit(
                f"Pronostic mis a jour : {prediction['selection']} → "
                f"{STATUS_LABELS.get(status, status)}"
            )
            self.refresh_data()
            self.predictions_changed.emit()

    def _delete(self) -> None:
        if not self._selected_id:
            return
        prediction = self.service.db.get_prediction(self._selected_id)
        if not prediction:
            return
        if not self.confirm(
            "Supprimer le pronostic",
            f"Supprimer definitivement le pronostic « {prediction['selection']} » "
            f"({prediction['home']} — {prediction['away']}) ?",
        ):
            return
        if self.service.db.delete_prediction(self._selected_id):
            self.toast.emit("Pronostic supprime.")
            self.refresh_data()
            self.predictions_changed.emit()

    def _new_prediction(self) -> None:
        dialog = PredictionDialog(self.service, {}, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            prediction = dialog.get_prediction()
            self.service.db.add_prediction(prediction)
            odd_text = f" @ {prediction['odds']:.2f}" if prediction.get("odds") else ""
            self.toast.emit(f"Pronostic enregistre : {prediction['selection']}{odd_text}")
            self.refresh_data()
            self.predictions_changed.emit()

    def _edit_selected(self) -> None:
        if not self._selected_id:
            return
        prediction = self.service.db.get_prediction(self._selected_id)
        if not prediction or prediction["status"] != "pending":
            return
        prefill = {
            "fixture_id": prediction.get("fixture_id"),
            "league_id": prediction.get("league_id"),
            "league_name": prediction.get("league_name"),
            "home": prediction.get("home"),
            "away": prediction.get("away"),
            "kickoff": prediction.get("kickoff"),
            "match_label": f"{prediction['home']} — {prediction['away']}",
            "market": prediction.get("market") or "1X2",
            "selection": prediction.get("selection"),
            "odds": prediction.get("odds"),
            "model_prob": prediction.get("model_prob"),
            "edge": prediction.get("edge"),
            "note": prediction.get("note"),
        }
        dialog = PredictionDialog(self.service, prefill, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_prediction()
            self.service.db.update_prediction(
                self._selected_id,
                {
                    "odds": data["odds"],
                    "selection": data["selection"],
                    "market": data["market"],
                    "note": data["note"],
                    "home": data["home"],
                    "away": data["away"],
                    "league_name": data["league_name"],
                },
            )
            self.toast.emit("Pronostic modifie.")
            self.refresh_data()
            self.predictions_changed.emit()

    def _export_csv(self) -> None:
        predictions = self.service.db.list_predictions()
        if not predictions:
            self.toast.emit("Aucun pronostic a exporter.")
            return
        default = str(Path.home() / "betting-matrix-pronostics.csv")
        path, _filter = QFileDialog.getSaveFileName(
            self, "Exporter les pronostics", default, "Fichier CSV (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle, delimiter=";")
                writer.writerow(
                    [
                        "Date",
                        "Domicile",
                        "Exterieur",
                        "Competition",
                        "Marche",
                        "Selection",
                        "Cote",
                        "Probabilite modele",
                        "Edge",
                        "Statut",
                        "Note",
                    ]
                )
                for prediction in predictions:
                    odd = prediction.get("odds")
                    writer.writerow(
                        [
                            prediction.get("kickoff") or prediction.get("created_at"),
                            prediction["home"],
                            prediction["away"],
                            prediction.get("league_name"),
                            MARKET_SHORT.get(prediction["market"], prediction["market"]),
                            prediction["selection"],
                            f"{odd:.2f}" if odd is not None else "",
                            f"{prediction['model_prob']:.4f}"
                            if prediction.get("model_prob") is not None
                            else "",
                            f"{prediction['edge']:.4f}"
                            if prediction.get("edge") is not None
                            else "",
                            STATUS_LABELS.get(prediction["status"], prediction["status"]),
                            prediction.get("note") or "",
                        ]
                    )
            self.toast.emit(f"Export CSV reussi : {path}")
        except OSError as exc:
            self.show_error("Export impossible", str(exc))

    # ------------------------------------------------------------------ utils

    @staticmethod
    def _format_date(value: str | None) -> str:
        if not value:
            return "—"
        try:
            return datetime.fromisoformat(value).astimezone().strftime("%d/%m/%y")
        except (ValueError, TypeError):
            return str(value)[:10]

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
