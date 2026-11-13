"""Configuration de Betting Matrix (chargement du .env, chemins, valeurs par defaut)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT_DIR / ".env"


def _load_dotenv(path: Path) -> None:
    """Charge un fichier .env simple sans dependance externe.

    Les variables deja presentes dans l'environnement restent prioritaires.
    Les anciennes variables API eventuelles sont ignorees par l'application.
    """
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(ENV_FILE)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, "true" if default else "false").strip().lower() in {"1", "true", "yes", "on"}


def _env_seasons(name: str, default: str) -> tuple[int, ...]:
    seasons: list[int] = []
    for chunk in os.getenv(name, default).split(","):
        try:
            seasons.append(int(chunk.strip()))
        except ValueError:
            continue
    return tuple(seasons) or (2026, 2025)


FREE_SEASONS: tuple[int, ...] = _env_seasons("FREE_SEASONS", "2026,2025")


def _default_season(seasons: tuple[int, ...]) -> int:
    fallback = seasons[0] if seasons else 2026
    value = _env_int("APP_DEFAULT_SEASON", fallback)
    return value if value in seasons else fallback


DEFAULT_SEASON: int = _default_season(FREE_SEASONS)

DEFAULT_LEAGUES: list[dict] = [
    {
        "id": 140,
        "name": "La Liga",
        "country": "Spain",
        "logo": "",
        "flag": "",
        "default": True,
    },
    {
        "id": 78,
        "name": "Bundesliga",
        "country": "Germany",
        "logo": "",
        "flag": "",
        "default": True,
    },
    {
        "id": 135,
        "name": "Serie A",
        "country": "Italy",
        "logo": "",
        "flag": "",
        "default": True,
    },
    {
        "id": 61,
        "name": "Ligue 1",
        "country": "France",
        "logo": "",
        "flag": "",
        "default": True,
    },
    {
        "id": 2,
        "name": "UEFA Champions League",
        "country": "World",
        "logo": "",
        "flag": "",
        "default": True,
    },
]

DEFAULT_SETTINGS: dict = {
    "default_season": DEFAULT_SEASON,
    "tracked_leagues": DEFAULT_LEAGUES,
}


@dataclass(frozen=True)
class Config:
    root_dir: Path
    data_dir: Path
    db_path: Path
    timezone: str = "Europe/Paris"
    seasons: tuple[int, ...] = FREE_SEASONS
    default_season: int = DEFAULT_SEASON
    auto_warmup: bool = False
    thesportsdb_key: str = "123"
    tsdb_min_interval_ms: int = 2000

    @property
    def season_hint(self) -> str:
        return ", ".join(str(s) for s in self.seasons)

    @property
    def free_seasons(self) -> tuple[int, ...]:
        return self.seasons


def load_config() -> Config:
    data_dir = ROOT_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return Config(
        root_dir=ROOT_DIR,
        data_dir=data_dir,
        db_path=data_dir / "betting_matrix.db",
        timezone=os.getenv("APP_TIMEZONE", "Europe/Paris").strip() or "Europe/Paris",
        seasons=FREE_SEASONS,
        default_season=DEFAULT_SEASON,
        auto_warmup=_env_bool("AUTO_WARMUP", False),
        thesportsdb_key=os.getenv("THESPORTSDB_KEY", "123").strip() or "123",
        tsdb_min_interval_ms=max(0, _env_int("THESPORTSDB_MIN_INTERVAL_MS", 2000)),
    )


APP_NAME = "Betting Matrix"
APP_VERSION = "1.0.0"

DISCLAIMER = (
    "Betting Matrix est un outil d'analyse statistique et de suivi de pronostics. "
    "Les probabilites affichees ne constituent pas des conseils de pari ni une garantie "
    "de resultat. L'application utilise uniquement des sources gratuites sans cle "
    "personnelle (football-data.co.uk, OpenFootball, OpenLigaDB, TheSportsDB) ; "
    "certaines donnees peuvent etre partielles ou retardees. "
    "Utilisez ces analyses de facon responsable."
)
