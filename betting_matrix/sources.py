"""Sources de donnees gratuites, sans cle API personnelle.

Sources utilisees pour les saisons 2025 et 2026 :

- football-data.co.uk (CSV) : resultats, cotes 1X2 et Over/Under 2.5.
- OpenFootball (JSON GitHub) : calendriers La Liga, Premier League,
  Bundesliga, Serie A, Ligue 1.
- OpenLigaDB (API publique) : calendrier et resultats Bundesliga.
- TheSportsDB (cle publique de demonstration ``123``) : calendrier
  partiel de la Ligue des Champions.

Toutes les reponses sont normalisees dans un format commun. Les identifiants
d'equipes et de matchs sont derives des noms canoniques afin que les differentes
sources puissent fusionner.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import re
import threading
import time
import unicodedata
from datetime import date, datetime, timezone
from typing import Any

import requests

from .config import Config
from .store import MemoryCache
from .errors import SourceError, SourceNetworkError, SourceRateLimitError

CSV_BASE = "https://www.football-data.co.uk/mmz4281"
OPENFOOTBALL_BASE = "https://raw.githubusercontent.com/openfootball/football.json/master"
OPENLIGA_BASE = "https://api.openligadb.de"
TSDB_BASE = "https://www.thesportsdb.com/api/v1/json"

CSV_LEAGUES = {
    140: {"code": "SP1", "name": "La Liga", "country": "Spain"},
    39: {"code": "E0", "name": "Premier League", "country": "England"},
    78: {"code": "D1", "name": "Bundesliga", "country": "Germany"},
    135: {"code": "I1", "name": "Serie A", "country": "Italy"},
    61: {"code": "F1", "name": "Ligue 1", "country": "France"},
}

OPENFOOTBALL_FILES = {
    140: {"file": "es.1.json", "name": "La Liga", "country": "Spain"},
    39: {"file": "en.1.json", "name": "Premier League", "country": "England"},
    78: {"file": "de.1.json", "name": "Bundesliga", "country": "Germany"},
    135: {"file": "it.1.json", "name": "Serie A", "country": "Italy"},
    61: {"file": "fr.1.json", "name": "Ligue 1", "country": "France"},
}

OPENLIGA_LEAGUES = {
    78: {"code": "bl1", "name": "Bundesliga", "country": "Germany"},
}

TSDB_LEAGUES = {
    2: {"id": "4480", "name": "UEFA Champions League", "country": "World"},
}

FREE_LEAGUES = {
    140: {"id": 140, "name": "La Liga", "country": "Spain"},
    39: {"id": 39, "name": "Premier League", "country": "England"},
    78: {"id": 78, "name": "Bundesliga", "country": "Germany"},
    135: {"id": 135, "name": "Serie A", "country": "Italy"},
    61: {"id": 61, "name": "Ligue 1", "country": "France"},
    2: {"id": 2, "name": "UEFA Champions League", "country": "World"},
}

SOURCE_LABELS = {
    "csv": "football-data.co.uk",
    "openfootball": "OpenFootball",
    "openliga": "OpenLigaDB",
    "tsdb": "TheSportsDB",
}

FINAL_STATUSES = {"FT", "AET", "PEN"}

# Noms courts football-data.co.uk / OpenLigaDB / TheSportsDB -> nom canonique.
TEAM_ALIASES = {
    # Espagne
    "ath bilbao": "athletic bilbao",
    "athletic": "athletic bilbao",
    "athletic club": "athletic bilbao",
    "ath madrid": "atletico madrid",
    "atletico": "atletico madrid",
    "atletico de madrid": "atletico madrid",
    "club atletico de madrid": "atletico madrid",
    "barcelona": "barcelona",
    "fc barcelona": "barcelona",
    "betis": "real betis",
    "real betis": "real betis",
    "real betis balompie": "real betis",
    "sociedad": "real sociedad",
    "real sociedad": "real sociedad",
    "real sociedad de futbol": "real sociedad",
    "vallecano": "rayo vallecano",
    "rayo vallecano": "rayo vallecano",
    "rayo vallecano de madrid": "rayo vallecano",
    "celta": "celta vigo",
    "celta vigo": "celta vigo",
    "celta de vigo": "celta vigo",
    "rc celta de vigo": "celta vigo",
    "espanyol": "espanyol",
    "espanol": "espanyol",
    "rcd espanyol": "espanyol",
    "rcd espanyol de barcelona": "espanyol",
    "elche": "elche",
    "elche cf": "elche",
    "getafe": "getafe",
    "getafe cf": "getafe",
    "girona": "girona",
    "girona fc": "girona",
    "levante": "levante",
    "levante ud": "levante",
    "mallorca": "mallorca",
    "rcd mallorca": "mallorca",
    "osasuna": "osasuna",
    "ca osasuna": "osasuna",
    "oviedo": "real oviedo",
    "real oviedo": "real oviedo",
    "alaves": "alaves",
    "deportivo alaves": "alaves",
    "sevilla": "sevilla",
    "sevilla fc": "sevilla",
    "valencia": "valencia",
    "valencia cf": "valencia",
    "villarreal": "villarreal",
    "villarreal cf": "villarreal",
    "real madrid": "real madrid",
    "real madrid cf": "real madrid",
    "la coruna": "deportivo la coruna",
    "deportivo de a coruna": "deportivo la coruna",
    "deportivo la coruna": "deportivo la coruna",
    "rc deportivo la coruna": "deportivo la coruna",
    "malaga": "malaga",
    "malaga cf": "malaga",
    "santander": "racing santander",
    "racing de santander": "racing santander",
    "racing santander": "racing santander",
    "real racing club de santander": "racing santander",
    # Allemagne
    "augsburg": "augsburg",
    "fc augsburg": "augsburg",
    "bayern": "bayern munchen",
    "bayern munich": "bayern munchen",
    "bayern muenchen": "bayern munchen",
    "bayern munchen": "bayern munchen",
    "fc bayern munchen": "bayern munchen",
    "dortmund": "borussia dortmund",
    "borussia dortmund": "borussia dortmund",
    "ein frankfurt": "eintracht frankfurt",
    "eintracht frankfurt": "eintracht frankfurt",
    "frankfurt": "eintracht frankfurt",
    "freiburg": "freiburg",
    "sc freiburg": "freiburg",
    "hamburg": "hamburger",
    "hamburger": "hamburger",
    "hamburger sv": "hamburger",
    "heidenheim": "heidenheim",
    "1 fc heidenheim": "heidenheim",
    "1 fc heidenheim 1846": "heidenheim",
    "1 heidenheim": "heidenheim",
    "hoffenheim": "hoffenheim",
    "tsg hoffenheim": "hoffenheim",
    "tsg 1899 hoffenheim": "hoffenheim",
    "koln": "koln",
    "fc koln": "koln",
    "1 fc koln": "koln",
    "1 koln": "koln",
    "leverkusen": "leverkusen",
    "bayer leverkusen": "leverkusen",
    "bayer 04 leverkusen": "leverkusen",
    "mainz": "mainz",
    "mainz 05": "mainz",
    "1 fsv mainz 05": "mainz",
    "1 mainz 05": "mainz",
    "m gladbach": "borussia monchengladbach",
    "monchengladbach": "borussia monchengladbach",
    "borussia monchengladbach": "borussia monchengladbach",
    "leipzig": "rb leipzig",
    "rb leipzig": "rb leipzig",
    "st pauli": "st pauli",
    "fc st pauli": "st pauli",
    "st pauli 1910": "st pauli",
    "fc st pauli 1910": "st pauli",
    "stuttgart": "stuttgart",
    "vfb stuttgart": "stuttgart",
    "union berlin": "union berlin",
    "1 fc union berlin": "union berlin",
    "werder bremen": "werder bremen",
    "sv werder bremen": "werder bremen",
    "wolfsburg": "wolfsburg",
    "vfl wolfsburg": "wolfsburg",
    "schalke 04": "schalke 04",
    "fc schalke 04": "schalke 04",
    "paderborn": "paderborn",
    "paderborn 07": "paderborn",
    "sc paderborn 07": "paderborn",
    "elversberg": "elversberg",
    "sv 07 elversberg": "elversberg",
    # Europe / UCL
    "man city": "manchester city",
    "manchester city": "manchester city",
    "man utd": "manchester united",
    "manchester united": "manchester united",
    "psg": "paris saint germain",
    "paris sg": "paris saint germain",
    "paris saint germain": "paris saint germain",
    "inter": "inter milan",
    "internazionale": "inter milan",
    "inter milan": "inter milan",
    "milan": "ac milan",
    "ac milan": "ac milan",
    "juve": "juventus",
    "juventus": "juventus",
    # Italie
    "ac monza": "monza",
    "acf fiorentina": "fiorentina",
    "as roma": "roma",
    "atalanta bc": "atalanta",
    "bologna fc 1909": "bologna",
    "cagliari calcio": "cagliari",
    "como 1907": "como",
    "fc internazionale milano": "inter milan",
    "frosinone calcio": "frosinone",
    "genoa cfc": "genoa",
    "hellas verona fc": "verona",
    "parma calcio 1913": "parma",
    "ss lazio": "lazio",
    "ssc napoli": "napoli",
    "udinese calcio": "udinese",
    "us cremonese": "cremonese",
    "us lecce": "lecce",
    "us sassuolo calcio": "sassuolo",
    "ac pisa 1909": "pisa",
    # France
    "aj auxerre": "auxerre",
    "angers sco": "angers",
    "as monaco fc": "monaco",
    "es troyes ac": "troyes",
    "le havre ac": "le havre",
    "lille osc": "lille",
    "ogc nice": "nice",
    "olympique de marseille": "marseille",
    "olympique lyonnais": "lyon",
    "paris saint germain fc": "paris saint germain",
    "racing club de lens": "lens",
    "rc strasbourg alsace": "strasbourg",
    "stade brestois 29": "brest",
    "stade rennais fc 1901": "rennes",
    # Angleterre / Premier League
    "afc bournemouth": "bournemouth",
    "bournemouth": "bournemouth",
    "brighton": "brighton",
    "brighton and hove albion": "brighton",
    "coventry": "coventry",
    "coventry city": "coventry",
    "hull": "hull",
    "hull city": "hull",
    "hull city afc": "hull",
    "ipswich": "ipswich",
    "ipswich town": "ipswich",
    "leeds": "leeds",
    "leeds united": "leeds",
    "man united": "manchester united",
    "newcastle": "newcastle",
    "newcastle united": "newcastle",
    "nott m forest": "nottingham forest",
    "nottingham forest": "nottingham forest",
    "sunderland": "sunderland",
    "sunderland afc": "sunderland",
    "tottenham": "tottenham",
    "tottenham hotspur": "tottenham",
    "west ham": "west ham",
    "west ham united": "west ham",
    "wolves": "wolverhampton",
    "wolverhampton": "wolverhampton",
    "wolverhampton wanderers": "wolverhampton",
}

_PREFIX_TOKENS = {
    "1",
    "fc",
    "cf",
    "sc",
    "sv",
    "vfb",
    "vfl",
    "tsg",
    "fsv",
    "ud",
    "rcd",
    "rc",
    "ca",
    "club",
}
_SUFFIX_TOKENS = {"fc", "cf", "sc", "sv", "ud", "rcd", "ca", "club"}

TSDB_STATUS = {
    "NS": "NS",
    "NOT STARTED": "NS",
    "FT": "FT",
    "AET": "AET",
    "PEN": "PEN",
    "PST": "PST",
    "POSTPONED": "PST",
    "CANC": "CANC",
    "CANCELLED": "CANC",
    "ABD": "ABD",
    "AWD": "AWD",
    "WO": "WO",
    "1H": "1H",
    "2H": "2H",
    "HT": "HT",
    "ET": "ET",
    "BT": "BT",
    "P": "P",
    "LIVE": "LIVE",
    "SUSP": "SUSP",
    "INT": "INT",
}


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def canonical_team_key(name: str) -> str:
    """Cle stable et lisible pour rapprocher les noms entre fournisseurs."""
    key = _fold(name)
    key = TEAM_ALIASES.get(key, key)
    tokens = key.split()
    while tokens and tokens[0] in _PREFIX_TOKENS:
        tokens.pop(0)
    while tokens and tokens[-1] in _SUFFIX_TOKENS:
        tokens.pop()
    key = " ".join(tokens)
    return TEAM_ALIASES.get(key, key) or key or "equipe inconnue"


def stable_team_id(name: str) -> int:
    digest = hashlib.sha1(canonical_team_key(name).encode("utf-8")).hexdigest()[:12]
    return int(digest, 16)


def stable_fixture_id(prefix: str, *parts: Any) -> int:
    raw = "|".join([prefix, *(str(part) for part in parts)])
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return int(digest, 16)


def season_code(season: int) -> str:
    return f"{int(season) % 100:02d}{(int(season) + 1) % 100:02d}"


def season_label(season: int) -> str:
    return f"{int(season)}-{(int(season) + 1) % 100:02d}"


def season_start_year(day: date) -> int:
    return day.year if day.month >= 7 else day.year - 1


def free_source_supports(league_id: int, season: int) -> bool:
    """Indique si les sources gratuites couvrent cette ligue et cette saison.

    La Liga, la Premier League, la Bundesliga, la Serie A et la Ligue 1 sont
    couvertes par les CSV et/ou les calendriers OpenFootball. La Ligue des
    Champions ne dispose que d'un calendrier partiel TheSportsDB pour la
    saison en cours.
    """
    league_id = int(league_id)
    if (
        league_id in CSV_LEAGUES
        or league_id in OPENFOOTBALL_FILES
        or league_id in OPENLIGA_LEAGUES
    ):
        return True
    if league_id in TSDB_LEAGUES:
        return int(season) >= season_start_year(date.today())
    return False


def csv_url(league_id: int, season: int) -> str:
    info = CSV_LEAGUES.get(int(league_id))
    if not info:
        raise SourceError(f"Aucun fichier CSV connu pour la ligue {league_id}.", "source")
    return f"{CSV_BASE}/{season_code(season)}/{info['code']}.csv"


def _parse_csv_date(value: str, time_value: str | None = None) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    parsed = None
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(value, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        return None
    clock = (time_value or "00:00").strip() or "00:00"
    try:
        hour, minute = clock.split(":")[:2]
        parsed = parsed.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
    except (TypeError, ValueError):
        pass
    return parsed


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _to_int(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(str(value).strip())
        return number if number > 1.0 else None
    except (TypeError, ValueError):
        return None


def _first_float(row: dict, *keys: str) -> float | None:
    for key in keys:
        value = _to_float(row.get(key))
        if value is not None:
            return value
    return None


def _csv_odds(row: dict) -> dict:
    return {
        "home": _first_float(row, "B365CH", "B365H", "AvgCH", "AvgH", "MaxCH", "MaxH"),
        "draw": _first_float(row, "B365CD", "B365D", "AvgCD", "AvgD", "MaxCD", "MaxD"),
        "away": _first_float(row, "B365CA", "B365A", "AvgCA", "AvgA", "MaxCA", "MaxA"),
        "over25": _first_float(row, "B365C>2.5", "B365>2.5", "AvgC>2.5", "Avg>2.5"),
        "under25": _first_float(row, "B365C<2.5", "B365<2.5", "AvgC<2.5", "Avg<2.5"),
    }


def _fixture_payload(
    *,
    fixture_id: int,
    moment: datetime | None,
    league_id: int,
    season: int,
    league_name: str,
    country: str,
    round_label: str,
    home_name: str,
    away_name: str,
    home_goals: int | None,
    away_goals: int | None,
    finished: bool,
    home_logo: str = "",
    away_logo: str = "",
    league_logo: str = "",
    venue_name: str = "",
    venue_city: str = "",
    referee: str | None = None,
    source: str,
    bookmaker_odds: dict | None = None,
) -> dict:
    winner = None
    if finished and home_goals is not None and away_goals is not None:
        if home_goals > away_goals:
            winner = "HOME_TEAM"
        elif away_goals > home_goals:
            winner = "AWAY_TEAM"
        else:
            winner = "DRAW"
    status = "FT" if finished else "NS"
    timestamp = int(moment.replace(tzinfo=timezone.utc).timestamp()) if moment else None
    return {
        "fixture": {
            "id": fixture_id,
            "date": moment.strftime("%Y-%m-%dT%H:%M:%S") if moment else None,
            "timestamp": timestamp,
            "referee": referee,
            "venue": {"name": venue_name, "city": venue_city},
            "status": {
                "short": status,
                "long": "Termine" if finished else "A venir",
                "elapsed": 90 if finished else None,
            },
        },
        "league": {
            "id": int(league_id),
            "name": league_name,
            "country": country,
            "logo": league_logo,
            "flag": "",
            "season": int(season),
            "round": round_label,
        },
        "teams": {
            "home": {
                "id": stable_team_id(home_name),
                "name": home_name or "Equipe domicile",
                "logo": home_logo,
                "winner": True if winner == "HOME_TEAM" else (False if winner else None),
            },
            "away": {
                "id": stable_team_id(away_name),
                "name": away_name or "Equipe exterieur",
                "logo": away_logo,
                "winner": True if winner == "AWAY_TEAM" else (False if winner else None),
            },
        },
        "goals": {"home": home_goals, "away": away_goals},
        "score": {
            "winner": winner,
            "fullTime": {"home": home_goals, "away": away_goals},
        },
        "source": source,
        "sources": [source],
        "bookmaker_odds": bookmaker_odds or {},
    }


def _free_fixture_id(
    league_id: int, season: int, moment: datetime | None, home_name: str, away_name: str
) -> int:
    day = moment.date().isoformat() if moment else "date-inconnue"
    return stable_fixture_id(
        "free",
        int(league_id),
        int(season),
        day,
        canonical_team_key(home_name),
        canonical_team_key(away_name),
    )


def parse_football_data_csv(text: str, league_id: int, season: int) -> list[dict]:
    """Transforme un CSV football-data.co.uk en fixtures normalisees."""
    info = CSV_LEAGUES.get(int(league_id), {"name": f"Ligue {league_id}", "country": ""})
    reader = csv.DictReader(io.StringIO(text))
    items: list[dict] = []
    for raw_row in reader:
        row = {(key or "").lstrip("\ufeff"): value for key, value in raw_row.items()}
        home_name = (row.get("HomeTeam") or "").strip()
        away_name = (row.get("AwayTeam") or "").strip()
        moment = _parse_csv_date(row.get("Date") or "", row.get("Time"))
        if not home_name or not away_name or moment is None:
            continue
        home_goals = _to_int(row.get("FTHG"))
        away_goals = _to_int(row.get("FTAG"))
        finished = home_goals is not None and away_goals is not None
        items.append(
            _fixture_payload(
                fixture_id=_free_fixture_id(
                    league_id, season, moment, home_name, away_name
                ),
                moment=moment,
                league_id=league_id,
                season=season,
                league_name=info["name"],
                country=info.get("country", ""),
                round_label=(row.get("Div") or "").strip(),
                home_name=home_name,
                away_name=away_name,
                home_goals=home_goals,
                away_goals=away_goals,
                finished=finished,
                referee=(row.get("Referee") or "").strip() or None,
                source=SOURCE_LABELS["csv"],
                bookmaker_odds=_csv_odds(row),
            )
        )
    items.sort(key=lambda item: item["fixture"].get("date") or "")
    return items


def _openfootball_round(value: str) -> str:
    text = (value or "").strip()
    match = re.match(r"Matchday\s+(\d+)", text, re.IGNORECASE)
    if match:
        return f"Journee {match.group(1)}"
    return text


def normalize_openfootball_match(raw: dict, league_id: int, season: int) -> dict:
    info = OPENFOOTBALL_FILES.get(
        int(league_id), {"name": f"Ligue {league_id}", "country": ""}
    )
    home_name = (raw.get("team1") or "").strip()
    away_name = (raw.get("team2") or "").strip()
    moment = _parse_iso_datetime(
        f"{raw.get('date') or ''}T{raw.get('time') or '00:00'}:00"
    )
    score = raw.get("score") or {}
    full_time = score.get("ft") if isinstance(score, dict) else None
    home_goals = away_goals = None
    if isinstance(full_time, (list, tuple)) and len(full_time) >= 2:
        home_goals = _to_int(full_time[0])
        away_goals = _to_int(full_time[1])
    finished = home_goals is not None and away_goals is not None
    return _fixture_payload(
        fixture_id=_free_fixture_id(league_id, season, moment, home_name, away_name),
        moment=moment,
        league_id=league_id,
        season=season,
        league_name=info["name"],
        country=info.get("country", ""),
        round_label=_openfootball_round(raw.get("round") or ""),
        home_name=home_name,
        away_name=away_name,
        home_goals=home_goals,
        away_goals=away_goals,
        finished=finished,
        source=SOURCE_LABELS["openfootball"],
    )


def _openliga_round(raw: dict) -> str:
    group = raw.get("group") or {}
    name = (group.get("groupName") or "").strip()
    match = re.match(r"(\d+)\.\s*Spieltag", name, re.IGNORECASE)
    if match:
        return f"Journee {match.group(1)}"
    return name


def normalize_openliga_match(raw: dict, league_id: int, season: int) -> dict:
    info = OPENLIGA_LEAGUES.get(
        int(league_id), {"name": f"Ligue {league_id}", "country": ""}
    )
    home = raw.get("team1") or {}
    away = raw.get("team2") or {}
    home_name = (home.get("teamName") or home.get("shortName") or "").strip()
    away_name = (away.get("teamName") or away.get("shortName") or "").strip()
    moment = _parse_iso_datetime(
        raw.get("matchDateTimeUTC") or raw.get("matchDateTime")
    )
    finished = bool(raw.get("matchIsFinished"))
    home_goals = away_goals = None
    if finished:
        for result in raw.get("matchResults") or []:
            if result.get("resultTypeID") == 2 or result.get("resultName") == "Endergebnis":
                home_goals = _to_int(result.get("pointsTeam1"))
                away_goals = _to_int(result.get("pointsTeam2"))
                break
        if home_goals is None or away_goals is None:
            goals = raw.get("goals") or []
            if goals:
                last = goals[-1]
                home_goals = _to_int(last.get("scoreTeam1"))
                away_goals = _to_int(last.get("scoreTeam2"))
    if home_goals is None or away_goals is None:
        finished = False
    return _fixture_payload(
        fixture_id=_free_fixture_id(league_id, season, moment, home_name, away_name),
        moment=moment,
        league_id=league_id,
        season=season,
        league_name=info["name"],
        country=info.get("country", ""),
        round_label=_openliga_round(raw),
        home_name=home_name,
        away_name=away_name,
        home_goals=home_goals,
        away_goals=away_goals,
        finished=finished,
        home_logo=(home.get("teamIconUrl") or "").strip(),
        away_logo=(away.get("teamIconUrl") or "").strip(),
        source=SOURCE_LABELS["openliga"],
    )


def normalize_tsdb_event(raw: dict, league_id: int, season: int) -> dict:
    info = TSDB_LEAGUES.get(int(league_id)) or FREE_LEAGUES.get(
        int(league_id), {"name": f"Ligue {league_id}", "country": ""}
    )
    home_name = (raw.get("strHomeTeam") or "").strip()
    away_name = (raw.get("strAwayTeam") or "").strip()
    moment = _parse_iso_datetime(raw.get("strTimestamp"))
    if moment is None:
        moment = _parse_iso_datetime(
            f"{raw.get('dateEvent') or ''}T{raw.get('strTime') or '00:00:00'}"
        )
    home_goals = _to_int(raw.get("intHomeScore"))
    away_goals = _to_int(raw.get("intAwayScore"))
    status_text = str(raw.get("strStatus") or "").strip().upper()
    short_status = TSDB_STATUS.get(status_text, "")
    if not short_status:
        short_status = "FT" if home_goals is not None and away_goals is not None else "NS"
    finished = short_status in FINAL_STATUSES
    if not finished:
        home_goals = away_goals = None
    round_value = str(raw.get("intRound") or "").strip()
    round_label = f"Journee {round_value}" if round_value else ""
    return _fixture_payload(
        fixture_id=_free_fixture_id(league_id, season, moment, home_name, away_name),
        moment=moment,
        league_id=league_id,
        season=season,
        league_name=raw.get("strLeague") or info["name"],
        country=raw.get("strCountry") or info.get("country", ""),
        round_label=round_label,
        home_name=home_name,
        away_name=away_name,
        home_goals=home_goals,
        away_goals=away_goals,
        finished=finished,
        home_logo=(raw.get("strHomeTeamBadge") or "").strip(),
        away_logo=(raw.get("strAwayTeamBadge") or "").strip(),
        league_logo=(raw.get("strLeagueBadge") or "").strip(),
        venue_name=(raw.get("strVenue") or "").strip(),
        venue_city=(raw.get("strLocation") or "").strip(),
        source=SOURCE_LABELS["tsdb"],
    )


def _fixture_identity(item: dict) -> tuple[str, str, str]:
    date_value = ((item.get("fixture") or {}).get("date") or "")[:10]
    teams = item.get("teams") or {}
    home = (teams.get("home") or {}).get("name") or ""
    away = (teams.get("away") or {}).get("name") or ""
    return date_value, canonical_team_key(home), canonical_team_key(away)


def _is_finished(item: dict) -> bool:
    status = (item.get("fixture") or {}).get("status") or {}
    return status.get("short") in FINAL_STATUSES


def _has_odds(item: dict) -> bool:
    return any(value for value in (item.get("bookmaker_odds") or {}).values())


def _merge_pair(first: dict, second: dict) -> dict:
    if _is_finished(first) != _is_finished(second):
        primary, secondary = (first, second) if _is_finished(first) else (second, first)
    elif _has_odds(first) != _has_odds(second):
        primary, secondary = (first, second) if _has_odds(first) else (second, first)
    else:
        primary, secondary = first, second

    merged = copy.deepcopy(primary)
    for side in ("home", "away"):
        target = merged.setdefault("teams", {}).setdefault(side, {})
        source = (secondary.get("teams") or {}).get(side) or {}
        for field in ("logo", "id"):
            if not target.get(field) and source.get(field):
                target[field] = source[field]
        if not target.get("name") and source.get("name"):
            target["name"] = source["name"]

    league = merged.setdefault("league", {})
    other_league = secondary.get("league") or {}
    for field in ("logo", "flag", "round"):
        if not league.get(field) and other_league.get(field):
            league[field] = other_league[field]

    fixture = merged.setdefault("fixture", {})
    other_fixture = secondary.get("fixture") or {}
    for field in ("referee", "timestamp"):
        if not fixture.get(field) and other_fixture.get(field):
            fixture[field] = other_fixture[field]
    if not (fixture.get("venue") or {}).get("name"):
        fixture["venue"] = other_fixture.get("venue") or fixture.get("venue") or {}

    odds = dict(secondary.get("bookmaker_odds") or {})
    for key, value in (merged.get("bookmaker_odds") or {}).items():
        if value is not None:
            odds[key] = value
    merged["bookmaker_odds"] = odds

    sources: list[str] = []
    for item in (first, second):
        for source in item.get("sources") or [item.get("source")]:
            if source and source not in sources:
                sources.append(source)
    merged["sources"] = sources
    merged["source"] = " + ".join(sources)
    return merged


def _team_pair_identity(item: dict) -> tuple[str, str]:
    teams = item.get("teams") or {}
    home = (teams.get("home") or {}).get("name") or ""
    away = (teams.get("away") or {}).get("name") or ""
    return canonical_team_key(home), canonical_team_key(away)


def _fixture_date(item: dict) -> str:
    return ((item.get("fixture") or {}).get("date") or "")[:10]


def _dates_close(first: str, second: str, window_days: int = 10) -> bool:
    if not first or not second:
        return True
    try:
        left = date.fromisoformat(first)
        right = date.fromisoformat(second)
    except ValueError:
        return False
    return abs((left - right).days) <= window_days


def merge_fixtures(*groups: list[dict]) -> list[dict]:
    """Fusionne plusieurs listes en eliminant les doublons inter-sources.

    Deux passes :
    1. fusion exacte sur (date, equipe domicile, equipe exterieur) ;
    2. fusion par paire d'equipes pour les matchs reprogrammes ou dont les
       sources donnent une date legerement differente (calendrier approximatif,
       fuseau horaire). La fenetre de 10 jours evite de confondre l'aller et le
       retour d'une meme affiche.
    """
    merged: dict[tuple[str, str, str], dict] = {}
    for group in groups:
        for item in group or []:
            key = _fixture_identity(item)
            if key in merged:
                merged[key] = _merge_pair(merged[key], item)
            else:
                merged[key] = copy.deepcopy(item)

    by_teams: dict[tuple[str, str], list[dict]] = {}
    for item in merged.values():
        by_teams.setdefault(_team_pair_identity(item), []).append(item)

    items: list[dict] = []
    for group in by_teams.values():
        clusters: list[list[dict]] = []
        for item in group:
            moment = _fixture_date(item)
            for cluster in clusters:
                if any(_dates_close(_fixture_date(existing), moment) for existing in cluster):
                    cluster.append(item)
                    break
            else:
                clusters.append([item])
        for cluster in clusters:
            merged_item = cluster[0]
            for other in cluster[1:]:
                merged_item = _merge_pair(merged_item, other)
            items.append(merged_item)

    items.sort(key=lambda item: (item.get("fixture") or {}).get("date") or "")
    return items


def _french_form(value: str) -> str:
    mapping = {"W": "V", "D": "N", "L": "D"}
    return "".join(mapping.get(letter, letter) for letter in (value or "").upper())


def compute_standings_from_fixtures(
    fixtures: list[dict], league_id: int, season: int
) -> dict:
    """Calcule un classement simple a partir des matchs termines."""
    info = CSV_LEAGUES.get(
        int(league_id),
        FREE_LEAGUES.get(int(league_id), {"name": f"Ligue {league_id}", "country": ""}),
    )
    table: dict[int, dict] = {}
    ordered = sorted(fixtures, key=lambda item: item.get("fixture", {}).get("date") or "")
    for fixture in ordered:
        status = (fixture.get("fixture") or {}).get("status") or {}
        if status.get("short") not in FINAL_STATUSES:
            continue
        goals = fixture.get("goals") or {}
        home_goals = _to_int(goals.get("home"))
        away_goals = _to_int(goals.get("away"))
        if home_goals is None or away_goals is None:
            continue
        teams = fixture.get("teams") or {}
        for side, scored, conceded in (
            ("home", home_goals, away_goals),
            ("away", away_goals, home_goals),
        ):
            team = teams.get(side) or {}
            team_id = team.get("id")
            if team_id is None:
                continue
            entry = table.setdefault(
                int(team_id),
                {
                    "name": team.get("name") or "",
                    "played": 0,
                    "win": 0,
                    "draw": 0,
                    "lose": 0,
                    "gf": 0,
                    "ga": 0,
                    "form": [],
                },
            )
            entry["played"] += 1
            entry["gf"] += scored
            entry["ga"] += conceded
            if scored > conceded:
                entry["win"] += 1
                result = "V"
            elif scored == conceded:
                entry["draw"] += 1
                result = "N"
            else:
                entry["lose"] += 1
                result = "D"
            entry["form"].append(result)

    rows: list[dict] = []
    for team_id, entry in table.items():
        points = entry["win"] * 3 + entry["draw"]
        diff = entry["gf"] - entry["ga"]
        rows.append(
            {
                "rank": 0,
                "team": {"id": team_id, "name": entry["name"], "logo": ""},
                "points": points,
                "goalsDiff": diff,
                "group": "",
                "form": "".join(entry["form"][-5:]),
                "status": "",
                "description": "",
                "all": {
                    "played": entry["played"],
                    "win": entry["win"],
                    "draw": entry["draw"],
                    "lose": entry["lose"],
                    "goals": {"for": entry["gf"], "against": entry["ga"]},
                },
                "home": {},
                "away": {},
            }
        )
    rows.sort(
        key=lambda row: (
            -int(row["points"]),
            -int(row["goalsDiff"]),
            -int(row["all"]["goals"]["for"]),
            row["team"]["name"],
        )
    )
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return {
        "league": {
            "id": int(league_id),
            "name": info["name"],
            "country": info.get("country", ""),
            "logo": "",
            "season": int(season),
            "standings": [rows],
        }
    }


class _CachedHttpSource:
    """Petit utilitaire de cache pour les sources HTTP gratuites."""

    def __init__(self, config: Config, cache: MemoryCache):
        self.config = config
        self.cache = cache

    def _cached(self, key: str, force: bool) -> dict | None:
        if force:
            return None
        cached = self.cache.cache_get(key)
        if cached and cached["fresh"]:
            return {
                "data": cached["data"] or [],
                "cached": True,
                "fresh": True,
                "stale": False,
                "warning": None,
                "fetched_at": cached["fetched_at"],
                "expires_at": cached["expires_at"],
            }
        return None

    @staticmethod
    def _stale(cached: dict | None, warning: str) -> dict | None:
        if not cached:
            return None
        return {
            "data": cached["data"] or [],
            "cached": True,
            "fresh": False,
            "stale": True,
            "warning": warning,
            "fetched_at": cached["fetched_at"],
            "expires_at": cached["expires_at"],
        }

    def _store(
        self, key: str, endpoint: str, params: dict, data: Any, ttl: int, source: str
    ) -> dict:
        self.cache.cache_set(
            key,
            endpoint,
            params,
            data,
            ttl,
            meta={"source": source, "label": source},
        )
        now = time.time()
        return {
            "data": data,
            "cached": False,
            "fresh": True,
            "stale": False,
            "warning": None,
            "fetched_at": now,
            "expires_at": now + ttl,
        }


class FootballDataCsvSource(_CachedHttpSource):
    def _ttl(self, season: int) -> int:
        return 30 * 86400 if int(season) < date.today().year else 12 * 3600

    def season_fixtures(self, league_id: int, season: int, force: bool = False) -> dict:
        league_id = int(league_id)
        season = int(season)
        if league_id not in CSV_LEAGUES:
            raise SourceError(
                f"Aucun CSV football-data.co.uk pour la ligue {league_id}.", "source"
            )
        key = f"csv:season:{league_id}:{season}"
        cached = self.cache.cache_get(key)
        hit = self._cached(key, force)
        if hit:
            return hit
        try:
            response = requests.get(
                csv_url(league_id, season),
                timeout=30,
                headers={"User-Agent": "BettingMatrix/1.0"},
                allow_redirects=True,
            )
            if response.status_code == 404:
                raise SourceError(
                    f"Le fichier CSV {season} n'existe pas encore pour cette ligue.", "source"
                )
            response.raise_for_status()
            response.encoding = "ISO-8859-1"
            items = parse_football_data_csv(response.text, league_id, season)
            if not items:
                raise SourceError(
                    "Le fichier CSV ne contient aucun match exploitable.", "source"
                )
            return self._store(
                key,
                "csv:season",
                {"league": league_id, "season": season},
                items,
                self._ttl(season),
                SOURCE_LABELS["csv"],
            )
        except SourceError:
            stale = self._stale(cached, "CSV indisponible : donnees en cache utilisees.")
            if stale:
                return stale
            raise
        except requests.RequestException as exc:
            stale = self._stale(
                cached, f"Reseau indisponible ({exc}). Donnees CSV en cache utilisees."
            )
            if stale:
                return stale
            raise SourceNetworkError(
                "Impossible de telecharger les CSV football-data.co.uk. "
                "Verifiez votre connexion.",
                "network",
            ) from exc
        except Exception as exc:
            stale = self._stale(
                cached, f"Lecture CSV impossible ({exc}). Donnees en cache utilisees."
            )
            if stale:
                return stale
            raise SourceError(f"Lecture CSV impossible : {exc}", "source") from exc

    def standings(self, league_id: int, season: int, force: bool = False) -> dict:
        result = self.season_fixtures(league_id, season, force=force)
        payload = compute_standings_from_fixtures(
            result.get("data") or [], int(league_id), int(season)
        )
        return {**result, "data": [payload]}


class OpenFootballSource(_CachedHttpSource):
    def _ttl(self, season: int) -> int:
        return 30 * 86400 if int(season) < date.today().year else 12 * 3600

    def season_fixtures(self, league_id: int, season: int, force: bool = False) -> dict:
        league_id = int(league_id)
        season = int(season)
        info = OPENFOOTBALL_FILES.get(league_id)
        if not info:
            raise SourceError(
                f"OpenFootball ne couvre pas la ligue {league_id}.", "source"
            )
        key = f"openfootball:season:{league_id}:{season}"
        cached = self.cache.cache_get(key)
        hit = self._cached(key, force)
        if hit:
            return hit
        url = f"{OPENFOOTBALL_BASE}/{season_label(season)}/{info['file']}"
        try:
            response = requests.get(
                url, timeout=30, headers={"User-Agent": "BettingMatrix/1.0"}
            )
            if response.status_code == 404:
                raise SourceError(
                    f"Le calendrier OpenFootball {season_label(season)} n'existe pas encore.",
                    "source",
                )
            response.raise_for_status()
            body = response.json()
            items = [
                normalize_openfootball_match(raw, league_id, season)
                for raw in (body.get("matches") or [])
            ]
            if not items:
                raise SourceError("OpenFootball ne renvoie aucun match.", "source")
            return self._store(
                key,
                "openfootball:season",
                {"league": league_id, "season": season},
                items,
                self._ttl(season),
                SOURCE_LABELS["openfootball"],
            )
        except SourceError:
            stale = self._stale(
                cached, "OpenFootball indisponible : donnees en cache utilisees."
            )
            if stale:
                return stale
            raise
        except requests.RequestException as exc:
            stale = self._stale(
                cached,
                f"Reseau indisponible ({exc}). Donnees OpenFootball en cache utilisees.",
            )
            if stale:
                return stale
            raise SourceNetworkError(
                "Impossible de joindre OpenFootball. Verifiez votre connexion.", "network"
            ) from exc
        except (ValueError, TypeError) as exc:
            stale = self._stale(
                cached, "Reponse OpenFootball invalide : donnees en cache utilisees."
            )
            if stale:
                return stale
            raise SourceError(f"Reponse OpenFootball invalide : {exc}", "source") from exc


class OpenLigaDbSource(_CachedHttpSource):
    def _ttl(self, season: int) -> int:
        return 30 * 86400 if int(season) < date.today().year else 6 * 3600

    def season_fixtures(self, league_id: int, season: int, force: bool = False) -> dict:
        league_id = int(league_id)
        season = int(season)
        info = OPENLIGA_LEAGUES.get(league_id)
        if not info:
            raise SourceError(
                f"OpenLigaDB ne couvre pas la ligue {league_id}.", "source"
            )
        key = f"openliga:season:{league_id}:{season}"
        cached = self.cache.cache_get(key)
        hit = self._cached(key, force)
        if hit:
            return hit
        url = f"{OPENLIGA_BASE}/getmatchdata/{info['code']}/{season}"
        try:
            response = requests.get(
                url, timeout=30, headers={"User-Agent": "BettingMatrix/1.0"}
            )
            if response.status_code == 404:
                raise SourceError(
                    f"OpenLigaDB ne trouve pas la saison {season}.", "source"
                )
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, list) or not body:
                raise SourceError("OpenLigaDB ne renvoie aucun match.", "source")
            items = [
                normalize_openliga_match(raw, league_id, season) for raw in body
            ]
            return self._store(
                key,
                "openliga:season",
                {"league": league_id, "season": season},
                items,
                self._ttl(season),
                SOURCE_LABELS["openliga"],
            )
        except SourceError:
            stale = self._stale(
                cached, "OpenLigaDB indisponible : donnees en cache utilisees."
            )
            if stale:
                return stale
            raise
        except requests.RequestException as exc:
            stale = self._stale(
                cached,
                f"Reseau indisponible ({exc}). Donnees OpenLigaDB en cache utilisees.",
            )
            if stale:
                return stale
            raise SourceNetworkError(
                "Impossible de joindre OpenLigaDB. Verifiez votre connexion.", "network"
            ) from exc
        except (ValueError, TypeError) as exc:
            stale = self._stale(
                cached, "Reponse OpenLigaDB invalide : donnees en cache utilisees."
            )
            if stale:
                return stale
            raise SourceError(f"Reponse OpenLigaDB invalide : {exc}", "source") from exc


class TheSportsDbClient(_CachedHttpSource):
    """Client TheSportsDB utilisant la cle publique de demonstration."""

    def __init__(self, config: Config, cache: MemoryCache):
        super().__init__(config, cache)
        self._lock = threading.RLock()
        self._last_call = 0.0
        self._min_interval = max(0, getattr(config, "tsdb_min_interval_ms", 2000)) / 1000.0
        self._session = requests.Session()
        self._session.headers.update(
            {"Accept": "application/json", "User-Agent": "BettingMatrix/1.0"}
        )

    @property
    def key(self) -> str:
        return (getattr(self.config, "thesportsdb_key", "") or "123").strip() or "123"

    @property
    def available(self) -> bool:
        return bool(self.key)

    def _request(
        self,
        path: str,
        params: dict,
        cache_key: str,
        ttl: int,
        force: bool = False,
    ) -> dict:
        cached = self.cache.cache_get(cache_key)
        hit = self._cached(cache_key, force)
        if hit:
            return hit
        try:
            with self._lock:
                elapsed = time.monotonic() - self._last_call
                wait = self._min_interval - elapsed
                if wait > 0:
                    time.sleep(wait)
                self._last_call = time.monotonic()
                response = self._session.get(
                    f"{TSDB_BASE}/{self.key}/{path}", params=params, timeout=30
                )
            if response.status_code == 429:
                raise SourceRateLimitError(
                    "Limite TheSportsDB atteinte. Reessayez dans quelques instants.",
                    "rate_limit",
                )
            if response.status_code >= 400:
                raise SourceError(
                    f"TheSportsDB a renvoye HTTP {response.status_code}.", "source"
                )
            body = response.json()
        except SourceError:
            stale = self._stale(
                cached, "TheSportsDB indisponible : donnees en cache utilisees."
            )
            if stale:
                return stale
            raise
        except requests.RequestException as exc:
            stale = self._stale(
                cached, "Reseau indisponible : donnees TheSportsDB en cache utilisees."
            )
            if stale:
                return stale
            raise SourceNetworkError(
                "Impossible de joindre TheSportsDB. Verifiez votre connexion.", "network"
            ) from exc
        except ValueError as exc:
            raise SourceError("Reponse JSON invalide de TheSportsDB.", "source") from exc
        events = (body or {}).get("events") or []
        return self._store(
            cache_key,
            f"tsdb:{path}",
            params,
            events,
            ttl,
            SOURCE_LABELS["tsdb"],
        )

    def next_league_events(
        self, league_id: int, season: int, force: bool = False
    ) -> dict:
        info = TSDB_LEAGUES.get(int(league_id))
        if not info:
            raise SourceError(
                f"TheSportsDB ne couvre pas la ligue {league_id}.", "source"
            )
        result = self._request(
            "eventsnextleague.php",
            {"id": info["id"]},
            f"tsdb:next:{league_id}",
            30 * 60,
            force=force,
        )
        items = []
        for raw in result.get("data") or []:
            raw_season = str(raw.get("strSeason") or "")
            try:
                raw_year = int(raw_season[:4])
            except (TypeError, ValueError):
                raw_year = int(season)
            if raw_year and raw_year != int(season):
                continue
            items.append(normalize_tsdb_event(raw, int(league_id), int(season)))
        return {**result, "data": items}

    def season_events(
        self, league_id: int, season: int, force: bool = False
    ) -> dict:
        info = TSDB_LEAGUES.get(int(league_id))
        if not info:
            raise SourceError(
                f"TheSportsDB ne couvre pas la ligue {league_id}.", "source"
            )
        result = self._request(
            "eventsseason.php",
            {"id": info["id"], "s": season_label(season)},
            f"tsdb:season:{league_id}:{season}",
            12 * 3600 if int(season) >= date.today().year else 30 * 86400,
            force=force,
        )
        items = [
            normalize_tsdb_event(raw, int(league_id), int(season))
            for raw in result.get("data") or []
        ]
        return {**result, "data": items}

    def events_by_date(self, date_str: str, force: bool = False) -> dict:
        result = self._request(
            "eventsday.php",
            {"d": date_str, "s": "Soccer"},
            f"tsdb:day:{date_str}",
            15 * 60,
            force=force,
        )
        items = []
        for raw in result.get("data") or []:
            league_id = next(
                (
                    lid
                    for lid, info in TSDB_LEAGUES.items()
                    if str(info["id"]) == str(raw.get("idLeague"))
                ),
                None,
            )
            if league_id is None:
                continue
            raw_season = str(raw.get("strSeason") or "")
            try:
                season = int(raw_season[:4])
            except (TypeError, ValueError):
                season = season_start_year(date.fromisoformat(date_str))
            items.append(normalize_tsdb_event(raw, league_id, season))
        return {**result, "data": items}


class FreeSources:
    """Facade qui combine toutes les sources gratuites."""

    def __init__(self, config: Config, cache: MemoryCache):
        self.config = config
        self.cache = cache
        self.csv = FootballDataCsvSource(config, cache)
        self.openfootball = OpenFootballSource(config, cache)
        self.openliga = OpenLigaDbSource(config, cache)
        self.tsdb = TheSportsDbClient(config, cache)

    @property
    def supported_leagues(self) -> set[int]:
        return set(FREE_LEAGUES)

    def season_fixtures(self, league_id: int, season: int, force: bool = False) -> dict:
        league_id = int(league_id)
        season = int(season)
        if not free_source_supports(league_id, season):
            raise SourceError(
                f"Les sources gratuites ne couvrent pas la ligue {league_id} "
                f"pour la saison {season}. Ligues couvertes : La Liga, "
                "Premier League, Bundesliga, Serie A, Ligue 1 et Ligue des "
                "Champions (saison en cours).",
                "source",
            )
        groups: list[list[dict]] = []
        sources: list[str] = []
        warnings: list[str] = []
        cached_flags: list[bool] = []
        fetched: list[float] = []
        expires: list[float] = []

        def collect(label: str, loader) -> None:
            try:
                result = loader()
            except SourceError as exc:
                warnings.append(f"{label} : {exc.user_message()}")
                return
            items = result.get("data") or []
            if items:
                groups.append(items)
                if label not in sources:
                    sources.append(label)
            cached_flags.append(bool(result.get("cached")))
            if result.get("warning"):
                warnings.append(str(result["warning"]))
            if result.get("fetched_at"):
                fetched.append(float(result["fetched_at"]))
            if result.get("expires_at"):
                expires.append(float(result["expires_at"]))

        if league_id in CSV_LEAGUES:
            collect(
                SOURCE_LABELS["csv"],
                lambda: self.csv.season_fixtures(league_id, season, force=force),
            )
        if league_id in OPENLIGA_LEAGUES:
            collect(
                SOURCE_LABELS["openliga"],
                lambda: self.openliga.season_fixtures(league_id, season, force=force),
            )
        if league_id in OPENFOOTBALL_FILES:
            collect(
                SOURCE_LABELS["openfootball"],
                lambda: self.openfootball.season_fixtures(league_id, season, force=force),
            )
        if league_id in TSDB_LEAGUES:
            collect(
                SOURCE_LABELS["tsdb"],
                lambda: self.tsdb.season_events(league_id, season, force=force),
            )
            if season >= season_start_year(date.today()):
                collect(
                    SOURCE_LABELS["tsdb"],
                    lambda: self.tsdb.next_league_events(league_id, season, force=force),
                )

        items = merge_fixtures(*groups)
        if not items:
            detail = " ".join(warnings[:3])
            raise SourceError(
                "Aucune donnee gratuite disponible pour cette ligue et cette saison. "
                + detail,
                "source",
            )

        if league_id == 2:
            warnings.append(
                "Ligue des Champions : calendrier partiel via la cle publique TheSportsDB. "
                "Le classement est calcule sur les matchs disponibles."
            )
        if any(not _is_finished(item) for item in items):
            warnings.append(
                "Les matchs a venir n'ont pas de cotes CSV : saisissez vos cotes "
                "manuellement dans la page Analyse."
            )

        warning = " | ".join(dict.fromkeys(w for w in warnings if w)) or None
        return {
            "data": items,
            "cached": any(cached_flags),
            "fresh": True,
            "stale": False,
            "warning": warning,
            "fetched_at": min(fetched) if fetched else time.time(),
            "expires_at": min(expires) if expires else time.time(),
            "sources": sources,
            "source": " + ".join(sources),
        }

    def fixtures_by_date(
        self, date_str: str, tracked_leagues: list[dict], force: bool = False
    ) -> dict:
        try:
            day = date.fromisoformat(date_str)
        except ValueError as exc:
            raise SourceError(f"Date invalide : {date_str}", "source") from exc
        season = season_start_year(day)
        tracked_ids = {int(league.get("id") or -1) for league in tracked_leagues}
        groups: list[list[dict]] = []
        sources: list[str] = []
        warnings: list[str] = []
        cached_flags: list[bool] = []
        fetched: list[float] = []
        expires: list[float] = []

        for league in tracked_leagues:
            league_id = int(league.get("id") or -1)
            if league_id not in FREE_LEAGUES:
                continue
            try:
                result = self.season_fixtures(league_id, season, force=force)
            except SourceError as exc:
                warnings.append(
                    f"{league.get('name') or league_id} : {exc.user_message()}"
                )
                continue
            day_items = [
                item
                for item in result.get("data") or []
                if (item.get("fixture") or {}).get("date", "")[:10] == date_str
            ]
            if day_items:
                groups.append(day_items)
                for source in result.get("sources") or []:
                    if source not in sources:
                        sources.append(source)
            cached_flags.append(bool(result.get("cached")))
            if result.get("fetched_at"):
                fetched.append(float(result["fetched_at"]))
            if result.get("expires_at"):
                expires.append(float(result["expires_at"]))

        if not any(groups) and any(lid in TSDB_LEAGUES for lid in tracked_ids):
            try:
                result = self.tsdb.events_by_date(date_str, force=force)
                day_items = [
                    item
                    for item in result.get("data") or []
                    if int((item.get("league") or {}).get("id") or -1) in tracked_ids
                ]
                if day_items:
                    groups.append(day_items)
                    if SOURCE_LABELS["tsdb"] not in sources:
                        sources.append(SOURCE_LABELS["tsdb"])
                cached_flags.append(bool(result.get("cached")))
                if result.get("fetched_at"):
                    fetched.append(float(result["fetched_at"]))
            except SourceError as exc:
                warnings.append(f"TheSportsDB : {exc.user_message()}")

        items = merge_fixtures(*groups)
        warning = " | ".join(dict.fromkeys(w for w in warnings if w)) or None
        return {
            "data": items,
            "cached": any(cached_flags),
            "fresh": True,
            "stale": False,
            "warning": warning,
            "fetched_at": min(fetched) if fetched else time.time(),
            "expires_at": min(expires) if expires else time.time(),
            "sources": sources,
            "source": " + ".join(sources),
        }

    def standings(self, league_id: int, season: int, force: bool = False) -> dict:
        result = self.season_fixtures(league_id, season, force=force)
        payload = compute_standings_from_fixtures(
            result.get("data") or [], int(league_id), int(season)
        )
        rows = ((payload.get("league") or {}).get("standings") or [[]])[0]
        warning = result.get("warning")
        if warning:
            warning = " | ".join(
                part
                for part in warning.split(" | ")
                if "cotes CSV" not in part
            ) or None
        if not rows:
            empty = (
                "Aucun resultat termine ne permet encore de calculer ce classement. "
                "Les calendriers sont disponibles, mais les journees ne sont pas jouees."
            )
            warning = f"{warning} | {empty}" if warning else empty
        if int(league_id) == 2:
            partial = "Classement partiel : seuls les matchs disponibles sont comptabilises."
            warning = f"{warning} | {partial}" if warning else partial
        return {**result, "data": [payload], "warning": warning}

    def find_fixture(
        self, fixture_id: int, tracked_leagues: list[dict], seasons: tuple[int, ...]
    ) -> dict | None:
        for league in tracked_leagues:
            league_id = int(league.get("id") or -1)
            if league_id not in FREE_LEAGUES:
                continue
            for season in seasons:
                try:
                    result = self.season_fixtures(league_id, int(season))
                except SourceError:
                    continue
                for item in result.get("data") or []:
                    if int((item.get("fixture") or {}).get("id") or -1) == int(fixture_id):
                        return item
        return None

    @staticmethod
    def odds_from_fixture(fixture: dict) -> dict[str, dict]:
        raw = fixture.get("bookmaker_odds") or {}
        odds: dict[str, dict] = {}
        for key in ("home", "draw", "away", "over25", "under25", "btts_yes", "btts_no"):
            value = raw.get(key)
            if value:
                try:
                    odd = float(value)
                except (TypeError, ValueError):
                    continue
                if odd > 1.0:
                    odds[key] = {"odd": round(odd, 3), "bookmaker": SOURCE_LABELS["csv"]}
        return odds
