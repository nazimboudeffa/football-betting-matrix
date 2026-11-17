"""Tests du modele Classement Pur (strategie autonome)."""

from __future__ import annotations

import unittest

from user_strategies.classement_pur import analyze_match, build_table


def fixture(
    home_id: int,
    away_id: int,
    home_goals: int,
    away_goals: int,
    day: int,
) -> dict:
    return {
        "fixture": {"date": f"2026-01-{day:02d}T20:00:00+00:00"},
        "teams": {
            "home": {"id": home_id, "name": f"Equipe {home_id}"},
            "away": {"id": away_id, "name": f"Equipe {away_id}"},
        },
        "goals": {"home": home_goals, "away": away_goals},
    }


def season_fixtures(rounds: int = 1) -> list[dict]:
    """Quatre equipes, une forte, une faible, deux intermediaires."""
    results = (
        (1, 4, 3, 0),
        (1, 3, 2, 0),
        (1, 2, 1, 0),
        (2, 4, 2, 1),
        (2, 3, 1, 1),
        (3, 4, 1, 0),
    )
    fixtures: list[dict] = []
    for round_index in range(rounds):
        for home, away, home_goals, away_goals in results:
            day = 1 + round_index * 6 + (home - 1) % 3
            fixtures.append(fixture(home, away, home_goals, away_goals, day))
    return fixtures


class ClassementTableTests(unittest.TestCase):
    def test_table_is_ranked_and_contains_venue_splits(self) -> None:
        table = build_table(season_fixtures(rounds=2))

        self.assertEqual(table["matches"], 12)
        self.assertEqual(table["n_teams"], 4)
        self.assertEqual(table["teams"][1]["rank"], 1)
        self.assertEqual(table["teams"][4]["rank"], 4)
        for bucket in table["teams"].values():
            self.assertEqual(bucket["home_played"] + bucket["away_played"], bucket["played"])
            self.assertEqual(bucket["played"], 6)
        self.assertEqual(table["teams"][1]["form"], ["V", "V", "V", "V", "V"])

    def test_before_date_ignores_later_results(self) -> None:
        fixtures = season_fixtures(rounds=2)
        table = build_table(fixtures, before_date="2026-01-07")

        self.assertLess(table["matches"], 12)
        self.assertEqual(table["teams"][1]["played"], 3)

    def test_ranking_is_deterministic_for_equal_teams(self) -> None:
        fixtures = [
            fixture(1, 2, 0, 0, 1),
            fixture(2, 1, 0, 0, 2),
        ]
        first = build_table(fixtures)["teams"]
        second = build_table(list(reversed(fixtures)))["teams"]

        self.assertEqual({tid: bucket["rank"] for tid, bucket in first.items()},
                         {tid: bucket["rank"] for tid, bucket in second.items()})


class ClassementAnalysisTests(unittest.TestCase):
    def test_probabilities_are_coherent_and_follow_the_rank(self) -> None:
        model = analyze_match(season_fixtures(rounds=4), 1, 4, "Equipe 1", "Equipe 4")
        probs = model["probabilities"]

        self.assertEqual(model["model_name"], "Classement Pur")
        self.assertEqual(model["rank_home"], 1)
        self.assertEqual(model["rank_away"], 4)
        self.assertGreater(model["rank_gap"], 0)
        self.assertAlmostEqual(probs["home"] + probs["draw"] + probs["away"], 1.0, places=3)
        self.assertAlmostEqual(probs["over25"] + probs["under25"], 1.0, places=3)
        self.assertAlmostEqual(probs["btts_yes"] + probs["btts_no"], 1.0, places=3)
        self.assertGreater(probs["home"], probs["away"])
        self.assertEqual(model["reliability"], "bonne")
        self.assertEqual(model["home"]["home_played"], 12)
        self.assertEqual(model["scores"], [])

    def test_unknown_opponent_gets_league_base_rates(self) -> None:
        model = analyze_match(season_fixtures(rounds=3), 1, 99, "Equipe 1", "Inconnue")
        probs = model["probabilities"]
        rates = model["league_rates"]

        self.assertAlmostEqual(probs["home"], rates["home"], places=3)
        self.assertAlmostEqual(probs["draw"], rates["draw"], places=3)
        self.assertAlmostEqual(probs["away"], rates["away"], places=3)

    def test_unknown_or_invalid_ids_do_not_break_the_analysis(self) -> None:
        fixtures = season_fixtures(rounds=2)
        unknown = analyze_match(fixtures, 99, 4, "Inconnue", "Equipe 4")
        invalid = analyze_match(fixtures, "abc", None, "Inconnue", "Inconnue")

        self.assertFalse(unknown["known_home"])
        self.assertTrue(unknown["known_away"])
        self.assertIsNone(unknown["rank_home"])
        self.assertAlmostEqual(
            unknown["probabilities"]["home"], unknown["league_rates"]["home"], places=3
        )
        self.assertFalse(invalid["known_home"])
        self.assertFalse(invalid["known_away"])
        self.assertEqual(invalid["rank_gap"], 0.0)

    def test_empty_season_uses_default_rates(self) -> None:
        model = analyze_match([], 1, 2, "Equipe 1", "Equipe 2")

        self.assertEqual(model["sample_matches"], 0)
        self.assertEqual(model["reliability"], "faible")
        self.assertAlmostEqual(model["probabilities"]["home"], 0.44, places=3)
        self.assertAlmostEqual(model["probabilities"]["draw"], 0.26, places=3)
        self.assertAlmostEqual(model["probabilities"]["away"], 0.30, places=3)


if __name__ == "__main__":
    unittest.main()
