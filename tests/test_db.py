"""Tests de la base SQLite locale (cache, reglages, paris)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from betting_matrix.db import Database


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmp.name) / "test.db")

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def test_cache_roundtrip_and_staleness(self) -> None:
        self.db.cache_set("fixtures:1", "fixtures", {"date": "2026-11-13"}, [{"id": 1}], 60)
        cached = self.db.cache_get("fixtures:1")
        self.assertIsNotNone(cached)
        assert cached is not None
        self.assertTrue(cached["fresh"])
        self.assertEqual(cached["data"], [{"id": 1}])

        self.db.cache_set("old:1", "fixtures", {}, [], -5)
        stale = self.db.cache_get("old:1")
        self.assertIsNotNone(stale)
        assert stale is not None
        self.assertFalse(stale["fresh"])
        self.assertIsNone(self.db.cache_get("old:1", allow_stale=False))

        stats = self.db.cache_stats()
        self.assertEqual(stats["entries"], 2)
        self.assertEqual(stats["fresh"], 1)
        self.assertEqual(stats["stale"], 1)
        self.assertGreater(stats["bytes"], 0)

        self.assertEqual(self.db.cache_clear("fixtures:"), 1)
        self.assertEqual(self.db.cache_stats()["entries"], 1)

    def test_settings_are_merged_with_defaults(self) -> None:
        defaults = {
            "default_season": 2024,
            "tracked_leagues": [{"id": 140, "name": "La Liga"}],
        }
        settings = self.db.get_settings(defaults)
        self.assertEqual(settings["default_season"], 2024)
        self.assertEqual(settings["tracked_leagues"][0]["id"], 140)

        settings["default_season"] = 2023
        self.db.save_settings(settings)
        reloaded = self.db.get_settings(defaults)
        self.assertEqual(reloaded["default_season"], 2023)

    def test_prediction_lifecycle_and_stats(self) -> None:
        prediction = self.db.add_prediction(
            {
                "fixture_id": 123,
                "league_id": 140,
                "league_name": "La Liga",
                "home": "Barcelone",
                "away": "Madrid",
                "market": "1X2",
                "selection": "Victoire domicile",
                "odds": 2.0,
                "model_prob": 0.60,
                "edge": 0.10,
                "kickoff": "2024-05-01T20:00:00+00:00",
            }
        )
        self.assertEqual(self.db.list_predictions()[0]["id"], prediction["id"])
        stats = self.db.prediction_stats()
        self.assertEqual(stats["pending"], 1)
        self.assertEqual(stats["total"], 1)
        self.assertAlmostEqual(stats["average_edge"], 0.10, places=4)
        self.assertEqual(stats["value_count"], 1)

        updated = self.db.update_prediction(
            prediction["id"],
            {
                "status": "won",
                "home": "FC Barcelone",
                "away": "Real Madrid",
                "league_name": "LaLiga",
            },
        )
        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(updated["status"], "won")
        self.assertEqual(updated["home"], "FC Barcelone")
        self.assertEqual(updated["league_name"], "LaLiga")
        self.assertIsNotNone(updated["settled_at"])

        stats = self.db.prediction_stats()
        self.assertEqual(stats["won"], 1)
        self.assertEqual(stats["win_rate"], 1.0)
        self.assertNotIn("bankroll", stats)

        self.assertTrue(self.db.delete_prediction(prediction["id"]))
        self.assertIsNone(self.db.get_prediction(prediction["id"]))

    def test_legacy_api_tables_are_removed(self) -> None:
        with self.db._lock:
            self.db._conn.execute("CREATE TABLE usage (id INTEGER PRIMARY KEY)")
            self.db._conn.execute("CREATE TABLE api_log (id INTEGER PRIMARY KEY)")
            self.db._conn.commit()
        reopened = Database(self.db.path)
        try:
            names = {
                row[0]
                for row in reopened._conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        finally:
            reopened.close()
        self.assertNotIn("usage", names)
        self.assertNotIn("api_log", names)


if __name__ == "__main__":
    unittest.main()
