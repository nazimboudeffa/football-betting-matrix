"""Strategie de reference : cote juste = 1 / probabilite du modele."""

from football_betting_matrix.strategies import base_rows

NAME = "Cote juste"
DESCRIPTION = "Cote = 1 / probabilite du modele, sans marge ni filtre."


def evaluate(probabilities: dict, context: dict | None = None) -> list[dict]:
    rows = base_rows(probabilities)
    for row in rows:
        row["signal"] = "Reference"
    return rows
