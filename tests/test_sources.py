"""Tests des sources gratuites (CSV, OpenFootball, OpenLigaDB, TheSportsDB)."""

from __future__ import annotations

import unittest

from datetime import date

from football_betting_matrix.sources import (
    canonical_team_key,
    compute_standings_from_fixtures,
    free_source_supports,
    merge_fixtures,
    normalize_openfootball_match,
    normalize_openliga_match,
    normalize_tsdb_event,
    parse_football_data_csv,
    season_code,
    season_label,
    season_start_year,
    stable_fixture_id,
)


CSV_SAMPLE = """Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,B365H,B365D,B365A,B365>2.5,B365<2.5
SP1,15/08/2026,18:30,Alaves,Getafe,3,0,H,2.35,2.80,3.75,2.42,1.55
SP1,16/08/2026,21:00,Ath Madrid,Espanol,2,1,H,1.55,4.10,6.50,2.05,1.80
"""


class TeamKeyTests(unittest.TestCase):
    def test_aliases_merge_short_names(self) -> None:
        self.assertEqual(canonical_team_key("Ath Madrid"), canonical_team_key("Atletico Madrid"))
        self.assertEqual(canonical_team_key("Espanol"), canonical_team_key("Espanyol"))
        self.assertEqual(canonical_team_key("Bayern Munich"), canonical_team_key("FC Bayern München"))
        self.assertEqual(canonical_team_key("M'gladbach"), canonical_team_key("Borussia Mönchengladbach"))
        self.assertEqual(canonical_team_key("La Coruna"), canonical_team_key("Deportivo de A Coruña"))
        self.assertEqual(canonical_team_key("Schalke 04"), canonical_team_key("FC Schalke 04"))
        self.assertEqual(canonical_team_key("Ath Madrid"), canonical_team_key("Club Atlético de Madrid"))
        self.assertEqual(canonical_team_key("Celta"), canonical_team_key("RC Celta de Vigo"))
        self.assertEqual(canonical_team_key("La Coruna"), canonical_team_key("RC Deportivo La Coruña"))
        self.assertEqual(canonical_team_key("Santander"), canonical_team_key("Real Racing Club de Santander"))
        self.assertEqual(canonical_team_key("Hoffenheim"), canonical_team_key("TSG 1899 Hoffenheim"))
        self.assertEqual(canonical_team_key("St Pauli"), canonical_team_key("FC St. Pauli 1910"))

    def test_serie_a_and_ligue_1_aliases(self) -> None:
        self.assertEqual(canonical_team_key("FC Internazionale Milano"), "inter milan")
        self.assertEqual(canonical_team_key("AC Milan"), "ac milan")
        self.assertEqual(canonical_team_key("Hellas Verona FC"), "verona")
        self.assertEqual(canonical_team_key("Paris Saint-Germain FC"), "paris saint germain")
        self.assertEqual(canonical_team_key("Olympique de Marseille"), "marseille")
        self.assertEqual(canonical_team_key("Stade Rennais FC 1901"), "rennes")

    def test_premier_league_aliases(self) -> None:
        self.assertEqual(canonical_team_key("Bournemouth"), canonical_team_key("AFC Bournemouth"))
        self.assertEqual(canonical_team_key("Brighton"), canonical_team_key("Brighton & Hove Albion FC"))
        self.assertEqual(canonical_team_key("Man United"), canonical_team_key("Manchester United FC"))
        self.assertEqual(canonical_team_key("Nott'm Forest"), canonical_team_key("Nottingham Forest FC"))
        self.assertEqual(canonical_team_key("Wolves"), canonical_team_key("Wolverhampton Wanderers FC"))
        self.assertEqual(canonical_team_key("Coventry"), canonical_team_key("Coventry City FC"))
        self.assertEqual(canonical_team_key("Hull"), canonical_team_key("Hull City AFC"))
        self.assertEqual(canonical_team_key("Ipswich"), canonical_team_key("Ipswich Town FC"))

    def test_stable_ids_are_deterministic(self) -> None:
        self.assertEqual(stable_fixture_id("free", 140, 2026, "2026-08-15"), stable_fixture_id("free", 140, 2026, "2026-08-15"))
        self.assertNotEqual(stable_fixture_id("free", 140, 2026, "2026-08-15"), stable_fixture_id("free", 140, 2026, "2026-08-16"))

    def test_season_helpers(self) -> None:
        self.assertEqual(season_code(2026), "2627")
        self.assertEqual(season_code(2025), "2526")
        self.assertEqual(season_label(2026), "2026-27")


