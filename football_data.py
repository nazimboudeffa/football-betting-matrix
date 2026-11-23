"""Source de données unique : football-data.co.uk.

Deux familles de fichiers sont utilisées :

* ``fixtures.csv`` et ``new_league_fixtures.csv`` : prochains matchs + cotes ;
* ``mmz4281/<saison>/<div>.csv`` (grandes ligues) et ``new/<pays>.csv``
  (ligues supplémentaires) : résultats, statistiques et cotes.

Les lignes CSV sont converties dans le format attendu par les stratégies :
``date``, ``teams.home.id`` / ``teams.away.id``, ``goals.home`` / ``goals.away``.
"""

from __future__ import annotations

import csv
import hashlib
import io
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests

BASE_URL = "https://www.football-data.co.uk"
FIXTURES_URLS = (
    f"{BASE_URL}/fixtures.csv",
    f"{BASE_URL}/new_league_fixtures.csv",
)

_CACHE_TTL_SECONDS = 30 * 60  # 30 minutes
_CACHE: Dict[str, Tuple[float, List[Dict[str, str]]]] = {}


@dataclass(frozen=True)
class LeagueSpec:
    """Une ligue football-data : libellé, code Div et chemin du CSV de saison."""

    name: str
    div: str
    path: str  # template avec {code}, ex. "mmz4281/{code}/F1.csv"


def _main_league(name: str, div: str) -> LeagueSpec:
    return LeagueSpec(name, div, "mmz4281/{code}/" + div + ".csv")


def _extra_league(name: str, country: str, file_code: str) -> LeagueSpec:
    return LeagueSpec(name, country, "new/" + file_code + ".csv")


LEAGUES: Tuple[LeagueSpec, ...] = (
    _main_league("France Ligue 1", "F1"),
    _main_league("France Ligue 2", "F2"),
    _main_league("England Premier League", "E0"),
    _main_league("England Championship", "E1"),
    _main_league("England League One", "E2"),
    _main_league("England League Two", "E3"),
    _main_league("Germany Bundesliga", "D1"),
    _main_league("Germany 2. Bundesliga", "D2"),
    _main_league("Spain La Liga", "SP1"),
    _main_league("Spain La Liga 2", "SP2"),
    _main_league("Italy Serie A", "I1"),
    _main_league("Italy Serie B", "I2"),
    _main_league("Netherlands Eredivisie", "N1"),
    _main_league("Belgium Pro League", "B1"),
    _main_league("Portugal Primeira Liga", "P1"),
    _main_league("Turkey Super Lig", "T1"),
    _main_league("Greece Super League", "G1"),
    _main_league("Scotland Premiership", "SC0"),
    _main_league("Scotland Championship", "SC1"),
    _extra_league("Argentina Liga Profesional", "Argentina", "ARG"),
    _extra_league("Austria Bundesliga", "Austria", "AUT"),
    _extra_league("Brazil Serie A", "Brazil", "BRA"),
    _extra_league("China Super League", "China", "CHN"),
    _extra_league("Denmark Superliga", "Denmark", "DNK"),
    _extra_league("Japan J1 League", "Japan", "JPN"),
    _extra_league("Mexico Liga MX", "Mexico", "MEX"),
    _extra_league("Norway Eliteserien", "Norway", "NOR"),
    _extra_league("Poland Ekstraklasa", "Poland", "POL"),
    _extra_league("Romania Liga I", "Romania", "ROU"),
    _extra_league("Sweden Allsvenskan", "Sweden", "SWE"),
    _extra_league("Switzerland Super League", "Switzerland", "SWZ"),
    _extra_league("USA MLS", "USA", "USA"),
)


def list_seasons() -> List[str]:
    """Saisons disponibles, de la plus récente à la plus ancienne."""
    return [f"{year}-{str(year + 1)[-2:]}" for year in range(2026, 2009, -1)]


def list_leagues() -> List[LeagueSpec]:
    return list(LEAGUES)


def season_code(season: str) -> str:
    """``2026-27`` -> ``2627`` (format des URL football-data)."""
    parts = str(season).split("-")
    if len(parts) == 2 and len(parts[0]) >= 4 and parts[1]:
        return parts[0][-2:] + parts[1][-2:]
    digits = "".join(ch for ch in str(season) if ch.isdigit())
    return digits[-4:] if len(digits) >= 4 else digits


def season_start_year(season: str) -> Optional[int]:
    try:
        return int(str(season).split("-")[0][:4])
    except (TypeError, ValueError):
        return None


def league_csv_url(spec: LeagueSpec, season: str) -> str:
    return f"{BASE_URL}/{spec.path.format(code=season_code(season))}"


def fetch_csv_rows(url: str, use_cache: bool = True) -> List[Dict[str, str]]:
    now = time.time()
    if use_cache and url in _CACHE:
        timestamp, rows = _CACHE[url]
        if now - timestamp < _CACHE_TTL_SECONDS:
            return rows
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    # Les CSV football-data commencent par un BOM : utf-8-sig le supprime.
    text = response.content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = [
        {key: value or "" for key, value in row.items() if key is not None}
        for row in reader
    ]
    if use_cache:
        _CACHE[url] = (now, rows)
    return rows


