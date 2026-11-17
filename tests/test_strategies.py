"""Tests du chargement des strategies de calcul de cotes utilisateur."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from football_betting_matrix.config import ROOT_DIR, Config
from football_betting_matrix.service import DataService
from football_betting_matrix.store import JsonSettingsStore, MemoryCache
from football_betting_matrix.strategies import (
    DEFAULT_STRATEGY_ID,
    Strategy,
    load_strategies,
    model_odds,
)

PROBABILITIES = {
    "home": 0.52,
    "draw": 0.25,
    "away": 0.23,
    "over25": 0.58,
    "under25": 0.42,
}


class StrategyLoadingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_load_valid_modules_and_ignore_invalid_ones(self) -> None:
        (self.directory / "alpha.py").write_text(
            'NAME = "Alpha"\nDESCRIPTION = "Premiere"\n'
            "def evaluate(probabilities, context=None):\n    return []\n",
            encoding="utf-8",
        )
        (self.directory / "beta.py").write_text(
            'NAME = "Beta"\n'
            "def evaluate(probabilities, context=None):\n    return []\n",
            encoding="utf-8",
        )
        (self.directory / "bad.py").write_text('NAME = "Sans evaluate"\n', encoding="utf-8")
        (self.directory / "broken.py").write_text("def evaluate(:\n", encoding="utf-8")
        (self.directory / "_private.py").write_text("NAME = 'Ignore'\n", encoding="utf-8")

        catalog = load_strategies(self.directory)

        self.assertEqual([strategy.id for strategy in catalog.strategies], ["alpha", "beta"])
        self.assertEqual([strategy.name for strategy in catalog.strategies], ["Alpha", "Beta"])
        self.assertEqual(len(catalog.errors), 2)
        self.assertTrue(any("bad.py" in error for error in catalog.errors))
        self.assertTrue(any("broken.py" in error for error in catalog.errors))

    def test_missing_directory_gives_empty_catalog(self) -> None:
        catalog = load_strategies(self.directory / "absent")
        self.assertEqual(catalog.strategies, ())
        self.assertIsNone(catalog.get("whatever"))

    def test_get_falls_back_to_first_strategy(self) -> None:
        strategy = Strategy("one", "Un", "", lambda probabilities, context=None: [])
        catalog = load_strategies(self.directory)
        catalog = type(catalog)((strategy,), ())
        self.assertIs(catalog.get("inconnu"), strategy)


class StrategyRunTests(unittest.TestCase):
    def test_run_keeps_only_usable_rows_and_adds_defaults(self) -> None:
        def evaluate(probabilities, context=None):
            return [
                {"label": "OK", "prob": 0.5, "odd": "2.0"},
                {"label": "Champs manquants", "prob": 0.5},
                {"label": "Nombre invalide", "prob": 0.5, "odd": "x"},
                "pas un dictionnaire",
            ]

        rows = Strategy("test", "Test", "", evaluate).run(PROBABILITIES)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["label"], "OK")
        self.assertEqual(rows[0]["prob"], 0.5)
        self.assertEqual(rows[0]["odd"], 2.0)
        self.assertIsNone(rows[0]["fair_odd"])
        self.assertIsNone(rows[0]["signal"])
        self.assertFalse(rows[0]["highlight"])

    def test_run_propagates_context(self) -> None:
        seen = {}

        def evaluate(probabilities, context=None):
            seen.update(context or {})
            return []

        Strategy("test", "Test", "", evaluate).run(PROBABILITIES, {"marge": 0.1})
        self.assertEqual(seen, {"marge": 0.1})


class BundledStrategyTests(unittest.TestCase):
    def setUp(self) -> None:
        catalog = load_strategies(ROOT_DIR / "user_strategies")
        self.catalog = catalog
        self.poisson = catalog.get("poisson_pur")
        self.strict = catalog.get("poisson_prudent")
        self.classement = catalog.get("classement_pur")

    def test_bundled_strategies_are_loaded_without_error(self) -> None:
        ids = {strategy.id for strategy in self.catalog.strategies}
        self.assertTrue({"classement_pur", "poisson_prudent", "poisson_pur"}.issubset(ids))
        self.assertEqual(self.catalog.errors, ())

    def test_poisson_matches_the_core_model_odds(self) -> None:
        self.assertIsNotNone(self.poisson)
        expected = model_odds(PROBABILITIES)
        actual = self.poisson.run(PROBABILITIES)

        self.assertEqual([row["label"] for row in actual], [row["label"] for row in expected])
        self.assertEqual([row["odd"] for row in actual], [row["odd"] for row in expected])
        self.assertTrue(all(row["signal"] == "Poisson" for row in actual))
        self.assertFalse(any(row["highlight"] for row in actual))

    def test_strict_filters_by_probability_adds_margin_and_sorts_by_odd(self) -> None:
        self.assertIsNotNone(self.strict)
        rows = self.strict.run(PROBABILITIES)

        self.assertEqual([row["label"] for row in rows], ["Victoire domicile", "Plus de 2.5 buts"])
        self.assertEqual([row["odd"] for row in rows], [2.02, 1.81])
        self.assertEqual([round(row["fair_odd"], 2) for row in rows], [1.92, 1.72])
        self.assertTrue(all(row["signal"] == "Marge +5 %" for row in rows))
        self.assertTrue(all(row["highlight"] for row in rows))

    def test_classement_pur_uses_fair_odds_and_a_ranking_signal(self) -> None:
        self.assertIsNotNone(self.classement)
        expected = model_odds(PROBABILITIES)
        rows = self.classement.run(PROBABILITIES)

        self.assertEqual([row["key"] for row in rows], [row["key"] for row in expected])
        self.assertEqual([row["odd"] for row in rows], [row["odd"] for row in expected])
        self.assertTrue(all(row["signal"] == "Classement" for row in rows))
        self.assertFalse(any(row["highlight"] for row in rows))

    def test_bundled_strategies_provide_the_probability_model(self) -> None:
        self.assertIsNotNone(self.catalog.probability_model())
        for strategy in self.catalog.strategies:
            self.assertIsNotNone(strategy.analyze, strategy.id)


class CoreSeparationTests(unittest.TestCase):
    def test_poisson_model_lives_outside_the_core(self) -> None:
        import football_betting_matrix.analysis as analysis

        for name in (
            "analyze_match",
            "build_season_stats",
            "poisson_matrix",
            "probabilities_from_matrix",
        ):
            self.assertFalse(hasattr(analysis, name), name)

    def test_strategy_files_are_self_contained(self) -> None:
        folder = ROOT_DIR / "user_strategies"
        names = ("poisson_pur.py", "poisson_prudent.py", "classement_pur.py")
        for name in names:
            source = (folder / name).read_text(encoding="utf-8")
            self.assertIn("def analyze_match(", source, name)
            self.assertIn("def evaluate(", source, name)
            for other in (item.removesuffix(".py") for item in names):
                if other != name.removesuffix(".py"):
                    self.assertNotIn(f"from {other} import", source, name)


class ServiceStrategyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.config = Config(
            root_dir=ROOT_DIR,
            data_dir=root,
            settings_path=root / "settings.json",
        )
        self.store = JsonSettingsStore(self.config.settings_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _service(self) -> DataService:
        return DataService(self.config, MemoryCache(), self.store)

    def test_service_loads_bundled_strategies(self) -> None:
        service = self._service()
        ids = {strategy.id for strategy in service.strategies.strategies}
        self.assertTrue({"classement_pur", "poisson_prudent", "poisson_pur"}.issubset(ids))

    def test_selection_is_saved_as_a_json_setting(self) -> None:
        service = self._service()
        self.assertEqual(service.value_strategy_id(), DEFAULT_STRATEGY_ID)

        service.set_value_strategy("classement_pur")
        self.assertEqual(self._service().value_strategy_id(), "classement_pur")

    def test_reload_strategies_reads_the_folder_again(self) -> None:
        service = self._service()
        before = {strategy.id for strategy in service.strategies.strategies}
        catalog = service.reload_strategies()

        self.assertEqual({strategy.id for strategy in catalog.strategies}, before)
        self.assertEqual({strategy.id for strategy in service.strategies.strategies}, before)


if __name__ == "__main__":
    unittest.main()
