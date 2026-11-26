"""Analyse IA via Llama App (llama.cpp local, optionnel)."""

from __future__ import annotations

import json
import os
from typing import Any

import requests


DEFAULT_LLAMA_APP_URL = "http://localhost:9931"
DEFAULT_PROMPT = (
    "Analyse ce match en te basant uniquement sur les donnees ci-dessous. "
    "Prends en compte la forme recente des equipes (champ 'teams_form.form', ex: V/N/D) et leur classement "
    "(rangs, context de classement) quand ils sont fournis. "
    "Decris les probabilites du modele, compare les cotes estimees, "
    "et rappelle qu'aucun resultat n'est garanti. Ne donne pas de conseil de pari."
)
LIST_TIMEOUT = 5.0
ASK_TIMEOUT = 300.0


class AiError(Exception):
    pass


def normalize_url(url: str | None) -> str:
    """Accepte ``http://host:9931`` ou ``http://host:9931/v1``."""
    value = (
        (url or "").strip()
        or os.environ.get("LLAMA_APP_URL", "").strip()
        or DEFAULT_LLAMA_APP_URL
    )
    value = value.rstrip("/")
    if value.endswith("/v1"):
        value = value[:-3].rstrip("/")
    return value


def _headers() -> dict[str, str]:
    """Llama App n'exige pas de cle, mais permet de proteger le serveur."""
    api_key = os.environ.get("LLAMA_API_KEY", "").strip()
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def _check_api_error(payload: Any) -> None:
    if not isinstance(payload, dict):
        return
    error = payload.get("error")
    if error:
        message = error.get("message") if isinstance(error, dict) else error
        raise AiError(f"Llama App : {message or error}")


def _raise_connection_error(exc: requests.ConnectionError, root: str) -> None:
    raise AiError(
        f"Llama App n'est pas joignable sur {root}. "
        "Lance l'application et charge un modele."
    ) from exc


def build_context(analysis: dict) -> str:
    payload: dict[str, Any] = analysis
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def list_models(base_url: str | None = None, timeout: float = LIST_TIMEOUT) -> list[str]:
    root = normalize_url(base_url)
    try:
        response = requests.get(f"{root}/v1/models", headers=_headers(), timeout=timeout)
        response.raise_for_status()
    except requests.ConnectionError as exc:
        _raise_connection_error(exc, root)
    except requests.Timeout as exc:
        raise AiError(f"Llama App ({root}) met trop de temps a repondre.") from exc
    except requests.RequestException as exc:
        raise AiError(f"Impossible de contacter Llama App : {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise AiError("Reponse Llama App invalide pour la liste des modeles.") from exc
    _check_api_error(payload)

    if isinstance(payload, dict):
        items = payload.get("data") or payload.get("models") or []
    elif isinstance(payload, list):
        items = payload
    else:
        items = []

    names: list[str] = []
    for item in items:
        if isinstance(item, str):
            name: Any = item
        elif isinstance(item, dict):
            name = item.get("id") or item.get("name") or item.get("model")
        else:
            continue
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return sorted(set(names))


def ask_llama_app(
    prompt: str,
    model: str,
    base_url: str | None = None,
    timeout: float = ASK_TIMEOUT,
) -> str:
    root = normalize_url(base_url)
    model_name = (model or "").strip()
    if not model_name:
        raise AiError("Choisissez un modele Llama App avant l'analyse.")

    body = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    try:
        response = requests.post(
            f"{root}/v1/chat/completions",
            json=body,
            headers=_headers(),
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.ConnectionError as exc:
        _raise_connection_error(exc, root)
    except requests.Timeout as exc:
        raise AiError("Llama App met trop de temps a repondre. Reessayez.") from exc
    except requests.RequestException as exc:
        raise AiError(f"Impossible de contacter Llama App : {exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise AiError("Reponse Llama App invalide.") from exc
    _check_api_error(payload)

    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not choices:
        raise AiError("Llama App n'a renvoye aucune reponse.")
    message = choices[0].get("message") or {}
    content = message.get("content") or message.get("reasoning_content") or ""
    if not str(content).strip():
        raise AiError("Llama App a renvoye une reponse vide.")
    return str(content).strip()