def _row_identity(row: Dict[str, str]) -> Tuple[str, str, str, str]:
    div = str(row.get("Div") or row.get("Country") or "").strip()
    date = str(row.get("Date") or "").strip()
    home = str(row.get("HomeTeam") or row.get("Home") or "").strip()
    away = str(row.get("AwayTeam") or row.get("Away") or "").strip()
    return div, date, normalize_team_name(home), normalize_team_name(away)


def fetch_fixture_rows(use_cache: bool = True) -> List[Dict[str, str]]:
    """Prochains matchs de toutes les ligues, sans doublons."""
    rows: List[Dict[str, str]] = []
    seen = set()
    for url in FIXTURES_URLS:
        try:
            part = fetch_csv_rows(url, use_cache=use_cache)
        except Exception:
            # Une des deux listes peut être momentanément indisponible.
            continue
        for row in part:
            key = _row_identity(row)
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Équipes et dates
# ---------------------------------------------------------------------------

_ALIASES = {
    "paris saint germain": "paris sg",
    "psg": "paris sg",
    "as monaco": "monaco",
    "olympique lyonnais": "lyon",
    "olympique de marseille": "marseille",
    "stade rennais": "rennes",
    "losc": "lille",
    "ogc nice": "nice",
    "fc barcelone": "barcelona",
}

_LEADING_TOKENS = ("fc", "afc", "cf", "sc", "as", "ac")


def normalize_team_name(name: str) -> str:
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", str(name))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = text.replace("&", " and ")
    for token in _LEADING_TOKENS:
        if text.startswith(token + " "):
            text = text[len(token) + 1 :]
            break
    text = "".join(ch if ch.isalnum() or ch == " " else " " for ch in text)
    text = " ".join(text.split())
    if text.endswith(" fc"):
        text = text[:-3].strip()
    return _ALIASES.get(text, text)


