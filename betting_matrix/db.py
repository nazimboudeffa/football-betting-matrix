"""Base SQLite locale : cache persistant, reglages et pronostics."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key        TEXT PRIMARY KEY,
    endpoint   TEXT NOT NULL,
    params     TEXT NOT NULL,
    payload    TEXT NOT NULL,
    fetched_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    size       INTEGER NOT NULL,
    meta       TEXT
);
CREATE INDEX IF NOT EXISTS idx_cache_endpoint ON cache(endpoint);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS predictions (
    id          TEXT PRIMARY KEY,
    fixture_id  INTEGER,
    league_id   INTEGER,
    league_name TEXT,
    home        TEXT NOT NULL,
    away        TEXT NOT NULL,
    kickoff     TEXT,
    market      TEXT NOT NULL,
    selection   TEXT NOT NULL,
    odds        REAL,
    model_prob  REAL,
    edge        REAL,
    note        TEXT,
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TEXT NOT NULL,
    settled_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_predictions_status ON predictions(status);
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    """Acces SQLite thread-safe (une connexion partagee + verrou)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.executescript(SCHEMA)
            self._drop_legacy_api_tables()
            self._migrate_legacy_bets()
            self._conn.commit()
        self.cache_hits = 0
        self.cache_stale_hits = 0
        self.cache_misses = 0

    def _drop_legacy_api_tables(self) -> None:
        """Supprime les tables de quota API des anciennes installations."""
        self._conn.execute("DROP TABLE IF EXISTS usage")
        self._conn.execute("DROP TABLE IF EXISTS api_log")

    def _migrate_legacy_bets(self) -> None:
        """Reprend les anciens paris (ancienne version) en pronostics."""
        legacy = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'bets'"
        ).fetchone()
        if not legacy:
            return
        existing = self._conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
        if existing:
            return
        self._conn.execute(
            """
            INSERT OR IGNORE INTO predictions
                (id, fixture_id, league_id, league_name, home, away, kickoff, market,
                 selection, odds, model_prob, edge, note, status, created_at, settled_at)
            SELECT id, fixture_id, league_id, COALESCE(league_name, ''), home, away, kickoff,
                   market, selection, odds, model_prob, edge, note, status, created_at, settled_at
            FROM bets
            """
        )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------ cache

    def cache_get(self, key: str, allow_stale: bool = True) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM cache WHERE key = ?", (key,)).fetchone()
            if row is None:
                self.cache_misses += 1
                return None
            now = time.time()
            fresh = row["expires_at"] > now
            if not fresh and not allow_stale:
                self.cache_misses += 1
                return None
            if fresh:
                self.cache_hits += 1
            else:
                self.cache_stale_hits += 1
            try:
                payload = json.loads(row["payload"])
            except json.JSONDecodeError:
                payload = None
            return {
                "key": row["key"],
                "endpoint": row["endpoint"],
                "params": json.loads(row["params"]) if row["params"] else {},
                "data": payload,
                "fetched_at": row["fetched_at"],
                "expires_at": row["expires_at"],
                "fresh": fresh,
                "size": row["size"],
                "meta": json.loads(row["meta"]) if row["meta"] else {},
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
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        now = time.time()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO cache (key, endpoint, params, payload, fetched_at, expires_at, size, meta)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    endpoint = excluded.endpoint,
                    params = excluded.params,
                    payload = excluded.payload,
                    fetched_at = excluded.fetched_at,
                    expires_at = excluded.expires_at,
                    size = excluded.size,
                    meta = excluded.meta
                """,
                (
                    key,
                    endpoint,
                    json.dumps(params, ensure_ascii=False, sort_keys=True),
                    payload,
                    now,
                    now + ttl_seconds,
                    len(payload.encode("utf-8")),
                    json.dumps(meta or {}, ensure_ascii=False),
                ),
            )
            self._conn.commit()

    def cache_delete(self, key: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            self._conn.commit()
            return cur.rowcount > 0

    def cache_clear(self, prefix: str | None = None) -> int:
        with self._lock:
            if prefix:
                cur = self._conn.execute("DELETE FROM cache WHERE key LIKE ?", (prefix + "%",))
            else:
                cur = self._conn.execute("DELETE FROM cache")
            self._conn.commit()
            return cur.rowcount

    def cache_stats(self) -> dict:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(size), 0) AS bytes, "
                "COALESCE(MIN(fetched_at), 0) AS oldest FROM cache"
            ).fetchone()
            now = time.time()
            fresh = self._conn.execute(
                "SELECT COUNT(*) FROM cache WHERE expires_at > ?", (now,)
            ).fetchone()[0]
            total_gets = self.cache_hits + self.cache_stale_hits + self.cache_misses
            return {
                "entries": row["n"],
                "bytes": row["bytes"],
                "oldest": row["oldest"] or None,
                "fresh": fresh,
                "stale": row["n"] - fresh,
                "hits": self.cache_hits,
                "stale_hits": self.cache_stale_hits,
                "misses": self.cache_misses,
                "hit_rate": (
                    (self.cache_hits + self.cache_stale_hits) / total_gets if total_gets else 0.0
                ),
            }

    def cache_list(self, limit: int = 300) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT key, endpoint, params, fetched_at, expires_at, size, meta "
                "FROM cache ORDER BY fetched_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        now = time.time()
        result = []
        for row in rows:
            meta = json.loads(row["meta"]) if row["meta"] else {}
            result.append(
                {
                    "key": row["key"],
                    "endpoint": row["endpoint"],
                    "params": json.loads(row["params"]) if row["params"] else {},
                    "fetched_at": row["fetched_at"],
                    "expires_at": row["expires_at"],
                    "size": row["size"],
                    "label": meta.get("label") or row["endpoint"],
                    "fresh": row["expires_at"] > now,
                }
            )
        return result

    # ---------------------------------------------------------------- settings

    def get_settings(self, defaults: dict) -> dict:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM settings WHERE key = 'app'"
            ).fetchone()
        settings = json.loads(json.dumps(defaults))
        if row:
            try:
                stored = json.loads(row["value"])
            except json.JSONDecodeError:
                stored = {}
            if isinstance(stored, dict):
                settings.update(stored)
        leagues = settings.get("tracked_leagues")
        if not isinstance(leagues, list) or not leagues:
            settings["tracked_leagues"] = json.loads(json.dumps(defaults["tracked_leagues"]))
        return settings

    def save_settings(self, settings: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO settings (key, value) VALUES ('app', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (json.dumps(settings, ensure_ascii=False, indent=2),),
            )
            self._conn.commit()

    # -------------------------------------------------------------- pronostics

    def add_prediction(self, prediction: dict) -> dict:
        odds = prediction.get("odds")
        try:
            odds = max(1.01, float(odds)) if odds not in (None, "") else None
        except (TypeError, ValueError):
            odds = None
        record = {
            "id": prediction.get("id") or str(uuid.uuid4()),
            "fixture_id": prediction.get("fixture_id"),
            "league_id": prediction.get("league_id"),
            "league_name": prediction.get("league_name") or "",
            "home": prediction.get("home") or "",
            "away": prediction.get("away") or "",
            "kickoff": prediction.get("kickoff"),
            "market": prediction.get("market") or "1X2",
            "selection": prediction.get("selection") or "",
            "odds": odds,
            "model_prob": prediction.get("model_prob"),
            "edge": prediction.get("edge"),
            "note": (prediction.get("note") or "")[:500],
            "status": prediction.get("status")
            if prediction.get("status") in {"pending", "won", "lost", "void"}
            else "pending",
            "created_at": prediction.get("created_at") or utc_now_iso(),
            "settled_at": prediction.get("settled_at"),
        }
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO predictions (id, fixture_id, league_id, league_name, home, away,
                                         kickoff, market, selection, odds, model_prob, edge,
                                         note, status, created_at, settled_at)
                VALUES (:id, :fixture_id, :league_id, :league_name, :home, :away, :kickoff,
                        :market, :selection, :odds, :model_prob, :edge, :note, :status,
                        :created_at, :settled_at)
                """,
                record,
            )
            self._conn.commit()
        return record

    def list_predictions(self, status: str | None = None) -> list[dict]:
        query = "SELECT * FROM predictions"
        params: Iterable[Any] = ()
        if status and status != "all":
            query += " WHERE status = ?"
            params = (status,)
        query += (
            " ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, "
            "COALESCE(kickoff, created_at) DESC"
        )
        with self._lock:
            rows = self._conn.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def get_prediction(self, prediction_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM predictions WHERE id = ?", (prediction_id,)
            ).fetchone()
        return dict(row) if row else None

    def update_prediction(self, prediction_id: str, patch: dict) -> dict | None:
        current = self.get_prediction(prediction_id)
        if not current:
            return None
        allowed = {
            "status",
            "odds",
            "note",
            "selection",
            "market",
            "kickoff",
            "home",
            "away",
            "league_name",
            "model_prob",
            "edge",
        }
        updates = {k: v for k, v in patch.items() if k in allowed}
        if "status" in updates:
            if updates["status"] not in {"pending", "won", "lost", "void"}:
                updates.pop("status")
            else:
                updates["settled_at"] = None if updates["status"] == "pending" else utc_now_iso()
        if "odds" in updates:
            try:
                updates["odds"] = (
                    max(1.01, float(updates["odds"]))
                    if updates["odds"] not in (None, "")
                    else None
                )
            except (TypeError, ValueError):
                updates.pop("odds")
        if "model_prob" in updates and updates["model_prob"] is not None:
            try:
                updates["model_prob"] = float(updates["model_prob"])
            except (TypeError, ValueError):
                updates.pop("model_prob")
        if "edge" in updates and updates["edge"] is not None:
            try:
                updates["edge"] = float(updates["edge"])
            except (TypeError, ValueError):
                updates.pop("edge")
        if "note" in updates:
            updates["note"] = str(updates["note"] or "")[:500]
        if "home" in updates:
            updates["home"] = str(updates["home"]).strip()
        if "away" in updates:
            updates["away"] = str(updates["away"]).strip()
        if "league_name" in updates:
            updates["league_name"] = str(updates["league_name"]).strip()[:120]
        if not updates:
            return current
        assignments = ", ".join(f"{key} = ?" for key in updates)
        values = list(updates.values()) + [prediction_id]
        with self._lock:
            self._conn.execute(f"UPDATE predictions SET {assignments} WHERE id = ?", values)
            self._conn.commit()
        return self.get_prediction(prediction_id)

    def delete_prediction(self, prediction_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM predictions WHERE id = ?", (prediction_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def prediction_stats(self) -> dict:
        predictions = self.list_predictions()
        settled = [p for p in predictions if p["status"] != "pending"]
        pending = [p for p in predictions if p["status"] == "pending"]
        won = [p for p in settled if p["status"] == "won"]
        lost = [p for p in settled if p["status"] == "lost"]
        voided = [p for p in settled if p["status"] == "void"]
        decided = len(won) + len(lost)
        edges = [float(p["edge"]) for p in predictions if p.get("edge") is not None]
        odds = [float(p["odds"]) for p in predictions if p.get("odds") is not None]
        return {
            "total": len(predictions),
            "settled": len(settled),
            "pending": len(pending),
            "won": len(won),
            "lost": len(lost),
            "void": len(voided),
            "win_rate": (len(won) / decided) if decided else 0.0,
            "average_edge": round(sum(edges) / len(edges), 4) if edges else 0.0,
            "average_odds": round(sum(odds) / len(odds), 2) if odds else 0.0,
            "value_count": sum(1 for p in predictions if (p.get("edge") or 0) > 0),
        }
