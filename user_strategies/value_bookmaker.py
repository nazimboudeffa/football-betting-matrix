"""Stratégie Value Bookmaker : compare les probabilités du modèle aux cotes réelles.

Les cotes proviennent du contexte fourni par l'interface (football-data.co.uk) :
meilleure cote disponible par marché et cote moyenne du marché.
"""

from __future__ import annotations

from football_betting_matrix.strategies import MARKET_LABELS

NAME = "Value Bookmaker"
DESCRIPTION = (
    "Compare les probabilités du modèle à la meilleure cote bookmaker disponible "
    "(football-data.co.uk). Signal = avantage espéré (probabilité × cote - 1)."
)

MIN_EDGE = 0.0  # seuil pour afficher un signal VALUE


def evaluate(probabilities: dict, context: dict | None = None) -> list[dict]:
    odds = ((context or {}).get("odds") or {})
    rows: list[dict] = []

    for key, label in MARKET_LABELS.items():
        prob = probabilities.get(key)
        entry = odds.get(key) or {}
        best = entry.get("best")
        if not prob or float(prob) <= 0 or not best:
            continue

        try:
            bookmaker = str(best[0])
            market_odd = float(best[1])
            prob = float(prob)
        except (TypeError, ValueError, IndexError):
            continue

        if market_odd <= 1.0:
            continue

        fair_odd = round(1.0 / prob, 3)
        edge = prob * market_odd - 1.0
        has_value = edge >= MIN_EDGE

        rows.append(
            {
                "key": key,
                "label": label,
                "prob": round(prob, 4),
                "odd": fair_odd,
                "fair_odd": fair_odd,
                "market_odd": market_odd,
                "bookmaker": bookmaker,
                "signal": (
                    f"VALUE {edge:+.1%} ({bookmaker})"
                    if has_value
                    else f"Pas de value ({edge:+.1%}, {bookmaker})"
                ),
                "highlight": has_value,
            }
        )

    return rows
