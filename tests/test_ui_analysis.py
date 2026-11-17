"""Tests des helpers de la page Analyse."""

from __future__ import annotations

import unittest

from football_betting_matrix.ui.pages.analysis import latest_played_fixture


class LatestPlayedFixtureTests(unittest.TestCase):
    @staticmethod
    def fixture(name: str, finished: bool, home=None, away=None) -> dict:
        return {
            "home": {"name": f"{name} domicile"},
            "away": {"name": f"{name} exterieur"},
            "status": {"finished": finished},
            "goals": {"home": home, "away": away},
        }

    def test_returns_most_recent_finished_fixture(self) -> None:
        upcoming = self.fixture("A venir", False)
        played = self.fixture("Joue", True, 2, 1)
        older = self.fixture("Ancien", True, 0, 0)
        self.assertIs(latest_played_fixture([upcoming, played, older]), played)

    def test_returns_none_when_no_finished_fixture(self) -> None:
        upcoming = self.fixture("A venir", False)
        self.assertIsNone(latest_played_fixture([upcoming]))

    def test_ignores_finished_without_score(self) -> None:
        incomplete = self.fixture("Sans score", True, None, None)
        self.assertIsNone(latest_played_fixture([incomplete]))


if __name__ == "__main__":
    unittest.main()
