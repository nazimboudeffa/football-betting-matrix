"""Strategie prudente : cote juste augmentee d'une marge de securite."""

from football_betting_matrix.strategies import base_rows

NAME = "Cote prudente"
DESCRIPTION = "Marches >= 45 % de probabilite, cote juste + 5 % de marge."

MIN_PROB = 0.45
MARGIN = 0.05


def evaluate(probabilities: dict, context: dict | None = None) -> list[dict]:
    rows = [row for row in base_rows(probabilities) if row["prob"] >= MIN_PROB]
    for row in rows:
        row["odd"] = round(row["fair_odd"] * (1 + MARGIN), 2)
        row["signal"] = f"Marge +{MARGIN * 100:.0f} %"
        row["highlight"] = True
    rows.sort(key=lambda row: row["odd"], reverse=True)
    return rows
