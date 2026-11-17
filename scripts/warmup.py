"""Verifie le chargement des donnees sans ouvrir l'interface.

Usage :
    python scripts/warmup.py
    python scripts/warmup.py --seasons 2026,2025
    python scripts/warmup.py --season 2025

Toutes les saisons utilisent les sources gratuites. Le cache est conserve en
memoire pendant l'execution du script, sans base de donnees.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from football_betting_matrix.config import FREE_SEASONS, load_config  # noqa: E402
from football_betting_matrix.service import DataService  # noqa: E402
from football_betting_matrix.store import JsonSettingsStore, MemoryCache  # noqa: E402
from football_betting_matrix.sources import free_source_supports  # noqa: E402


def _parse_seasons(value: str) -> tuple[int, ...]:
    seasons: list[int] = []
    for chunk in value.split(","):
        try:
            seasons.append(int(chunk.strip()))
        except ValueError:
            continue
    return tuple(seasons)


def main() -> int:
    parser = argparse.ArgumentParser(description="Precharge le cache de Betting Matrix.")
    parser.add_argument(
        "--season",
        type=int,
        default=None,
        help="Saison unique a precharger (raccourci de --seasons).",
    )
    parser.add_argument(
        "--seasons",
        type=str,
        default=None,
        help=(
            "Saisons separees par des virgules (defaut : "
            + ",".join(str(season) for season in FREE_SEASONS)
            + ")."
        ),
    )
    args = parser.parse_args()

    config = load_config()
    if args.season is not None:
        selected = (args.season,)
    elif args.seasons:
        selected = _parse_seasons(args.seasons)
    else:
        selected = FREE_SEASONS
    if not selected:
        selected = FREE_SEASONS

    unknown = [season for season in selected if season not in config.seasons]
    if unknown:
        print(
            "Erreur : saison(s) non configuree(s) : "
            + ", ".join(str(season) for season in unknown)
            + f". Saisons disponibles : {config.season_hint}."
        )
        return 1

    cache = MemoryCache()
    service = DataService(config, cache, JsonSettingsStore(config.settings_path))
    if args.season is not None:
        service.update_settings({"default_season": args.season})

    settings = service.settings()
    leagues = settings.get("tracked_leagues") or []
    skipped: list[str] = []
    for league in leagues:
        league_id = int(league.get("id") or -1)
        league_name = league.get("name") or f"Ligue {league_id}"
        unavailable = [
            season
            for season in selected
            if not free_source_supports(league_id, season)
        ]
        if unavailable:
            skipped.append(
                f"{league_name} ({', '.join(str(season) for season in unavailable)})"
            )
    print(
        f"Betting Matrix - prechargement de {len(leagues)} ligue(s), "
        f"saison(s) {', '.join(str(season) for season in selected)}"
    )
    if skipped:
        print(
            "Ligues/saisons ignorees (sources gratuites indisponibles) : "
            + ", ".join(skipped)
        )
    print("Sources gratuites : CSV, OpenFootball, OpenLigaDB, TheSportsDB.\n")

    def progress(index: int, total: int, label: str) -> None:
        print(f"[{index}/{total}] {label}...", flush=True)

    result = service.warmup(progress=progress, seasons=selected)
    errors = result.get("errors") or []
    print("\nTermine.")
    for step in result.get("steps") or []:
        status = "OK" if step.get("ok") else "ECHEC"
        warning = f" ({step['warning']})" if step.get("warning") else ""
        error = f" - {step['error']}" if step.get("error") else ""
        print(f"  {status:5} {step['label']}{warning}{error}")
    stats = service.cache_stats()
    print(f"\nCache session : {stats['entries']} entree(s), {stats['bytes'] / 1024:.0f} Ko")
    if errors:
        print(
            f"\n{len(errors)} etape(s) en echec. "
            "Les reponses deja en cache restent utilisables."
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
