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

    def test_additional_csv_league_can_be_tracked(self) -> None:
        self.service.add_league({"id": 40})
        league = next(
            item for item in self.service.tracked_leagues() if int(item["id"]) == 40
        )
        self.assertEqual(league["name"], "Championship")
        self.assertEqual(league["country"], "England")

    def test_added_league_goes_on_top_and_removed_league_goes_to_bottom(self) -> None:
        self.service.add_league({"id": 40})
        self.service.add_league({"id": 72})
        tracked_ids = [int(item["id"]) for item in self.service.tracked_leagues()]
        self.assertEqual(tracked_ids[:2], [72, 40])

        available_ids = [item["id"] for item in self.service.available_leagues()]
        self.assertNotIn(40, available_ids)
        self.assertNotIn(72, available_ids)

        self.service.remove_league(40)
        tracked_ids = [int(item["id"]) for item in self.service.tracked_leagues()]
        self.assertEqual(tracked_ids[0], 72)
        self.assertNotIn(40, tracked_ids)
        self.assertEqual(self.service.available_leagues()[-1]["id"], 40)

    def test_restore_defaults_resets_order(self) -> None:
        self.service.add_league({"id": 40})
        self.service.restore_default_leagues()
        tracked_ids = [int(item["id"]) for item in self.service.tracked_leagues()]
        self.assertEqual(tracked_ids, [140, 39, 78, 135, 61, 2])
        self.assertNotIn(2, [item["id"] for item in self.service.available_leagues()])


class RefereeProfileTests(unittest.TestCase):
    def test_profile_uses_only_past_matches_and_both_sides(self) -> None:
        fixtures = [
            {
                "date": "2026-08-15T20:00:00",
                "referee": "Duval",
                "stats": {"yellow_cards": {"home": 2, "away": 3}, "fouls": {"home": 10, "away": 12}},
            },
            {
                "date": "2026-08-22T20:00:00",
                "referee": "DUVAL",
                "stats": {"yellow_cards": {"home": 4, "away": 1}, "fouls": {"home": 8, "away": 9}},
            },
            {
                "date": "2026-08-29T20:00:00",
                "referee": "Duval",
                "stats": {"yellow_cards": {"home": 9, "away": 9}},
            },
            {
                "date": "2026-08-16T20:00:00",
                "referee": "Martin",
                "stats": {"yellow_cards": {"home": 7, "away": 7}},
            },
        ]
        profile = DataService._referee_profile(fixtures, "Duval", "2026-08-29")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["matches"], 2)
        self.assertEqual(profile["yellow_per_game"], 5.0)
        self.assertEqual(profile["fouls_per_game"], 19.5)

    def test_profile_without_referee_returns_none(self) -> None:
        self.assertIsNone(DataService._referee_profile([], "", None))


if __name__ == "__main__":
    unittest.main()
