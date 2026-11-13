"""Tests de l'orchestration : migration des reglages et sources gratuites."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from betting_matrix.config import DEFAULT_LEAGUES, Config
from betting_matrix.db import Database
from betting_matrix.errors import SourceError
from betting_matrix.service import DataService


class SettingsMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.config = Config(
            root_dir=root,
            data_dir=root,
            db_path=root / "test.db",
            seasons=(2026, 2025, 2024),
            default_season=2026,
        )
        self.db = Database(self.config.db_path)
        self.db.save_settings(
            {
                "default_season": 2024,
                "tracked_leagues": [
                    {"id": 140, "name": "La Liga", "country": "Spain", "default": True},
                    {"id": 78, "name": "Bundesliga", "country": "Germany", "default": True},
                    {"id": 61, "name": "Ligue 1", "country": "France", "default": True},
                    {"id": 2, "name": "UEFA Champions League", "country": "World", "default": True},
                    {"id": 39, "name": "Premier League", "country": "England", "default": False},
                ],
                "bankroll": 1000.0,
                "currency": "EUR",
                "default_stake": 10.0,
            }
        )
        self.service = DataService(self.config, self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def test_legacy_settings_are_migrated(self) -> None:
        settings = self.service.settings()
        self.assertEqual(settings["default_season"], 2026)
        self.assertNotIn("bankroll", settings)
        self.assertNotIn("currency", settings)
        self.assertNotIn("default_stake", settings)
        self.assertTrue(settings["sources_migrated"])
        self.assertTrue(settings["free_leagues_migrated"])
        self.assertTrue(settings["serie_a_ligue1_migrated"])

        ids = [int(league["id"]) for league in settings["tracked_leagues"]]
        self.assertEqual(ids, [140, 78, 61, 2, 135])
        self.assertNotIn(39, ids)

    def test_already_migrated_install_receives_serie_a_and_ligue_1(self) -> None:
        self.db.save_settings(
            {
                "default_season": 2026,
                "tracked_leagues": [
                    {"id": 140, "name": "La Liga", "country": "Spain", "default": True},
                    {"id": 78, "name": "Bundesliga", "country": "Germany", "default": True},
                    {"id": 2, "name": "UEFA Champions League", "country": "World", "default": True},
                ],
                "sources_migrated": True,
                "free_leagues_migrated": True,
            }
        )
        settings = self.service.settings()
        ids = [int(league["id"]) for league in settings["tracked_leagues"]]
        self.assertIn(135, ids)
        self.assertIn(61, ids)
        self.assertTrue(settings["serie_a_ligue1_migrated"])

    def test_migration_is_one_time(self) -> None:
        self.service.settings()
        settings = self.service.settings()
        settings["tracked_leagues"] = [
            league for league in settings["tracked_leagues"] if int(league["id"]) != 135
        ]
        self.service.save_settings(settings)

        self.assertNotIn(135, [int(item["id"]) for item in self.service.tracked_leagues()])

    def test_explicit_season_is_kept_after_migration(self) -> None:
        self.service.update_settings({"default_season": 2024})
        self.assertEqual(self.service.settings()["default_season"], 2024)

    def test_add_league_rejects_unsupported_competition(self) -> None:
        with self.assertRaises(SourceError):
            self.service.add_league({"id": 39, "name": "Premier League"})

    def test_default_leagues_include_serie_a_and_ligue_1(self) -> None:
        ids = {int(league["id"]) for league in DEFAULT_LEAGUES}
        self.assertEqual(ids, {140, 78, 135, 61, 2})


if __name__ == "__main__":
    unittest.main()
