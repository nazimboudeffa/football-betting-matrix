"""Stockage local leger : cache en memoire et reglages JSON, sans base de donnees."""

from __future__ import annotations

import json
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Any


class MemoryCache:
    """Cache partage entre les sources, conserve uniquement pendant la session."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: dict[str, dict[str, Any]] = {}
        self.hits = 0
        self.stale_hits = 0
        self.misses = 0

    def cache_get(self, key: str, allow_stale: bool = True) -> dict | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self.misses += 1
                return None
            now = time.time()
            fresh = entry["expires_at"] > now
            if not fresh and not allow_stale:
                self.misses += 1
                return None
            if fresh:
                self.hits += 1
            else:
                self.stale_hits += 1
            return {
                "key": key,
                "endpoint": entry["endpoint"],
                "params": deepcopy(entry["params"]),
                "data": deepcopy(entry["data"]),
                "fetched_at": entry["fetched_at"],
                "expires_at": entry["expires_at"],
                "fresh": fresh,
                "size": entry["size"],
                "meta": deepcopy(entry["meta"]),
            }

    def cache_set(
        self,
        key: str,
        endpoint: str,
        params: dict,
        data: Any,
        ttl_seconds: int,
        meta: dict | None = None,
    ) -> None:
        try:
            size = len(
                json.dumps(data, ensure_ascii=False, default=str, separators=(",", ":")).encode(
                    "utf-8"
                )
            )
        except (TypeError, ValueError):
            size = len(str(data).encode("utf-8"))
        now = time.time()
        with self._lock:
            self._entries[key] = {
                "endpoint": endpoint,
                "params": deepcopy(params),
                "data": deepcopy(data),
                "fetched_at": now,
                "expires_at": now + ttl_seconds,
                "size": size,
                "meta": deepcopy(meta or {}),
            }

    def cache_delete(self, key: str) -> bool:
        with self._lock:
            return self._entries.pop(key, None) is not None

    def cache_clear(self, prefix: str | None = None) -> int:
        with self._lock:
            if prefix:
                keys = [key for key in self._entries if key.startswith(prefix)]
            else:
                keys = list(self._entries)
            for key in keys:
                del self._entries[key]
            return len(keys)

    def cache_stats(self) -> dict:
        with self._lock:
            entries = list(self._entries.values())
            hits = self.hits
            stale_hits = self.stale_hits
            misses = self.misses
        now = time.time()
        fresh = sum(1 for entry in entries if entry["expires_at"] > now)
        total_gets = hits + stale_hits + misses
        return {
            "entries": len(entries),
            "bytes": sum(entry["size"] for entry in entries),
            "oldest": min((entry["fetched_at"] for entry in entries), default=None),
            "fresh": fresh,
            "stale": len(entries) - fresh,
            "hits": hits,
            "stale_hits": stale_hits,
            "misses": misses,
            "hit_rate": (hits + stale_hits) / total_gets if total_gets else 0.0,
        }

    def cache_list(self, limit: int = 300) -> list[dict]:
        with self._lock:
            entries = sorted(
                self._entries.items(), key=lambda item: item[1]["fetched_at"], reverse=True
            )[:limit]
            result = []
            now = time.time()
            for key, entry in entries:
                result.append(
                    {
                        "key": key,
                        "endpoint": entry["endpoint"],
                        "params": deepcopy(entry["params"]),
                        "fetched_at": entry["fetched_at"],
                        "expires_at": entry["expires_at"],
                        "size": entry["size"],
                        "label": entry["meta"].get("label") or entry["endpoint"],
                        "fresh": entry["expires_at"] > now,
                    }
                )
            return result


class JsonSettingsStore:
    """Reglages persistes dans un simple fichier JSON."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(payload, dict):
            self._data = payload

    def get_settings(self, defaults: dict) -> dict:
        settings = deepcopy(defaults)
        with self._lock:
            settings.update(deepcopy(self._data))
        leagues = settings.get("tracked_leagues")
        if not isinstance(leagues, list) or not leagues:
            settings["tracked_leagues"] = deepcopy(defaults["tracked_leagues"])
        return settings

    def save_settings(self, settings: dict) -> None:
        with self._lock:
            self._data = deepcopy(settings)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(self.path.suffix + ".tmp")
            temp.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temp.replace(self.path)