class SourceSupportTests(unittest.TestCase):
    def test_free_source_coverage(self) -> None:
        current = season_start_year(date.today())
        self.assertTrue(free_source_supports(140, 2025))
        self.assertTrue(free_source_supports(39, 2025))
        self.assertTrue(free_source_supports(78, 2025))
        self.assertTrue(free_source_supports(135, 2025))
        self.assertTrue(free_source_supports(61, 2025))
        self.assertTrue(free_source_supports(2, current))
        self.assertFalse(free_source_supports(2, current - 1))
        self.assertFalse(free_source_supports(999, 2025))


class CsvParsingTests(unittest.TestCase):
    def test_parse_results_and_odds(self) -> None:
        items = parse_football_data_csv(CSV_SAMPLE, 140, 2026)
        self.assertEqual(len(items), 2)
        first = items[0]
        self.assertEqual(first["teams"]["home"]["name"], "Alaves")
        self.assertEqual(first["teams"]["away"]["name"], "Getafe")
        self.assertEqual(first["goals"], {"home": 3, "away": 0})
        self.assertEqual(first["fixture"]["status"]["short"], "FT")
        self.assertEqual(first["bookmaker_odds"]["home"], 2.35)
        self.assertEqual(first["bookmaker_odds"]["draw"], 2.8)
        self.assertEqual(first["bookmaker_odds"]["away"], 3.75)
        self.assertEqual(first["bookmaker_odds"]["over25"], 2.42)
        self.assertEqual(first["source"], "football-data.co.uk")

    def test_fixture_ids_match_between_sources(self) -> None:
        csv_items = parse_football_data_csv(CSV_SAMPLE, 140, 2026)
        openfootball = normalize_openfootball_match(
            {
                "round": "Matchday 1",
                "date": "2026-08-15",
                "time": "18:30",
                "team1": "Deportivo Alavés",
                "team2": "Getafe CF",
                "score": {"ft": [3, 0]},
            },
            140,
            2026,
        )
        self.assertEqual(csv_items[0]["fixture"]["id"], openfootball["fixture"]["id"])
        self.assertEqual(csv_items[0]["teams"]["home"]["id"], openfootball["teams"]["home"]["id"])


class NormalizationTests(unittest.TestCase):
    def test_openfootball_match(self) -> None:
        item = normalize_openfootball_match(
            {
                "round": "Matchday 12",
                "date": "2026-11-20",
                "time": "20:00",
                "team1": "Athletic Bilbao",
                "team2": "Espanyol",
                "score": {},
            },
            140,
            2026,
        )
        self.assertEqual(item["fixture"]["status"]["short"], "NS")
        self.assertIsNone(item["goals"]["home"])
        self.assertEqual(item["league"]["round"], "Journee 12")
        self.assertEqual(item["source"], "OpenFootball")

    def test_openliga_match(self) -> None:
        item = normalize_openliga_match(
            {
                "matchID": 1,
                "matchDateTimeUTC": "2026-11-20T19:30:00Z",
                "matchIsFinished": True,
                "matchResults": [
                    {"resultTypeID": 2, "resultName": "Endergebnis", "pointsTeam1": 2, "pointsTeam2": 1}
                ],
                "group": {"groupName": "12. Spieltag"},
                "team1": {"teamName": "FC Bayern München", "teamIconUrl": "https://example/logo1.png"},
                "team2": {"teamName": "1. FC Köln", "teamIconUrl": "https://example/logo2.png"},
            },
            78,
            2026,
        )
        self.assertEqual(item["fixture"]["status"]["short"], "FT")
        self.assertEqual(item["goals"], {"home": 2, "away": 1})
        self.assertEqual(item["league"]["round"], "Journee 12")
        self.assertEqual(item["teams"]["home"]["logo"], "https://example/logo1.png")

    def test_tsdb_match(self) -> None:
        item = normalize_tsdb_event(
            {
                "idEvent": "123",
                "strTimestamp": "2026-11-24T17:45:00",
                "strHomeTeam": "Bodø/Glimt",
                "strAwayTeam": "LASK",
                "strLeague": "UEFA Champions League",
                "strCountry": "World",
                "strStatus": "NS",
                "intRound": "5",
                "strHomeTeamBadge": "https://example/home.png",
            },
            2,
            2026,
        )
        self.assertEqual(item["fixture"]["status"]["short"], "NS")
        self.assertEqual(item["league"]["round"], "Journee 5")
        self.assertEqual(item["teams"]["home"]["logo"], "https://example/home.png")


