"""Contexte d'analyse et client de l'instance Ollama locale.

Aucun appel n'est effectue tant que l'utilisateur n'a pas clique sur le bouton
« Analyser » de la fenetre IA. Ollama doit etre lance separement (`ollama serve`)
avec au moins un modele installe (`ollama pull <modele>`).
"""

from __future__ import annotations

import json
from typing import Any

import requests

from .config import DEFAULT_OLLAMA_URL
from .errors import SourceError

DEFAULT_PROMPT = (
    "Analyse ce match en te basant uniquement sur les donnees ci-dessous. "
    "Decris les probabilites du modele, compare les cotes de la strategie "
    "selectionnee avec les cotes de marche reelles, et utilise les xG, les "
    "statistiques de match et le profil de l'arbitre lorsqu'ils sont presents. "
    "Si le classement est present, utilise-le pour situer les equipes dans leur "
    "ligue. Souligne les limites des donnees et rappelle qu'aucun resultat "
    "n'est garanti. Ne donne pas de conseil de pari."
)
LIST_TIMEOUT = 5.0
ASK_TIMEOUT = 300.0


def normalize_url(url: str | None) -> str:
    """Nettoie l'URL de base d'Ollama (sans slash final)."""
    value = (url or "").strip().rstrip("/")
    return value or DEFAULT_OLLAMA_URL


def build_context(analysis: dict) -> str:
    """Convertit l'analyse courante en contexte JSON lisible par le modele."""
    fixture = analysis.get("fixture") or {}
    model = analysis.get("model") or {}
    league = fixture.get("league") or {}
    home = fixture.get("home") or {}
    away = fixture.get("away") or {}
    selected = analysis.get("selected_strategy")

    payload: dict[str, Any] = {
        "match": {
            "id": fixture.get("id"),
            "competition": league.get("name"),
            "saison": league.get("season"),
            "journee": league.get("round"),
            "date": fixture.get("date"),
            "domicile": home.get("name"),
            "exterieur": away.get("name"),
            "statut": (fixture.get("status") or {}).get("label"),
            "source": fixture.get("source"),
        },
        "modele": {
            "probabilites": model.get("probabilities") or {},
            "scores_probables": model.get("scores") or [],
            "xG_domicile": model.get("lambda_home"),
            "xG_exterieur": model.get("lambda_away"),
            "total_attendu": model.get("expected_total"),
            "echantillon_matchs": model.get("sample_matches"),
            "fiabilite": model.get("reliability"),
            "equipes": {
                "domicile": model.get("home") or {},
                "exterieur": model.get("away") or {},
            },
            "meta": model.get("_meta") or {},
        },
        "donnees_match": {
            "xG": (analysis.get("context") or {}).get("xg") or {},
            "statistiques": (analysis.get("context") or {}).get("stats") or {},
            "marche": (analysis.get("context") or {}).get("market") or {},
            "arbitre": (analysis.get("context") or {}).get("referee") or {},
        },
        "classement": analysis.get("standings") or {},
        "strategie": (
            {
                "id": (analysis.get("strategie") or {}).get("id") or selected,
                "nom": (analysis.get("strategie") or {}).get("name"),
                "description": (analysis.get("strategie") or {}).get("description"),
                "cotes": (analysis.get("strategie") or {}).get("rows") or [],
            }
            if (analysis.get("strategie") or selected)
            else {}
        ),
        "note": (
            "Les cotes de la strategie selectionnee sont estimees par le modele, "
            "ce ne sont pas des cotes de bookmaker. Les cotes de marche presentes "
            "dans 'marche' sont "
            "elles issues du CSV et peuvent servir de reference. Les xG et statistiques "
            "sont absents des saisons anterieures a 2026-27. Le classement, lorsqu'il "
            "est present, est calcule a partir des resultats de la meme saison que le "
            "modele : il ne constitue pas une source d'information independante. "
            "Aucun resultat n'est garanti."
        ),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def build_prompt(user_prompt: str, context: str) -> str:
    """Assemble le prompt utiliseur et le contexte d'analyse."""
    instruction = (user_prompt or "").strip() or DEFAULT_PROMPT
    return (
        f"{instruction}\n\n"
        "--- DONNEES DE L'ANALYSE ---\n"
        f"{context}\n"
        "--- FIN DES DONNEES ---"
    )


def list_models(base_url: str | None = None, timeout: float = LIST_TIMEOUT) -> list[str]:
    """Recupere les modeles installes dans l'instance Ollama locale."""
    root = normalize_url(base_url)
    try:
        response = requests.get(f"{root}/api/tags", timeout=timeout)
        response.raise_for_status()
    except requests.ConnectionError as exc:
        raise SourceError(
            f"Ollama n'est pas joignable sur {root}. Lancez Ollama (ollama serve) puis reessayez.",
            "ollama",
        ) from exc
    except requests.Timeout as exc:
        raise SourceError(f"Ollama ({root}) met trop de temps a repondre.", "ollama") from exc
    except requests.HTTPError as exc:
        raise SourceError(f"Ollama a renvoye une erreur : {exc}", "ollama") from exc
    except requests.RequestException as exc:
        raise SourceError(f"Impossible de contacter Ollama : {exc}", "ollama") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise SourceError("Reponse Ollama invalide pour la liste des modeles.", "ollama") from exc

    names: list[str] = []
    for item in payload.get("models") or []:
        name = item.get("name") or item.get("model")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return sorted(set(names))


def ask_ollama(
    prompt: str,
    model: str,
    base_url: str | None = None,
    timeout: float = ASK_TIMEOUT,
) -> str:
    """Envoie le prompt a Ollama et renvoie la reponse du modele choisi."""
    root = normalize_url(base_url)
    model_name = (model or "").strip()
    if not model_name:
        raise SourceError("Choisissez un modele Ollama avant de lancer l'analyse.", "ollama")

    body = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    try:
        response = requests.post(f"{root}/api/chat", json=body, timeout=timeout)
        response.raise_for_status()
    except requests.ConnectionError as exc:
        raise SourceError(
            f"Ollama n'est pas joignable sur {root}. Lancez Ollama (ollama serve) puis reessayez.",
            "ollama",
        ) from exc
    except requests.Timeout as exc:
        raise SourceError("Ollama met trop de temps a repondre. Reessayez.", "ollama") from exc
    except requests.HTTPError as exc:
        detail = ""
        reply = getattr(exc, "response", None)
        if reply is not None and getattr(reply, "text", None):
            detail = f" : {reply.text[:200]}"
        raise SourceError(f"Ollama a renvoye une erreur{detail}", "ollama") from exc
    except requests.RequestException as exc:
        raise SourceError(f"Impossible de contacter Ollama : {exc}", "ollama") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise SourceError("Reponse Ollama invalide.", "ollama") from exc

    content = (payload.get("message") or {}).get("content") or payload.get("response") or ""
    if not str(content).strip():
        raise SourceError("Ollama a renvoye une reponse vide.", "ollama")
    return str(content).strip()
