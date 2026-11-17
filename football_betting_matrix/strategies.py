"""Chargement et validation des strategies de calcul de cotes utilisateur.

Une strategie est un module Python place dans le dossier ``user_strategies`` a la
racine du projet. Elle expose ``NAME``, ``DESCRIPTION`` et une fonction
``evaluate(probabilities, context=None)`` qui renvoie une liste de cotes calculees.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .analysis import model_odds
from .config import DEFAULT_ODDS_STRATEGY

DEFAULT_STRATEGY_ID = DEFAULT_ODDS_STRATEGY
STRATEGY_DIR_NAME = "user_strategies"

Evaluate = Callable[[dict, dict | None], list[dict]]
REQUIRED_FIELDS = ("label", "prob", "odd")


@dataclass(frozen=True)
class Strategy:
    id: str
    name: str
    description: str
    evaluate: Evaluate

    def run(self, probabilities: dict, context: dict | None = None) -> list[dict]:
        """Appelle la strategie et ne garde que les lignes exploitables par l'UI."""
        raw = self.evaluate(probabilities, context or {})
        rows: list[dict] = []
        for item in raw or []:
            if not isinstance(item, dict):
                continue
            if not all(field in item for field in REQUIRED_FIELDS):
                continue
            try:
                row = {
                    **item,
                    "prob": float(item["prob"]),
                    "odd": float(item["odd"]),
                }
            except (TypeError, ValueError):
                continue
            row.setdefault("fair_odd", None)
            row.setdefault("signal", None)
            row.setdefault("highlight", False)
            rows.append(row)
        return rows


@dataclass(frozen=True)
class StrategyCatalog:
    strategies: tuple[Strategy, ...] = ()
    errors: tuple[str, ...] = ()

    def get(self, strategy_id: str) -> Strategy | None:
        for strategy in self.strategies:
            if strategy.id == strategy_id:
                return strategy
        return self.strategies[0] if self.strategies else None


def base_rows(probabilities: dict) -> list[dict]:
    """Cotes justes de base (1 / probabilite) reutilisables par les strategies."""
    rows = model_odds(probabilities)
    for row in rows:
        row["signal"] = None
        row["highlight"] = False
    return rows


def strategies_dir(config_root: Path) -> Path:
    return Path(config_root) / STRATEGY_DIR_NAME


def _load_module(path: Path, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Import de module impossible pour {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def load_strategies(directory: Path) -> StrategyCatalog:
    """Charge les modules de ``directory`` en ignorant ceux qui sont invalides."""
    directory = Path(directory)
    if not directory.is_dir():
        return StrategyCatalog()

    strategies: list[Strategy] = []
    errors: list[str] = []
    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module_name = f"_user_strategy_{path.stem}"
        try:
            module = _load_module(path, module_name)
            name = getattr(module, "NAME", None)
            evaluate = getattr(module, "evaluate", None)
            if not isinstance(name, str) or not name.strip():
                raise ValueError("NAME manquant ou invalide")
            if not callable(evaluate):
                raise ValueError("fonction evaluate() manquante")
            strategies.append(
                Strategy(
                    id=path.stem,
                    name=name.strip(),
                    description=str(getattr(module, "DESCRIPTION", "") or ""),
                    evaluate=evaluate,
                )
            )
        except Exception as exc:  # une strategie utilisateur ne doit pas casser l'UI
            errors.append(f"{path.name} : {exc}")

    return StrategyCatalog(tuple(strategies), tuple(errors))