class MergeAndStandingsTests(unittest.TestCase):
    def test_merge_prefers_finished_with_odds(self) -> None:
        csv_item = parse_football_data_csv(CSV_SAMPLE, 140, 2026)[0]
        tsdb_item = normalize_tsdb_event(
            {
                "idEvent": "1",
                "strTimestamp": "2026-08-15T18:30:00",
                "strHomeTeam": "Deportivo Alavés",
                "strAwayTeam": "Getafe CF",
                "strLeague": "Spanish La Liga",
                "strStatus": "NS",
            },
            140,
            2026,
        )
        merged = merge_fixtures([tsdb_item], [csv_item])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["fixture"]["status"]["short"], "FT")
        self.assertEqual(merged[0]["bookmaker_odds"]["home"], 2.35)
        self.assertIn("TheSportsDB", merged[0]["source"])
        self.assertIn("football-data.co.uk", merged[0]["source"])

    def test_merge_rescheduled_match_by_team_pair(self) -> None:
        csv_item = parse_football_data_csv(CSV_SAMPLE, 140, 2026)[0]
        openfootball = normalize_openfootball_match(
            {
                "date": "2026-08-16",
                "time": "18:30",
                "team1": "Alaves",
                "team2": "Getafe",
                "score": {},
            },
            140,
            2026,
        )
        merged = merge_fixtures([csv_item], [openfootball])
        self.assertEqual(len(merged), 1)
        self.assertTrue(merged[0]["fixture"]["date"].startswith("2026-08-15"))
        self.assertEqual(merged[0]["fixture"]["status"]["short"], "FT")
        self.assertEqual(merged[0]["bookmaker_odds"]["home"], 2.35)

    def test_merge_prefers_first_source_date_for_upcoming(self) -> None:
        openliga = normalize_openliga_match(
            {
                "matchID": 1,
                "matchDateTimeUTC": "2026-12-06T16:30:00Z",
                "matchIsFinished": False,
                "matchResults": [],
                "group": {"groupName": "13. Spieltag"},
                "team1": {"teamName": "SV 07 Elversberg"},
                "team2": {"teamName": "VfB Stuttgart"},
            },
            78,
            2026,
        )
        openfootball = normalize_openfootball_match(
            {
                "date": "2026-12-05",
                "time": "15:30",
                "team1": "SV 07 Elversberg",
                "team2": "VfB Stuttgart",
                "score": {},
            },
            78,
            2026,
        )
        merged = merge_fixtures([openliga], [openfootball])
        self.assertEqual(len(merged), 1)
        self.assertTrue(merged[0]["fixture"]["date"].startswith("2026-12-06"))
        self.assertIn("OpenLigaDB", merged[0]["source"])

    def test_merge_keeps_distant_same_pair_separate(self) -> None:
        first = normalize_openfootball_match(
            {
                "date": "2026-08-15",
                "time": "20:00",
                "team1": "Barcelona",
                "team2": "Real Madrid",
                "score": {},
            },
            140,
            2026,
        )
        second = normalize_openfootball_match(
            {
                "date": "2027-01-15",
                "time": "20:00",
                "team1": "Barcelona",
                "team2": "Real Madrid",
                "score": {},
            },
            140,
            2026,
        )
        merged = merge_fixtures([first], [second])
        self.assertEqual(len(merged), 2)

    def test_standings_from_results(self) -> None:
        items = parse_football_data_csv(CSV_SAMPLE, 140, 2026)
        payload = compute_standings_from_fixtures(items, 140, 2026)
        rows = payload["league"]["standings"][0]
        self.assertEqual(rows[0]["team"]["name"], "Alaves")
        self.assertEqual(rows[0]["points"], 3)
        self.assertEqual(rows[0]["goalsDiff"], 3)
        self.assertEqual(rows[-1]["team"]["name"], "Getafe")


if __name__ == "__main__":
    unittest.main()
