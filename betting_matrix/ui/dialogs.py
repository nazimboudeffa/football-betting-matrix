"""Boites de dialogue partagees."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ..service import DataService
from ..theme import ACCENT, MUTED, TEXT


class PredictionDialog(QDialog):
    """Formulaire d'enregistrement d'un pronostic (sans mise ni bankroll)."""

    MARKETS = [
        ("1X2", "1X2 (resultat du match)"),
        ("OU25", "Plus / Moins de 2.5 buts"),
        ("BTTS", "Les deux equipes marquent"),
        ("AUTRE", "Autre marche"),
    ]
    SELECTIONS = {
        "1X2": ["Victoire domicile", "Match nul", "Victoire exterieur"],
        "OU25": ["Plus de 2.5 buts", "Moins de 2.5 buts"],
        "BTTS": ["Les deux equipes marquent : Oui", "Les deux equipes marquent : Non"],
        "AUTRE": [""],
    }
    MARKET_KEYS = {
        "1X2": {"Victoire domicile": "home", "Match nul": "draw", "Victoire exterieur": "away"},
        "OU25": {"Plus de 2.5 buts": "over25", "Moins de 2.5 buts": "under25"},
        "BTTS": {
            "Les deux equipes marquent : Oui": "btts_yes",
            "Les deux equipes marquent : Non": "btts_no",
        },
    }

    def __init__(
        self,
        service: DataService,
        prefill: dict | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.service = service
        self.prefill = prefill or {}
        self.setWindowTitle("Nouveau pronostic")
        self.setMinimumWidth(480)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)

        title = QLabel("Enregistrer un pronostic")
        title.setStyleSheet(f"font-size: 15pt; font-weight: 700; color: {TEXT};")
        root.addWidget(title)
        subtitle = QLabel(
            "Aucune mise, aucun capital : l'application enregistre uniquement votre "
            "pronostic, la cote eventuelle et son resultat."
        )
        subtitle.setObjectName("small")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        match_card = QWidget()
        match_layout = QVBoxLayout(match_card)
        match_layout.setContentsMargins(14, 12, 14, 12)
        match_layout.setSpacing(4)
        match_card.setStyleSheet(
            "background: #0d1520; border: 1px solid #1e2d42; border-radius: 10px;"
        )
        self.match_label = QLabel(
            self.prefill.get("match_label")
            or f"{self.prefill.get('home', '')} — {self.prefill.get('away', '')}".strip(" —")
            or "Match libre"
        )
        self.match_label.setStyleSheet(f"font-size: 11pt; font-weight: 600; color: {TEXT};")
        self.match_label.setWordWrap(True)
        match_layout.addWidget(self.match_label)
        league_line = " • ".join(
            part
            for part in [
                self.prefill.get("league_name", ""),
                service.format_kickoff(self.prefill.get("kickoff")),
            ]
            if part
        )
        self.league_label = QLabel(league_line or "Aucune competition selectionnee")
        self.league_label.setObjectName("small")
        match_layout.addWidget(self.league_label)
        root.addWidget(match_card)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.home_edit = QLineEdit(self.prefill.get("home", ""))
        self.home_edit.setPlaceholderText("Equipe a domicile")
        form.addRow("Domicile", self.home_edit)
        self.away_edit = QLineEdit(self.prefill.get("away", ""))
        self.away_edit.setPlaceholderText("Equipe a l'exterieur")
        form.addRow("Exterieur", self.away_edit)
        self.league_edit = QLineEdit(self.prefill.get("league_name", ""))
        self.league_edit.setPlaceholderText("Competition (optionnelle)")
        form.addRow("Competition", self.league_edit)

        self.market_combo = QComboBox()
        for key, label in self.MARKETS:
            self.market_combo.addItem(label, key)
        form.addRow("Marche", self.market_combo)

        self.selection_combo = QComboBox()
        self.selection_combo.setEditable(True)
        self.selection_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        form.addRow("Selection", self.selection_combo)

        self.odds_spin = QDoubleSpinBox()
        self.odds_spin.setRange(0.0, 1000.0)
        self.odds_spin.setDecimals(2)
        self.odds_spin.setSingleStep(0.05)
        self.odds_spin.setSpecialValueText("—")
        self.odds_spin.setValue(float(self.prefill.get("odds") or 0.0))
        form.addRow("Cote (optionnelle)", self.odds_spin)

        self.note_edit = QLineEdit(self.prefill.get("note") or "")
        self.note_edit.setPlaceholderText("Note optionnelle (analyse, condition, etc.)")
        form.addRow("Note", self.note_edit)
        root.addLayout(form)

        self.model_label = QLabel("Probabilite modele : non disponible")
        self.model_label.setObjectName("small")
        self.model_label.setWordWrap(True)
        root.addWidget(self.model_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        save_button.setText("Enregistrer")
        save_button.setObjectName("primary")
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_button.setText("Annuler")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.market_combo.currentIndexChanged.connect(self._on_market_changed)
        self.home_edit.textChanged.connect(self._update_match_label)
        self.away_edit.textChanged.connect(self._update_match_label)

        self._apply_prefill()

    def _apply_prefill(self) -> None:
        market = self.prefill.get("market") or "1X2"
        index = self.market_combo.findData(market)
        if index >= 0:
            self.market_combo.setCurrentIndex(index)
        self._on_market_changed()
        selection = self.prefill.get("selection")
        if selection:
            idx = self.selection_combo.findText(selection)
            if idx >= 0:
                self.selection_combo.setCurrentIndex(idx)
            else:
                self.selection_combo.setEditText(selection)
        model_prob = self.prefill.get("model_prob")
        edge = self.prefill.get("edge")
        if model_prob is not None:
            parts = [f"Probabilite modele : {float(model_prob) * 100:.1f} %"]
            if edge is not None:
                parts.append(f"edge : {float(edge) * 100:+.1f} pts")
            self.model_label.setText(" • ".join(parts))
            self.model_label.setStyleSheet(
                f"color: {ACCENT}; font-family: 'Cascadia Mono', Consolas, monospace;"
            )
        else:
            self.model_label.setStyleSheet(f"color: {MUTED};")

    def _update_match_label(self) -> None:
        home = self.home_edit.text().strip()
        away = self.away_edit.text().strip()
        if home or away:
            self.match_label.setText(f"{home or '?'} — {away or '?'}")

    def _on_market_changed(self) -> None:
        market = self.market_combo.currentData()
        self.selection_combo.blockSignals(True)
        self.selection_combo.clear()
        self.selection_combo.addItems(self.SELECTIONS.get(market, [""]))
        self.selection_combo.setEditText(self.selection_combo.itemText(0))
        self.selection_combo.blockSignals(False)

    def _accept(self) -> None:
        if not self.home_edit.text().strip() or not self.away_edit.text().strip():
            QMessageBox.warning(
                self, "Equipes manquantes", "Renseignez les deux equipes du match."
            )
            return
        if not self.selection_combo.currentText().strip():
            QMessageBox.warning(self, "Selection manquante", "Choisissez ou saisissez une selection.")
            return
        self.accept()

    def get_prediction(self) -> dict:
        market_key = self.market_combo.currentData()
        selection = self.selection_combo.currentText().strip()
        model_key = self.MARKET_KEYS.get(market_key, {}).get(selection)
        prefill_prob = self.prefill.get("model_prob")
        odds = round(self.odds_spin.value(), 2)
        return {
            "fixture_id": self.prefill.get("fixture_id"),
            "league_id": self.prefill.get("league_id"),
            "league_name": self.league_edit.text().strip(),
            "home": self.home_edit.text().strip(),
            "away": self.away_edit.text().strip(),
            "kickoff": self.prefill.get("kickoff"),
            "market": market_key,
            "selection": selection,
            "odds": odds if odds > 1.01 else None,
            "model_prob": prefill_prob if model_key else None,
            "edge": self.prefill.get("edge") if model_key else None,
            "note": self.note_edit.text().strip(),
            "status": "pending",
        }
