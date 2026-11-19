"""Tests de non-regression pour le changement de date dans la page Matchs."""

from __future__ import annotations

import os
import unittest
from datetime import date, timedelta
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from football_betting_matrix.ui.pages.matches import MatchesPage


class _Service:
    """Service minimal : les chargements sont simules par les tests."""

    def __init__(self) -> None:
        self.config = SimpleNamespace(seasons=(2026, 2025))

    def tracked_leagues(self) -> list[dict]:
        return []

    def settings(self) -> dict:
        return {"default_season": 2026}


class MatchesDateNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _page(self):
        page = MatchesPage(_Service())
        started: list = []

        def fake_run_task(_fn, on_success, on_error=None, progress=None, busy_text=""):
            started.append(on_success)
            return True

        page.run_task = fake_run_task
        return page, started

    def test_date_change_during_load_is_reloaded(self) -> None:
        page, started = self._page()
        today_iso = date.today().isoformat()
        tomorrow = date.today() + timedelta(days=1)

        page.load_live()
        self.assertEqual(len(started), 1)
        self.assertEqual(page._live_requested_date, today_iso)

        # Memorise la nouvelle date sans ecraser le chargement en cours.
        page.set_date(tomorrow)
        self.assertEqual(len(started), 1)
        self.assertTrue(page._live_pending_reload)

        # La fin du chargement d'aujourd'hui declenche celui de demain.
        started[0]({"items": []})
        self.assertEqual(len(started), 2)
        self.assertEqual(page._live_requested_date, tomorrow.isoformat())
        self.assertFalse(page._live_pending_reload)

    def test_date_change_after_load_starts_immediately(self) -> None:
        page, started = self._page()
        tomorrow = date.today() + timedelta(days=1)

        page.load_live()
        started[0]({"items": []})
        self.assertEqual(len(started), 1)

        page.set_date(tomorrow)
        self.assertEqual(len(started), 2)
        self.assertEqual(page._live_requested_date, tomorrow.isoformat())
        self.assertFalse(page._live_pending_reload)


if __name__ == "__main__":
    unittest.main()
