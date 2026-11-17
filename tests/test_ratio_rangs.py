"""Tests du modele Ratio de Rangs (strategie autonome)."""

from __future__ import annotations

import unittest

from football_betting_matrix.config import ROOT_DIR
from football_betting_matrix.strategies import load_strategies, strategies_dir
from user_strategies.ratio_rangs import analyze_match, build_table, rank_ratio


def fixture(home_id: int, away_id: int, home_goals: int, away_goals: int, day: int) -> dict:
    return {
        "fixture": {"date": f"2026-01-{day:02d}T20:00:00+00:00"},
        "teams": {
            "home": {"id": home_id, "name": f"Equipe {home_id}"},
            "away": {"id": away_id, "name": f"Equipe {away_id}"},
        },
        "goals": {"home": home_goals, "away": away_goals},
    }


def season_fixtures(rounds: int = 1) -> list[dict]:
    """Quatre equipes ; domicile gagne 3 fois, nul 1 fois, exterieur 2 fois."""
    results = (
        (1, 4, 3, 0),
        (1, 3, 2, 1),
        (1, 2, 0, 1),
        (2, 4, 2, 1),
        (2, 3, 1, 1),
        (3, 4, 0, 1),
    )
    fixtures: list[dict] = []
    for round_index in range(rounds):
        for home, away, home_goals, away_goals in results:
            fixtures.append(
                fixture(home, away, home_goals, away_goals, 1 + round_index * 6 + home)
            )
    return fixtures


class RankRatioTests(unittest.TestCase):
    def test_raw_ratio_favours_the_better_rank(self) -> None:
        self.assertAlmostEqual(rank_ratio(1, 4), 0.8)
        self.assertAlmostEqual(rank_ratio(4, 1), 0.2)
        self.assertAlmostEqual(rank_ratio(0, 0), 0.5)


class RatioTableTests(unittest.TestCase):
    def test_table_is_ranked_and_contains_venue_splits(self) -> None:
        table = build_table(season_fixtures(rounds=2))

        self.assertEqual(table["matches"], 12)
        self.assertEqual(table["n_teams"], 4)
        self.assertEqual(table["teams"][2]["rank"], 1)
        self.assertEqual(table["teams"][3]["rank"], 4)
        for bucket in table["teams"].values():
            self.assertEqual(bucket["home_played"] + bucket["away_played"], bucket["played"])
            self.assertEqual(bucket["played"], 6)
        self.assertAlmostEqual(table["rates"]["home"], 0.5)
        self.assertAlmostEqual(table["rates"]["away"], 1 / 3)

    def test_before_date_ignores_later_results(self) -> None:
        table = build_table(season_fixtures(rounds=2), before_date="2026-01-07")

        self.assertLess(table["matches"], 12)
        self.assertEqual(table["teams"][1]["played"], 3)

    def test_ranking_is_deterministic(self) -> None:
        fixtures = [fixture(1, 2, 0, 0, 1), fixture(2, 1, 0, 0, 2)]
        first = build_table(fixtures)["teams"]
        second = build_table(list(reversed(fixtures)))["teams"]

        self.assertEqual(
            {tid: bucket["rank"] for tid, bucket in first.items()},
            {tid: bucket["rank"] for tid, bucket in second.items()},
        )


class RatioAnalysisTests(unittest.TestCase):
    def test_probabilities_are_coherent_and_follow_the_rank(self) -> None:
        model = analyze_match(season_fixtures(rounds=10), 1, 4, "Equipe 1", "Equipe 4")
        probs = model["probabilities"]

        self.assertEqual(model["model_name"], "Ratio de Rangs")
        self.assertEqual((model["rank_home"], model["rank_away"]), (2, 3))
        self.assertAlmostEqual(rank_ratio(2, 3), 0.6)
        self.assertAlmostEqual(model["rank_weight"], 0.6, places=3)
        self.assertAlmostEqual(probs["home"] + probs["draw"] + probs["away"], 1.0, places=3)
        self.assertAlmostEqual(probs["over25"] + probs["under25"], 1.0, places=3)
        self.assertAlmostEqual(probs["btts_yes"] + probs["btts_no"], 1.0, places=3)
        self.assertGreater(probs["home"], probs["away"])
        self.assertEqual(model["reliability"], "bonne")
        self.assertEqual(model["home"]["home_played"], 30)
        self.assertEqual(model["scores"], [])

        weak_home = analyze_match(season_fixtures(rounds=10), 3, 2, "Equipe 3", "Equipe 2")
        self.assertEqual((weak_home["rank_home"], weak_home["rank_away"]), (4, 1))
        self.assertGreater(
            weak_home["probabilities"]["away"], weak_home["probabilities"]["home"]
        )

    def test_unknown_teams_keep_the_league_home_advantage(self) -> None:
        fixtures = season_fixtures(rounds=10)
        model = analyze_match(fixtures, 99, 98, "Inconnue 1", "Inconnue 2")
        probs = model["probabilities"]
        rates = model["league_rates"]
        decisive = rates["home"] + rates["away"]

        self.assertFalse(model["known_home"])
        self.assertFalse(model["known_away"])
        self.assertAlmostEqual(model["rank_weight"], 0.5)
        self.assertAlmostEqual(probs["draw"], rates["draw"], places=3)
        self.assertAlmostEqual(probs["home"] / (probs["home"] + probs["away"]),
                               rates["home"] / decisive, places=3)

    def test_small_sample_damps_the_rank_ratio(self) -> None:
        early = analyze_match(season_fixtures(rounds=1), 1, 4, "Equipe 1", "Equipe 4")
        late = analyze_match(season_fixtures(rounds=10), 1, 4, "Equipe 1", "Equipe 4")

        self.assertLess(early["rank_weight"], late["rank_weight"])
        self.assertLess(early["probabilities"]["home"], late["probabilities"]["home"])

    def test_invalid_ids_and_empty_season_do_not_break_the_analysis(self) -> None:
        fixtures = season_fixtures(rounds=2)
        invalid = analyze_match(fixtures, "abc", None, "Inconnue", "Inconnue")
        empty = analyze_match([], 1, 2, "Equipe 1", "Equipe 2")

        invalid_rates = invalid["league_rates"]
        expected_home = (1 - invalid_rates["draw"]) * invalid_rates["home"] / (
            invalid_rates["home"] + invalid_rates["away"]
        )
        self.assertFalse(invalid["known_home"])
        self.assertFalse(invalid["known_away"])
        self.assertAlmostEqual(invalid["probabilities"]["home"], expected_home, places=3)
        self.assertEqual(empty["sample_matches"], 0)
        self.assertEqual(empty["reliability"], "faible")
        self.assertAlmostEqual(empty["probabilities"]["draw"], 0.26, places=3)


class RatioStrategyIntegrationTests(unittest.TestCase):
    def test_loader_exposes_fair_odds_with_a_ratio_signal(self) -> None:
        catalog = load_strategies(strategies_dir(ROOT_DIR))
        strategy = catalog.get("ratio_rangs")

        self.assertIsNotNone(strategy)
        rows = strategy.run({"home": 0.5, "draw": 0.25, "away": 0.25})
        self.assertTrue(rows)
        self.assertEqual([row["signal"] for row in rows], ["Ratio de rangs"] * len(rows))
        for row in rows:
            self.assertAlmostEqual(row["odd"], round(1 / row["prob"], 3), places=3)


if __name__ == "__main__":
    unittest.main()