def team_id(name: str) -> int:
    """Identifiant entier stable, calculé à partir du nom normalisé."""
    digest = hashlib.sha1(normalize_team_name(name).encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def parse_date(raw: str) -> Optional[str]:
    value = str(raw or "").strip()
    if not value:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _as_float(value: object) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _as_int(value: object) -> Optional[int]:
    number = _as_float(value)
    return int(number) if number is not None else None


def _season_matches(raw_season: object, season: str) -> bool:
    """Filtre les CSV « extra » qui contiennent plusieurs saisons."""
    if not raw_season:
        return True
    value = str(raw_season).strip()
    start = season_start_year(season)
    if start is None:
        return True
    return value == str(start) or value.startswith(f"{start}/") or f"/{start + 1}" in value


# ---------------------------------------------------------------------------
# Cotes
# ---------------------------------------------------------------------------

_BOOKMAKERS = (
    ("Bet365", "B365"),
    ("Betfred", "BFD"),
    ("BetMGM", "BMGM"),
    ("BetVictor", "BV"),
    ("Bet&Win", "BW"),
    ("Coral", "CL"),
    ("Ladbrokes", "LB"),
    ("Pinnacle", "PS"),
    ("Paddy Power", "PP"),
    ("Skybet", "SK"),
    ("William Hill", "WH"),
    ("Betfair Exchange", "BFE"),
)

_MARKET_SUFFIXES = {
    "home": "H",
    "draw": "D",
    "away": "A",
    "over25": ">2.5",
    "under25": "<2.5",
}


def parse_odds(row: Dict[str, str], closing: bool = False) -> Dict[str, dict]:
    """Cotes par marché, avec la meilleure cote disponible et la moyenne."""
    marker = "C" if closing else ""
    result: Dict[str, dict] = {}
    for key, suffix in _MARKET_SUFFIXES.items():
        bookmakers: Dict[str, float] = {}
        for label, prefix in _BOOKMAKERS:
            value = _as_float(row.get(f"{prefix}{marker}{suffix}"))
            if value is not None and value > 1.0:
                bookmakers[label] = value
        average = _as_float(row.get(f"Avg{marker}{suffix}"))
        maximum = _as_float(row.get(f"Max{marker}{suffix}"))
        candidates = [(label, value) for label, value in bookmakers.items()]
        if maximum is not None and maximum > 1.0:
            candidates.append(("Max du marché", maximum))
        best = max(candidates, key=lambda item: item[1]) if candidates else None
        result[key] = {
            "bookmakers": bookmakers,
            "avg": average,
            "max": maximum,
            "best": best,  # (bookmaker, cote)
        }
    return result


# ---------------------------------------------------------------------------
# Conversion en matchs
# ---------------------------------------------------------------------------


def row_to_fixture(
    row: Dict[str, str],
    spec: LeagueSpec,
    season: str,
    upcoming: bool = False,
) -> Optional[dict]:
    home = str(row.get("HomeTeam") or row.get("Home") or row.get("home_team") or "").strip()
    away = str(row.get("AwayTeam") or row.get("Away") or row.get("away_team") or "").strip()
    date = parse_date(row.get("Date") or row.get("date"))
    if not home or not away or not date:
        return None

    home_goals = _as_int(row.get("FTHG") if "FTHG" in row else row.get("HG"))
    away_goals = _as_int(row.get("FTAG") if "FTAG" in row else row.get("AG"))
    if (home_goals is None) != (away_goals is None):
        home_goals = away_goals = None
    played = home_goals is not None and not upcoming

    odds = parse_odds(row, closing=False)
    closing_odds = parse_odds(row, closing=True)
    # Les fichiers « extra » ne contiennent que des cotes de clôture.
    if not any(item["best"] for item in odds.values()):
        odds = closing_odds

    return {
        "date": date,
        "time": str(row.get("Time") or "").strip(),
        "div": spec.div,
        "league": spec.name,
        "season": season,
        "team1": home,
        "team2": away,
        "teams": {
            "home": {"id": team_id(home), "name": home},
            "away": {"id": team_id(away), "name": away},
        },
        "goals": {"home": home_goals, "away": away_goals},
        "score": {"ft": [home_goals, away_goals]} if played else None,
        "result": str(row.get("FTR") or row.get("Res") or "").strip(),
        "played": played,
        "odds": odds,
        "closing_odds": closing_odds,
        "fd_row": row,
    }


def _fixture_identity(fixture: dict) -> Tuple[str, str, str]:
    return (
        fixture["date"],
        normalize_team_name(fixture["team1"]),
        normalize_team_name(fixture["team2"]),
    )


def build_fixtures(
    spec: LeagueSpec,
    season: str,
    include_upcoming: bool = True,
) -> List[dict]:
    """Résultats de la saison + prochains matchs, dans l'ordre chronologique."""
    fixtures: List[dict] = []
    seen = set()

    for row in fetch_csv_rows(league_csv_url(spec, season)):
        if not _season_matches(row.get("Season"), season):
            continue
        fixture = row_to_fixture(row, spec, season)
        if fixture is None:
            continue
        key = _fixture_identity(fixture)
        if key in seen:
            continue
        seen.add(key)
        fixtures.append(fixture)

    if include_upcoming:
        for row in fetch_fixture_rows():
            div = str(row.get("Div") or row.get("Country") or "").strip()
            if div != spec.div:
                continue
            fixture = row_to_fixture(row, spec, season, upcoming=True)
            if fixture is None:
                continue
            key = _fixture_identity(fixture)
            if key in seen:
                continue
            seen.add(key)
            fixtures.append(fixture)

    fixtures.sort(key=lambda item: (item["date"], item.get("time") or ""))
    return fixtures


# ---------------------------------------------------------------------------
# Affichage
# ---------------------------------------------------------------------------


def format_fd_info(row: Dict[str, str]) -> List[tuple]:
    """Informations libles dans le panneau football-data de l'interface."""
    items: List[tuple] = []

    def odd_triplet(prefix: str) -> str:
        values = [row.get(prefix + suffix, "") for suffix in ("H", "D", "A")]
        return " / ".join(value or "-" for value in values)

    for label, prefix in (
        ("Bet365 (H/D/A)", "B365"),
        ("Pinnacle (H/D/A)", "PS"),
        ("Betfair Exchange (H/D/A)", "BFE"),
        ("Moyenne marché (H/D/A)", "Avg"),
    ):
        if any(row.get(prefix + suffix) for suffix in ("H", "D", "A")):
            items.append((label, odd_triplet(prefix)))

    for label, prefix in (
        ("Bet365 clôture (H/D/A)", "B365C"),
        ("Pinnacle clôture (H/D/A)", "PSC"),
        ("Moyenne clôture (H/D/A)", "AvgC"),
    ):
        if any(row.get(prefix + suffix) for suffix in ("H", "D", "A")):
            items.append((label, odd_triplet(prefix)))

    over = row.get("B365>2.5") or row.get("P>2.5") or row.get("Avg>2.5")
    under = row.get("B365<2.5") or row.get("P<2.5") or row.get("Avg<2.5")
    if over or under:
        items.append(("Over / Under 2.5", f"{over or '-'} / {under or '-'}"))

    hg = row.get("FTHG") if "FTHG" in row else row.get("HG")
    ag = row.get("FTAG") if "FTAG" in row else row.get("AG")
    ftr = row.get("FTR") or row.get("Res")
    if hg not in (None, "") and ag not in (None, ""):
        items.append(("Score FT", f"{hg}-{ag} ({ftr or '?'})"))

    hxg = row.get("HxG")
    axg = row.get("AxG")
    if hxg or axg:
        items.append(("xG", f"{hxg or '-'}-{axg or '-'}"))

    hs = row.get("HS")
    as_ = row.get("AS")
    hst = row.get("HST")
    ast = row.get("AST")
    if hs or as_:
        items.append(("Tirs (cadrés)", f"{hs or '-'}-{as_ or '-'} ({hst or '-'}-{ast or '-'})"))

    hc = row.get("HC")
    ac = row.get("AC")
    if hc or ac:
        items.append(("Corners", f"{hc or '-'}-{ac or '-'}"))

    return items
