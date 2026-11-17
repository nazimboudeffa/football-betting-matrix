"""Service de donnees : normalisation des reponses et operations metier."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Callable

from .analysis import market_summary
from .config import DEFAULT_LEAGUES, DEFAULT_OLLAMA_URL, DEFAULT_SETTINGS, Config
from .errors import SourceError
from .sources import (
    FREE_LEAGUES,
    SOURCE_LABELS,
    FreeSources,
    free_source_supports,
    season_start_year,
)
from .store import JsonSettingsStore, MemoryCache
from .strategies import DEFAULT_STRATEGY_ID, StrategyCatalog, load_strategies, strategies_dir

STATUS_LABELS = {
    "TBD": "A venir",
    "NS": "A venir",
    "1H": "1re mi-temps",
    "HT": "Mi-temps",
    "2H": "2e mi-temps",
    "ET": "Prolongation",
    "BT": "Pause prolongation",
    "P": "Tirs au but",
    "SUSP": "Suspendu",
    "INT": "Interrompu",
    "FT": "Termine",
    "AET": "Termine (a.p.)",
    "PEN": "Termine (tab)",
    "PST": "Reporte",
    "CANC": "Annule",
    "ABD": "Abandonne",
    "AWD": "Attribue",
    "WO": "Forfait",
    "LIVE": "En direct",
}

FINAL_STATUSES = {"FT", "AET", "PEN"}


def normalize_fixture(raw: dict) -> dict:
    fixture = raw.get("fixture") or {}
    league = raw.get("league") or {}
    teams = raw.get("teams") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    goals = raw.get("goals") or {}
    status = fixture.get("status") or {}
    venue = fixture.get("venue") or {}
    score = raw.get("score") or {}
    short_status = status.get("short") or "NS"
    source = raw.get("source") or ""
    sources = raw.get("sources") or ([source] if source else [])
    return {
        "id": fixture.get("id"),
        "date": fixture.get("date"),
        "timestamp": fixture.get("timestamp"),
        "referee": fixture.get("referee"),
        "venue": {"name": venue.get("name") or "", "city": venue.get("city") or ""},
        "status": {
            "short": short_status,
            "long": status.get("long") or "",
            "elapsed": status.get("elapsed"),
            "label": STATUS_LABELS.get(short_status, status.get("long") or short_status),
            "finished": short_status in FINAL_STATUSES,
        },
        "league": {
            "id": league.get("id"),
            "name": league.get("name") or "",
            "country": league.get("country") or "",
            "logo": league.get("logo") or "",
            "flag": league.get("flag") or "",
            "season": league.get("season"),
            "round": league.get("round") or "",
        },
        "home": {
            "id": home.get("id"),
            "name": home.get("name") or "Equipe domicile",
            "logo": home.get("logo") or "",
            "winner": home.get("winner"),
        },
        "away": {
            "id": away.get("id"),
            "name": away.get("name") or "Equipe exterieur",
            "logo": away.get("logo") or "",
            "winner": away.get("winner"),
        },
        "goals": {"home": goals.get("home"), "away": goals.get("away")},
        "score": score,
        "source": source,
        "sources": sources,
        "bookmaker_odds": raw.get("bookmaker_odds") or {},
        "xg": raw.get("xg") or {},
        "stats": raw.get("stats") or {},
        "market": raw.get("market") or {},
        "raw": raw,
    }


def normalize_standing_row(row: dict) -> dict:
    team = row.get("team") or {}
    return {
        "rank": row.get("rank"),
        "team": {
            "id": team.get("id"),
            "name": team.get("name") or "",
            "logo": team.get("logo") or "",
        },
        "points": row.get("points"),
        "goals_diff": row.get("goalsDiff"),
        "group": row.get("group") or "",
        "form": row.get("form") or "",
        "status": row.get("status") or "",
        "description": row.get("description") or "",
        "all": row.get("all") or {},
        "home": row.get("home") or {},
        "away": row.get("away") or {},
    }


def available_leagues_text() -> str:
    """Liste des ligues couvertes, construite depuis les sources gratuites."""
    return ", ".join(
        f"{info['name']} ({league_id})"
        for league_id, info in sorted(
            FREE_LEAGUES.items(), key=lambda item: item[1]["name"]
        )
    )


def _sorted_league_ids() -> list[int]:
    return [
        int(league_id)
        for league_id, _ in sorted(
            FREE_LEAGUES.items(),
            key=lambda item: (item[1]["country"], item[1]["name"]),
        )
    ]


def _free_meta(result: dict) -> dict:
    return {
        "cached": bool(result.get("cached")),
        "stale": bool(result.get("stale")),
        "fresh": bool(result.get("fresh", True)),
        "warning": result.get("warning"),
        "fetched_at": result.get("fetched_at"),
        "expires_at": result.get("expires_at"),
        "source": result.get("source") or "",
        "sources": list(result.get("sources") or []),
    }


class DataService:
    def __init__(self, config: Config, cache: MemoryCache, settings: JsonSettingsStore):
        self.config = config
        self.cache = cache
        self.settings_store = settings
        self.strategies = load_strategies(strategies_dir(config.root_dir))
        self.free = FreeSources(config, cache)

    # --------------------------------------------------------------- reglages

    def settings(self) -> dict:
        return self.settings_store.get_settings(DEFAULT_SETTINGS)

    def save_settings(self, settings: dict) -> dict:
        self.settings_store.save_settings(settings)
        return settings

    def value_strategy_id(self) -> str:
        return str(self.settings().get("value_strategy") or DEFAULT_STRATEGY_ID)

    def set_value_strategy(self, strategy_id: str) -> None:
        settings = self.settings()
        settings["value_strategy"] = strategy_id
        self.save_settings(settings)

    def reload_strategies(self) -> StrategyCatalog:
        self.strategies = load_strategies(strategies_dir(self.config.root_dir))
        return self.strategies

    def ollama_url(self) -> str:
        value = str(self.settings().get("ollama_url") or "").strip().rstrip("/")
        return value or DEFAULT_OLLAMA_URL

    def ollama_model(self) -> str:
        return str(self.settings().get("ollama_model") or "").strip()

    def set_ollama_model(self, model: str) -> None:
        settings = self.settings()
        settings["ollama_model"] = (model or "").strip()
        self.save_settings(settings)

    def update_settings(self, patch: dict) -> dict:
        settings = self.settings()
        if "default_season" in patch:
            try:
                season = int(patch["default_season"])
                if season in self.config.seasons:
                    settings["default_season"] = season
            except (TypeError, ValueError):
                pass
        if "ollama_url" in patch:
            url = str(patch["ollama_url"] or "").strip().rstrip("/")
            settings["ollama_url"] = url or DEFAULT_OLLAMA_URL
        return self.save_settings(settings)

    def tracked_leagues(self) -> list[dict]:
        return list(self.settings().get("tracked_leagues") or [])

    def _available_order(self) -> list[int]:
        """Ordre des ligues non suivies (les plus recentes retirees en fin)."""
        settings = self.settings()
        stored = [int(value) for value in settings.get("available_league_order") or []]
        order = [lid for lid in stored if lid in FREE_LEAGUES]
        for league_id in _sorted_league_ids():
            if league_id not in order:
                order.append(league_id)
        return order

    def available_leagues(self) -> list[dict]:
        """Ligues couvertes qui ne sont pas encore suivies."""
        tracked = {int(league.get("id", -1)) for league in self.tracked_leagues()}
        leagues: list[dict] = []
        for league_id in self._available_order():
            if league_id in tracked:
                continue
            info = FREE_LEAGUES[league_id]
            leagues.append(
                {
                    "id": league_id,
                    "name": info.get("name") or f"Ligue {league_id}",
                    "country": info.get("country") or "",
                    "logo": "",
                    "flag": "",
                    "type": "League",
                }
            )
        return leagues

    def add_league(self, league: dict) -> list[dict]:
        league_id = int(league.get("id", -1))
        info = FREE_LEAGUES.get(league_id)
        if not info:
            raise SourceError(
                "Cette ligue n'est pas couverte par les sources gratuites. "
                f"Ligues disponibles : {available_leagues_text()}.",
                "source",
            )
        settings = self.settings()
        leagues = settings.get("tracked_leagues") or []
        if any(int(existing.get("id", -1)) == league_id for existing in leagues):
            return leagues
        leagues.insert(
            0,
            {
                "id": league_id,
                "name": info.get("name") or f"Ligue {league_id}",
                "country": info.get("country") or "",
                "logo": "",
                "flag": "",
                "default": False,
            },
        )
        order = self._available_order()
        settings["available_league_order"] = [
            lid for lid in order if lid != league_id
        ]
        settings["tracked_leagues"] = leagues
        self.save_settings(settings)
        return leagues

    def remove_league(self, league_id: int) -> list[dict]:
        settings = self.settings()
        before = settings.get("tracked_leagues") or []
        after = [
            league
            for league in before
            if int(league.get("id", -1)) != int(league_id)
        ]
        if len(after) != len(before):
            order = [
                lid for lid in self._available_order() if lid != int(league_id)
            ]
            order.append(int(league_id))
            settings["available_league_order"] = order
        settings["tracked_leagues"] = after
        self.save_settings(settings)
        return after

    def restore_default_leagues(self) -> list[dict]:
        settings = self.settings()
        settings["tracked_leagues"] = [dict(league) for league in DEFAULT_LEAGUES]
        settings["available_league_order"] = _sorted_league_ids()
        self.save_settings(settings)
        return settings["tracked_leagues"]

    # --------------------------------------------------------------- fixtures

    def fixtures_by_date(self, date_str: str, force: bool = False) -> dict:
        try:
            day = date.fromisoformat(date_str)
        except ValueError:
            day = date.today()
        season = season_start_year(day)
        tracked = self.tracked_leagues()
        result = self.free.fixtures_by_date(date_str, tracked, force=force)
        items = [normalize_fixture(item) for item in result.get("data") or []]
        items.sort(key=lambda item: item.get("date") or "")
        return {
            "items": items,
            "total_worldwide": len(items),
            "date": date_str,
            "season": season,
            **_free_meta(result),
        }

    def season_fixtures(self, league_id: int, season: int, force: bool = False) -> dict:
        result = self.free.season_fixtures(league_id, season, force=force)
        items = [normalize_fixture(item) for item in result.get("data") or []]
        items.sort(key=lambda item: item.get("date") or "")
        return {
            "items": items,
            "league_id": int(league_id),
            "season": int(season),
            **_free_meta(result),
        }

    def fixture(self, fixture_id: int) -> dict | None:
        raw = self.free.find_fixture(
            int(fixture_id), self.tracked_leagues(), self.config.seasons
        )
        return normalize_fixture(raw) if raw else None

    def odds_for_fixture(self, fixture: int | dict, force: bool = False) -> dict:
        if isinstance(fixture, dict):
            item = fixture
        else:
            item = self.free.find_fixture(
                int(fixture), self.tracked_leagues(), self.config.seasons
            )
            if item is None:
                raise SourceError(
                    f"Match {fixture} introuvable dans les sources gratuites.", "source"
                )
        fixture_id = int(item.get("id") or 0)
        odds = self.free.odds_from_fixture(item)
        warning = None
        if not odds:
            warning = "Cotes non disponibles pour ce match gratuit."
        return {
            "odds": odds,
            "bookmaker_count": 1 if odds else 0,
            "bookmakers": [SOURCE_LABELS["csv"]] if odds else [],
            "entries": len(odds),
            "cached": True,
            "stale": False,
            "fresh": True,
            "warning": warning,
            "fetched_at": None,
            "expires_at": None,
            "fixture_id": fixture_id,
            "source": SOURCE_LABELS["csv"] if odds else "",
        }

    def standings(self, league_id: int, season: int, force: bool = False) -> dict:
        try:
            result = self.free.standings(league_id, season, force=force)
        except SourceError as exc:
            info = FREE_LEAGUES.get(int(league_id), {})
            return {
                "league": {
                    "id": int(league_id),
                    "name": info.get("name") or f"Ligue {league_id}",
                    "country": info.get("country") or "",
                    "logo": "",
                    "season": int(season),
                },
                "groups": [],
                "cached": False,
                "stale": False,
                "fresh": False,
                "warning": exc.user_message(),
                "fetched_at": None,
                "expires_at": None,
                "source": "",
                "sources": [],
            }
        payload = (result.get("data") or [{}])[0]
        meta = _free_meta(result)
        league = payload.get("league") or {}
        groups_raw = league.get("standings") or []
        groups = []
        for index, rows in enumerate(groups_raw):
            normalized = [normalize_standing_row(row) for row in rows or []]
            if not normalized:
                continue
            name = normalized[0].get("group") or (
                "Classement" if len(groups_raw) == 1 else f"Groupe {index + 1}"
            )
            groups.append({"name": name, "rows": normalized})
        league_payload = {
            "id": league.get("id"),
            "name": league.get("name") or "",
            "country": league.get("country") or "",
            "logo": league.get("logo") or "",
            "season": league.get("season"),
        }
        if not groups:
            result_payload = {
                **meta,
                "league": league_payload,
                "groups": [],
            }
            result_payload["warning"] = result_payload.get("warning") or (
                "Aucun resultat termine ne permet encore de calculer ce classement. "
                "Les calendriers sont disponibles, mais les journees ne sont pas jouees."
            )
            return result_payload
        return {
            "league": league_payload,
            "groups": groups,
            **meta,
        }

    # ---------------------------------------------------------------- ligues

    def search_leagues(self, query: str) -> list[dict]:
        query = (query or "").strip()
        if len(query) < 2:
            return []
        needle = query.lower()
        leagues = [
            {
                "id": info["id"],
                "name": info["name"],
                "type": "League",
                "country": info["country"],
                "logo": "",
                "flag": "",
                "seasons": list(self.config.seasons),
                "current_season": self.config.default_season,
            }
            for info in FREE_LEAGUES.values()
            if needle in info["name"].lower() or needle in info["country"].lower()
        ]
        leagues.sort(key=lambda item: (item.get("country") or "", item.get("name") or ""))
        return leagues

    def league_info(self, league_id: int) -> dict | None:
        info = FREE_LEAGUES.get(int(league_id))
        if not info:
            raise SourceError(
                f"Les sources gratuites couvrent : {available_leagues_text()}.",
                "source",
            )
        return {
            "id": info["id"],
            "name": info["name"],
            "type": "League",
            "logo": "",
            "country": info["country"],
            "flag": "",
            "seasons": list(self.config.seasons),
            "current_season": self.config.default_season,
        }

    # --------------------------------------------------------------- analyse

    @staticmethod
    def _referee_profile(
        fixtures: list[dict], referee: str | None, before_date: str | None = None
    ) -> dict | None:
        """Statistiques descriptives d'un arbitre sur les matchs deja joues."""
        name = (referee or "").strip().casefold()
        if not name:
            return None
        matches: list[dict] = []
        for item in fixtures:
            if (item.get("referee") or "").strip().casefold() != name:
                continue
            if before_date:
                day = (item.get("date") or "")[:10]
                if day and day >= before_date:
                    continue
            stats = item.get("stats") or {}
            if stats:
                matches.append(stats)
        if not matches:
            return None

        def average(field: str) -> float | None:
            values: list[float] = []
            for stats in matches:
                side = stats.get(field) or {}
                home = side.get("home")
                away = side.get("away")
                if home is None and away is None:
                    continue
                values.append(float(home or 0) + float(away or 0))
            return round(sum(values) / len(values), 2) if values else None

        return {
            "name": referee.strip(),
            "matches": len(matches),
            "yellow_per_game": average("yellow_cards"),
            "red_per_game": average("red_cards"),
            "fouls_per_game": average("fouls"),
        }

    def analyze_fixture(self, fixture: dict, season: int, force: bool = False) -> dict:
        league_id = int(fixture["league"]["id"])
        season_data = self.season_fixtures(league_id, season, force=force)
        fixtures = season_data["items"]
        if not fixtures:
            raise SourceError(
                f"Aucun match disponible pour la ligue {league_id} en {season}. "
                "Essayez une autre saison ou verifiez les sources gratuites.",
                "source",
            )
        fixture_season = fixture.get("league", {}).get("season")
        before_date = None
        if str(fixture_season) == str(season):
            date_value = (fixture.get("date") or "")[:10]
            if date_value:
                before_date = date_value
        selected = self.strategies.get(self.value_strategy_id())
        analyzer = selected if selected and selected.analyze else self.strategies.probability_model()
        if analyzer is None or analyzer.analyze is None:
            raise SourceError(
                "Aucune strategie ne fournit de modele de probabilites dans user_strategies/.",
                "config",
            )
        model = analyzer.analyze(
            fixtures,
            fixture.get("home", {}).get("id"),
            fixture.get("away", {}).get("id"),
            fixture.get("home", {}).get("name") or "",
            fixture.get("away", {}).get("name") or "",
            before_date=before_date,
        )
        model["league_id"] = league_id
        model["season"] = season
        model["fixture"] = fixture
        model["context"] = {
            "xg": fixture.get("xg") or {},
            "stats": fixture.get("stats") or {},
            "market": market_summary(fixture.get("market") or {}),
            "referee": self._referee_profile(
                fixtures, fixture.get("referee"), before_date
            ),
        }
        model["_meta"] = {
            k: season_data.get(k)
            for k in ("cached", "stale", "warning", "fetched_at", "source", "sources")
        }
        model["_meta"]["model_strategy"] = model.get("model_name") or analyzer.name
        return model

    # -------------------------------------------------------------- warmup

    def warmup(
        self,
        progress: Callable[[int, int, str], None] | None = None,
        seasons: tuple[int, ...] | list[int] | None = None,
    ) -> dict:
        today = date.today()
        settings = self.settings()
        leagues = settings.get("tracked_leagues") or []
        if seasons is None:
            seasons = self.config.seasons
        selected = [int(season) for season in seasons]
        if not selected:
            selected = [int(settings.get("default_season") or self.config.default_season)]
        steps: list[tuple[str, Callable[[], Any]]] = [
            (
                "Matchs d'aujourd'hui",
                lambda: self.fixtures_by_date(today.isoformat()),
            ),
            (
                "Matchs de demain",
                lambda: self.fixtures_by_date((today + timedelta(days=1)).isoformat()),
            ),
        ]
        for league in leagues:
            league_id = int(league["id"])
            league_name = league.get("name") or f"Ligue {league_id}"
            for season in selected:
                if not free_source_supports(league_id, season):
                    continue
                steps.append(
                    (
                        f"Classement {league_name} ({season})",
                        lambda lid=league_id, s=season: self.standings(lid, s),
                    )
                )
                steps.append(
                    (
                        f"Saison {league_name} ({season})",
                        lambda lid=league_id, s=season: self.season_fixtures(lid, s),
                    )
                )

        errors: list[str] = []
        results: list[dict] = []
        total = len(steps)
        for index, (label, fn) in enumerate(steps, start=1):
            if progress:
                progress(index, total, label)
            try:
                value = fn()
                results.append({"label": label, "ok": True, "warning": (value or {}).get("warning")})
            except SourceError as exc:
                errors.append(f"{label} : {exc.user_message()}")
                results.append({"label": label, "ok": False, "error": exc.user_message()})
            except Exception as exc:  # pragma: no cover - garde-fou UI
                errors.append(f"{label} : {exc}")
                results.append({"label": label, "ok": False, "error": str(exc)})
        return {"steps": results, "errors": errors, "total": total}

    # ------------------------------------------------------------- helpers

    @staticmethod
    def date_window() -> tuple[date, date, date]:
        today = date.today()
        return today - timedelta(days=1), today, today + timedelta(days=1)

    def cache_stats(self) -> dict:
        return self.cache.cache_stats()

    def cache_list(self, limit: int = 300) -> list[dict]:
        return self.cache.cache_list(limit)

    def cache_clear(self, prefix: str | None = None) -> int:
        return self.cache.cache_clear(prefix)

    @staticmethod
    def format_kickoff(iso_date: str | None) -> str:
        if not iso_date:
            return "Date inconnue"
        try:
            dt = datetime.fromisoformat(iso_date)
            local = dt.astimezone()
            return local.strftime("%d/%m %H:%M")
        except (ValueError, TypeError):
            return iso_date[:16].replace("T", " ")

    @staticmethod
    def format_day(iso_date: str | None) -> str:
        if not iso_date:
            return ""
        try:
            dt = datetime.fromisoformat(iso_date)
            return dt.astimezone().strftime("%d/%m/%Y")
        except (ValueError, TypeError):
            return iso_date[:10]
