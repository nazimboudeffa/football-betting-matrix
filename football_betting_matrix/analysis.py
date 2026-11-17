"""Helpers generiques lies aux cotes.

Le calcul des probabilites (modele de Poisson) n'est plus ici : il vit dans
``user_strategies/poisson.py`` et est expose par les strategies utilisateur.
Le coeur ne garde que le parsing des cotes bookmaker et les helpers de marge.
"""

from __future__ import annotations

from typing import Any


def _odd(value: Any) -> float | None:
    try:
        odd = float(value)
    except (TypeError, ValueError):
        return None
    if 1.0 < odd < 1000.0:
        return odd
    return None


def _keep_best(bucket: dict[str, dict], key: str, odd: float | None, bookmaker: str) -> None:
    if odd is None:
        return
    current = bucket.get(key)
    if current is None or odd > current["odd"]:
        bucket[key] = {"odd": round(odd, 3), "bookmaker": bookmaker}


def parse_odds(response: list[dict]) -> dict:
    """Extrait les meilleures cotes 1X2 / O-U 2.5 / BTTS parmi les bookmakers."""
    best: dict[str, dict] = {}
    bookmakers: set[str] = set()
    entries = 0
    for fixture_entry in response or []:
        for book in fixture_entry.get("bookmakers") or []:
            bookmaker = book.get("name") or "Bookmaker"
            entries += 1
            bookmakers.add(bookmaker)
            for bet in book.get("bets") or []:
                bet_id = bet.get("id")
                values = bet.get("values") or []
                if bet_id == 1:
                    for value in values:
                        label = str(value.get("value", "")).strip().lower()
                        odd = _odd(value.get("odd"))
                        if label == "home":
                            _keep_best(best, "home", odd, bookmaker)
                        elif label == "draw":
                            _keep_best(best, "draw", odd, bookmaker)
                        elif label == "away":
                            _keep_best(best, "away", odd, bookmaker)
                elif bet_id == 5:
                    for value in values:
                        label = str(value.get("value", "")).strip().lower()
                        odd = _odd(value.get("odd"))
                        if label in {"over 2.5", "over 2.5 goals"}:
                            _keep_best(best, "over25", odd, bookmaker)
                        elif label in {"under 2.5", "under 2.5 goals"}:
                            _keep_best(best, "under25", odd, bookmaker)
                elif bet_id == 8:
                    for value in values:
                        label = str(value.get("value", "")).strip().lower()
                        odd = _odd(value.get("odd"))
                        if label == "yes":
                            _keep_best(best, "btts_yes", odd, bookmaker)
                        elif label == "no":
                            _keep_best(best, "btts_no", odd, bookmaker)
    return {
        "odds": best,
        "bookmakers": sorted(bookmakers),
        "bookmaker_count": len(bookmakers),
        "entries": entries,
    }


def implied_probability(odd: float) -> float:
    return 1.0 / odd if odd > 1 else 0.0


def odds_summary(odds: dict[str, dict]) -> dict:
    """Marge du bookmaker sur le 1X2 (surcote)."""
    keys = ("home", "draw", "away")
    if not all(k in odds for k in keys):
        return {"margin": None, "overround": None}
    implied = [implied_probability(odds[k]["odd"]) for k in keys]
    total = sum(implied)
    return {"margin": round(total - 1.0, 4), "overround": round(total, 4)}


def _first_odd(*values: Any) -> float | None:
    for value in values:
        odd = _odd(value)
        if odd is not None:
            return odd
    return None


def market_summary(market: dict | None) -> dict:
    """Decrit le marche 1X2 d'un match sans produire de probabilite de modele.

    Les probabilites renvoyees sont celles implicitement contenues dans les
    cotes, avec la marge du bookmaker retiree. Elles servent de reference a
    l'analyse ; les strategies restent seules a decider d'un quelconque calcul.
    """
    if not market:
        return {}
    one_two_x = market.get("one_two_x") or {}
    totals = market.get("totals") or {}
    asian = market.get("asian") or {}
    sources = {
        "pinnacle": one_two_x.get("pinnacle") or {},
        "closing": one_two_x.get("closing") or {},
        "consensus": one_two_x.get("consensus") or {},
        "opening": one_two_x.get("opening") or {},
        "best": one_two_x.get("best") or {},
    }
    compact = {
        name: {key: _odd(value) for key, value in source.items()}
        for name, source in sources.items()
    }
    reference_name = None
    reference = None
    for name in ("pinnacle", "closing", "consensus"):
        candidate = compact.get(name) or {}
        if all(candidate.get(key) is not None for key in ("home", "draw", "away")):
            reference_name, reference = name, candidate
            break

    result: dict[str, Any] = {
        "reference": reference_name,
        "opening": compact.get("opening") or {},
        "closing": compact.get("closing") or {},
        "pinnacle": compact.get("pinnacle") or {},
        "consensus": compact.get("consensus") or {},
        "best": compact.get("best") or {},
        "asian": {
            "line": asian.get("line"),
            "home": _odd(asian.get("home")),
            "away": _odd(asian.get("away")),
        },
        "totals": {
            name: {
                "over25": _odd((value or {}).get("over25")),
                "under25": _odd((value or {}).get("under25")),
            }
            for name, value in totals.items()
        },
        "probabilities": {},
        "margin": None,
        "movement": {},
    }
    if reference:
        raw = [1.0 / reference[key] for key in ("home", "draw", "away")]
        total = sum(raw)
        if total > 0:
            result["probabilities"] = {
                key: round((1.0 / reference[key]) / total, 4)
                for key in ("home", "draw", "away")
            }
            result["margin"] = round(total - 1.0, 4)
    opening = result["opening"]
    closing = result["closing"]
    for key in ("home", "draw", "away"):
        if opening.get(key) and closing.get(key):
            result["movement"][key] = round(
                (closing[key] - opening[key]) / opening[key], 4
            )
    return result
