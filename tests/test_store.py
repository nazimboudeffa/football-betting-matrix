"""Tests du stockage leger : cache memoire et reglages JSON."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from betting_matrix.store import JsonSettingsStore, MemoryCache


class MemoryCacheTests(unittest.TestCase):
    def test_cache_roundtrip_and_staleness(self) -> None:
        cache = MemoryCache()
        cache.cache_set("fixtures:1", "fixtures", {"date": "2026-11-13"}, [{"id": 1}], 60)
        cached = cache.cache_get("fixtures:1")
        self.assertIsNotNone(cached)
        assert cached is not None
        self.assertTrue(cached["fresh"])
        self.assertEqual(cached["data"], [{"id": 1}])

        cache.cache_set("old:1", "fixtures", {}, [], -5)
        stale = cache.cache_get("old:1")
        self.assertIsNotNone(stale)
        assert stale is not None
        self.assertFalse(stale["fresh"])
        self.assertIsNone(cache.cache_get("old:1", allow_stale=False))

        stats = cache.cache_stats()
        self.assertEqual(stats["entries"], 2)
        self.assertEqual(stats["fresh"], 1)
        self.assertEqual(stats["stale"], 1)
        self.assertGreater(stats["bytes"], 0)

        self.assertEqual(cache.cache_clear("fixtures:"), 1)
        self.assertEqual(cache.cache_stats()["entries"], 1)

    def test_cache_list_returns_metadata(self) -> None:
        cache = MemoryCache()
        cache.cache_set(
            "standings:1", "standings", {"league": 140}, [], 60, meta={"label": "La Liga"}
        )
        entries = cache.cache_list()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["label"], "La Liga")
        self.assertTrue(entries[0]["fresh"])

    def test_cache_is_not_shared_between_instances(self) -> None:
        first = MemoryCache()
        first.cache_set("key", "endpoint", {}, [1], 60)
        self.assertIsNone(MemoryCache().cache_get("key"))


class JsonSettingsStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "settings.json"
        self.store = JsonSettingsStore(self.path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_defaults_are_merged_with_stored_values(self) -> None:
        defaults = {
            "default_season": 2024,
            "tracked_leagues": [{"id": 140, "name": "La Liga"}],
        }
        settings = self.store.get_settings(defaults)
        self.assertEqual(settings["default_season"], 2024)
        self.assertEqual(settings["tracked_leagues"][0]["id"], 140)

        settings["default_season"] = 2023
        self.store.save_settings(settings)
        reloaded = JsonSettingsStore(self.path).get_settings(defaults)
        self.assertEqual(reloaded["default_season"], 2023)

    def test_invalid_file_falls_back_to_defaults(self) -> None:
        self.path.write_text("{invalid", encoding="utf-8")
        store = JsonSettingsStore(self.path)
        settings = store.get_settings(
            {"default_season": 2026, "tracked_leagues": [{"id": 140}]}
        )
        self.assertEqual(settings["default_season"], 2026)

    def test_saved_file_is_valid_json(self) -> None:
        self.store.save_settings({"default_season": 2026, "tracked_leagues": [{"id": 39}]})
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["default_season"], 2026)


if __name__ == "__main__":
    unittest.main()
