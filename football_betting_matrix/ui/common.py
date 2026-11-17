"""Helpers communs aux pages."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QAbstractItemView, QComboBox, QHeaderView, QTableWidget

from ..theme import MUTED, TEXT
from .widgets import Badge


def populate_leagues(
    combo: QComboBox,
    leagues: list[dict],
    include_all: bool = False,
    all_label: str = "Toutes les ligues",
) -> None:
    current = combo.currentData()
    combo.blockSignals(True)
    combo.clear()
    if include_all:
        combo.addItem(all_label, None)
    for league in leagues:
        combo.addItem(league.get("name") or f"Ligue {league.get('id')}", int(league.get("id")))
    if current is not None:
        index = combo.findData(current)
        if index >= 0:
            combo.setCurrentIndex(index)
    combo.blockSignals(False)


def populate_seasons(combo: QComboBox, seasons: tuple[int, ...], default: int | None = None) -> None:
    combo.blockSignals(True)
    combo.clear()
    for season in seasons:
        combo.addItem(f"Saison {season}", int(season))
    if default is not None:
        index = combo.findData(int(default))
        if index >= 0:
            combo.setCurrentIndex(index)
    combo.blockSignals(False)


def configure_table(
    table: QTableWidget,
    headers: list[str],
    stretch_columns: list[int] | None = None,
    row_height: int = 40,
    sortable: bool = False,
) -> None:
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(row_height)
    table.setShowGrid(False)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    table.setWordWrap(False)
    header = table.horizontalHeader()
    header.setHighlightSections(False)
    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    for column in stretch_columns or []:
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
    if not sortable:
        table.setSortingEnabled(False)


def status_badge(fixture: dict) -> Badge:
    status = fixture.get("status") or {}
    short = status.get("short") or "NS"
    label = status.get("label") or short
    if short in {"FT", "AET", "PEN"}:
        return Badge(label, "gray")
    if short in {"1H", "2H", "HT", "ET", "BT", "P", "LIVE"}:
        return Badge(label, "red")
    if short in {"PST", "CANC", "ABD", "SUSP", "INT"}:
        return Badge(label, "amber")
    if short in {"AWD", "WO"}:
        return Badge(label, "purple")
    return Badge(label, "blue")


def score_text(fixture: dict) -> str:
    goals = fixture.get("goals") or {}
    home = goals.get("home")
    away = goals.get("away")
    if home is None or away is None:
        return "—"
    return f"{home} - {away}"


def format_odd(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}"


def form_badge_text(form: str) -> str:
    mapping = {"V": "V", "N": "N", "D": "D", "W": "V", "L": "D"}
    return " ".join(mapping.get(letter.upper(), letter.upper()) for letter in (form or "")[:5])


def make_table_font(size: float = 9.0) -> QFont:
    font = QFont("Segoe UI")
    font.setPointSizeF(size)
    return font


def secondary_label(text: str):
    from PyQt6.QtWidgets import QLabel

    label = QLabel(text)
    label.setStyleSheet(f"color: {MUTED}; font-size: 8.5pt;")
    return label


def primary_label(text: str, bold: bool = False):
    from PyQt6.QtWidgets import QLabel

    label = QLabel(text)
    weight = "font-weight: 600;" if bold else ""
    label.setStyleSheet(f"color: {TEXT}; {weight}")
    return label
