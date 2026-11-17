"""Tests du modele Poisson et des calculs de value bets."""

from __future__ import annotations

import math
import unittest

from football_betting_matrix.analysis import (
    analyze_match,
    build_season_stats,
    implied_probability,
    odds_summary,
    parse_odds,
    poisson_matrix,
    probabilities_from_matrix,
    value_bets,
)


def fixture(
    fixture_id: int,
    home_id: int,
    away_id: int,
    home_goals: int,
    away_goals: int,
    date: str = "2024-01-01T20:00:00+00:00",
) -> dict:
    return {
        "fixture": {"id": fixture_id, "date": date, "status": {"short": "FT"}},
        "league": {"id": 140, "season": 2024},
        "teams": {
            "home": {"id": home_id, "name": f"Equipe {home_id}"},
            "away": {"id": away_id, "name": f"Equipe {away_id}"},
        },
        "goals": {"home": home_goals, "away": away_goals},
    }


def normalized_fixture(
    fixture_id: int,
    home_id: int,
    away_id: int,
    home_goals: int,
    away_goals: int,
    date: str = "2024-01-01T20:00:00",
) -> dict:
    """Forme renvoyee par DataService.normalize_fixture (sans bloc teams)."""
    return {
        "id": fixture_id,
        "date": date,
        "status": {"short": "FT"},
        "league": {"id": 140, "season": 2024},
        "home": {"id": home_id, "name": f"Equipe {home_id}"},
        "away": {"id": away_id, "name": f"Equipe {away_id}"},
        "goals": {"home": home_goals, "away": away_goals},
    }


class PoissonTests(unittest.TestCase):
    def test_matrix_is_normalised(self) -> None:
        matrix = poisson_matrix(1.4, 1.1)
        total = sum(sum(row) for row in matrix)
        self.assertAlmostEqual(total, 1.0, places=9)

    def test_probabilities_are_coherent(self) -> None:
        probs = probabilities_from_matrix(poisson_matrix(1.8, 0.9))
        self.assertAlmostEqual(probs["home"] + probs["draw"] + probs["away"], 1.0, places=9)
        self.assertAlmostEqual(probs["over25"] + probs["under25"], 1.0, places=9)
        self.assertAlmostEqual(probs["btts_yes"] + probs["btts_no"], 1.0, places=9)
        self.assertGreater(probs["home"], probs["away"])
        self.assertEqual(len(probs["scores"]), 8)
        self.assertGreaterEqual(probs["scores"][0]["prob"], probs["scores"][-1]["prob"])


class SeasonStatsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixtures = [
            fixture(1, 1, 2, 2, 0, "2024-01-01T20:00:00+00:00"),
            fixture(2, 3, 1, 1, 1, "2024-01-08T20:00:00+00:00"),
            fixture(3, 2, 3, 0, 3, "2024-01-15T20:00:00+00:00"),
        ]

    def test_aggregation(self) -> None:
        stats = build_season_stats(self.fixtures)
        self.assertEqual(stats["matches"], 3)
        self.assertEqual(stats["teams"][1]["played"], 2)
        self.assertEqual(stats["teams"][1]["gf"], 3)
        self.assertEqual(stats["teams"][1]["ga"], 1)
        self.assertEqual(stats["teams"][1]["form"], ["V", "N"])

    def test_before_date_filters(self) -> None:
        stats = build_season_stats(self.fixtures, before_date="2024-01-15")
        self.assertEqual(stats["matches"], 2)
        self.assertEqual(stats["teams"][3]["played"], 1)

    def test_normalized_fixture_shape_is_supported(self) -> None:
        fixtures = [
            normalized_fixture(1, 1, 2, 2, 0, "2024-01-01T20:00:00"),
            normalized_fixture(2, 3, 1, 1, 1, "2024-01-08T20:00:00"),
            normalized_fixture(3, 2, 3, 0, 3, "2024-01-15T20:00:00"),
        ]
        stats = build_season_stats(fixtures, before_date="2024-01-15")
        self.assertEqual(stats["matches"], 2)
        model = analyze_match(
            fixtures,
            1,
            2,
            "Equipe 1",
            "Equipe 2",
            before_date="2024-01-15",
        )
        self.assertTrue(model["known_home"])
        self.assertTrue(model["known_away"])
        self.assertGreater(model["lambda_home"], 0)
        self.assertGreater(model["lambda_away"], 0)

    def test_analysis_with_known_and_unknown_teams(self) -> None:
        model = analyze_match(self.fixtures, 1, 2, "Equipe 1", "Equipe 2")
        self.assertTrue(model["known_home"])
        self.assertTrue(model["known_away"])
        probabilities = model["probabilities"]
        self.assertAlmostEqual(
            probabilities["home"] + probabilities["draw"] + probabilities["away"],
            1.0,
            places=3,
        )
        self.assertGreater(model["lambda_home"], 0)
        self.assertGreater(model["lambda_away"], 0)

        unknown = analyze_match(self.fixtures, 99, 2, "Inconnue", "Equipe 2")
        self.assertFalse(unknown["known_home"])
        self.assertGreater(unknown["lambda_home"], 0)


class OddsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.response = [
            {
                "bookmakers": [
                    {
                        "name": "Book A",
                        "bets": [
                            {
                                "id": 1,
                                "values": [
                                    {"value": "Home", "odd": "2.10"},
                                    {"value": "Draw", "odd": "3.40"},
                                    {"value": "Away", "odd": "3.60"},
                                ],
                            },
                            {
                                "id": 5,
                                "values": [
                                    {"value": "Over 2.5", "odd": "1.90"},
                                    {"value": "Under 2.5", "odd": "1.95"},
                                ],
                            },
                            {
                                "id": 8,
                                "values": [
                                    {"value": "Yes", "odd": "1.80"},
                                    {"value": "No", "odd": "2.00"},
                                ],
                            },
                        ],
                    },
                    {
                        "name": "Book B",
                        "bets": [
                            {
                                "id": 1,
                                "values": [
                                    {"value": "Home", "odd": "2.25"},
                                    {"value": "Draw", "odd": "3.20"},
                                    {"value": "Away", "odd": "3.70"},
                                ],
                            }
                        ],
                    },
                ]
            }
        ]

    def test_parse_odds_keeps_best_price(self) -> None:
        parsed = parse_odds(self.response)
        odds = parsed["odds"]
        self.assertEqual(odds["home"]["odd"], 2.25)
        self.assertEqual(odds["home"]["bookmaker"], "Book B")
        self.assertEqual(odds["draw"]["odd"], 3.4)
        self.assertEqual(odds["away"]["odd"], 3.7)
        self.assertAlmostEqual(odds["over25"]["odd"], 1.9, places=3)
        self.assertEqual(parsed["bookmaker_count"], 2)

    def test_value_bets(self) -> None:
        bets = value_bets(
            {"home": 0.60, "draw": 0.25, "away": 0.15},
            {"home": 2.0, "draw": 3.0, "away": 6.0},
        )
        self.assertEqual(len(bets), 3)
        by_key = {bet["key"]: bet for bet in bets}
        self.assertTrue(by_key["home"]["recommended"])
        self.assertAlmostEqual(by_key["home"]["edge"], 0.10, places=4)
        self.assertAlmostEqual(by_key["away"]["edge"], -0.0167, places=4)
        self.assertFalse(by_key["away"]["recommended"])
        self.assertEqual(bets[0]["key"], "home")
        self.assertAlmostEqual(by_key["home"]["fair_odd"], 1.67, places=2)
        self.assertNotIn("kelly", by_key["home"])

    def test_implied_probability_and_margin(self) -> None:
        self.assertAlmostEqual(implied_probability(2.0), 0.5)
        summary = odds_summary(
            {
                "home": {"odd": 2.0},
                "draw": {"odd": 3.5},
                "away": {"odd": 4.0},
            }
        )
        self.assertAlmostEqual(summary["overround"], 1.0357, places=4)
        self.assertAlmostEqual(summary["margin"], 0.0357, places=4)


class MathSanityTests(unittest.TestCase):
    def test_poisson_mass(self) -> None:
        matrix = poisson_matrix(0.0, 0.0)
        self.assertAlmostEqual(matrix[0][0], 1.0, places=12)
        self.assertTrue(math.isclose(sum(sum(row) for row in matrix), 1.0, rel_tol=1e-12))


if __name__ == "__main__":
    unittest.main()
