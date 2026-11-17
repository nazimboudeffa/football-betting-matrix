"""Importe les CSV gratuits football-data.co.uk dans le cache memoire.

Aucune cle API n'est necessaire.

Usage :
    python scripts/import_football_data.py
    python scripts/import_football_data.py --seasons 2026,2025
    python scripts/import_football_data.py --seasons 2026,2025 --leagues 140,39,78,135,61
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from betting_matrix.config import FREE_SEASONS, load_config  # noqa: E402
from betting_matrix.errors import SourceError  # noqa: E402
from betting_matrix.service import DataService  # noqa: E402
from betting_matrix.store import JsonSettingsStore, MemoryCache  # noqa: E402
from betting_matrix.sources import CSV_LEAGUES  # noqa: E402


def _parse_ints(value: str) -> tuple[int, ...]:
    items: list[int] = []
    for chunk in value.split(","):
        try:
            items.append(int(chunk.strip()))
        except ValueError:
            continue
    return tuple(items)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Importe les resultats et cotes football-data.co.uk."
    )
    parser.add_argument(
        "--seasons",
        type=str,
        default=",".join(str(season) for season in FREE_SEASONS),
        help=(
            "Saisons separees par des virgules (defaut : "
            + ",".join(str(season) for season in FREE_SEASONS)
            + ")."
        ),
    )
    parser.add_argument(
        "--leagues",
        type=str,
        default=",".join(str(league_id) for league_id in CSV_LEAGUES),
        help=(
            "IDs de ligues separees par des virgules (defaut : "
            + ",".join(str(league_id) for league_id in CSV_LEAGUES)
            + ")."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignorer le cache et retelecharger les CSV.",
    )
    args = parser.parse_args()

    seasons = _parse_ints(args.seasons)
    leagues = _parse_ints(args.leagues)
    if not seasons or not leagues:
        print("Erreur : saisons ou ligues invalides.")
        return 1

    config = load_config()
    cache = MemoryCache()
    service = DataService(config, cache, JsonSettingsStore(config.settings_path))
    failures = 0

    for league_id in leagues:
        league_name = (CSV_LEAGUES.get(league_id) or {}).get(
            "name", f"Ligue {league_id}"
        )
        for season in seasons:
            try:
                result = service.free.csv.season_fixtures(
                    league_id, season, force=args.force
                )
                items = result.get("data") or []
                finished = sum(
                    1
                    for item in items
                    if (item.get("fixture") or {}).get("status", {}).get("short")
                    in {"FT", "AET", "PEN"}
                )
                with_odds = sum(
                    1
                    for item in items
                    if any((item.get("bookmaker_odds") or {}).values())
                )
                standings = service.free.standings(league_id, season, force=False)
                rows = (
                    ((standings.get("data") or [{}])[0].get("league") or {})
                    .get("standings")
                    or [[]]
                )[0]
                print(
                    f"{league_name} {season} : {len(items)} match(s), "
                    f"{finished} termine(s), {with_odds} avec cotes, "
                    f"{len(rows)} equipe(s) au classement."
                )
                if result.get("warning"):
                    print(f"  ! {result['warning']}")
            except SourceError as exc:
                failures += 1
                print(f"{league_name} {season} : echec - {exc.user_message()}")
            except Exception as exc:  # pragma: no cover - garde-fou CLI
                failures += 1
                print(f"{league_name} {season} : erreur inattendue - {exc}")

    stats = service.cache_stats()
    print(f"\nCache session : {stats['entries']} entree(s), {stats['bytes'] / 1024:.0f} Ko")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
