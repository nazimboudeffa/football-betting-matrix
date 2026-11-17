"""Tests de l'orchestration : reglages JSON et ligues suivies."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from football_betting_matrix.config import DEFAULT_LEAGUES, Config
from football_betting_matrix.errors import SourceError
from football_betting_matrix.service import DataService
from football_betting_matrix.store import JsonSettingsStore, MemoryCache


class SettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.config = Config(
            root_dir=root,
            data_dir=root,
            settings_path=root / "settings.json",
            seasons=(2026, 2025, 2024),
            default_season=2026,
        )
        self.store = JsonSettingsStore(self.config.settings_path)
        self.service = DataService(self.config, MemoryCache(), self.store)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_default_settings_cover_all_free_leagues(self) -> None:
        settings = self.service.settings()
        self.assertEqual(settings["default_season"], 2026)
        ids = [int(league["id"]) for league in settings["tracked_leagues"]]
        self.assertEqual(ids, [140, 39, 78, 135, 61, 2])

    def test_settings_survive_a_new_service(self) -> None:
        self.service.update_settings({"default_season": 2025})
        self.service.remove_league(2)
        reloaded = DataService(self.config, MemoryCache(), JsonSettingsStore(self.config.settings_path))
        settings = reloaded.settings()
        self.assertEqual(settings["default_season"], 2025)
        self.assertNotIn(2, [int(league["id"]) for league in settings["tracked_leagues"]])

    def test_add_and_remove_league(self) -> None:
        self.service.remove_league(39)
        self.assertNotIn(39, [int(item["id"]) for item in self.service.tracked_leagues()])
        self.service.add_league({"id": 39})
        self.assertIn(39, [int(item["id"]) for item in self.service.tracked_leagues()])

    def test_add_league_rejects_unsupported_competition(self) -> None:
        with self.assertRaises(SourceError):
            self.service.add_league({"id": 999, "name": "Ligue inconnue"})

    def test_default_leagues_include_premier_league_serie_a_and_ligue_1(self) -> None:
        ids = {int(league["id"]) for league in DEFAULT_LEAGUES}
        self.assertEqual(ids, {140, 39, 78, 135, 61, 2})


if __name__ == "__main__":
    unittest.main()
