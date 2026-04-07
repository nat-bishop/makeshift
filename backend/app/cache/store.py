"""Unified cache backed by SQLite (cache.db), separate from game.db.

Two cache types:
  - creation: object name -> physics/affordance/etc (persistent, global)
  - pairwise: sorted pair key -> 9-field interaction result (persistent, global)

Creature behavior is scene-local and lives only in SceneCache (scene.py).
"""

from __future__ import annotations

import json
import time

import aiosqlite
import structlog

logger = structlog.get_logger()


def normalize_name(name: str) -> str:
    """Lowercase, strip, collapse internal whitespace."""
    return " ".join(name.strip().lower().split())


def pair_key(name_a: str, name_b: str) -> str:
    """Lexicographically sorted, '::'-joined, normalized."""
    a, b = normalize_name(name_a), normalize_name(name_b)
    return f"{a}::{b}" if a <= b else f"{b}::{a}"


class CacheStore:
    """Async SQLite cache for creation and pairwise entries."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    @classmethod
    async def open(cls, path: str = "data/cache.db") -> CacheStore:
        db = await aiosqlite.connect(path)
        store = cls(db)
        await store._init_schema()
        return store

    async def _init_schema(self) -> None:
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                cache_type TEXT NOT NULL,
                cache_key TEXT NOT NULL,
                value_json TEXT NOT NULL,
                model_version TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL,
                PRIMARY KEY (cache_type, cache_key)
            )
        """)
        await self._db.commit()

    # --- Generic ---

    async def get(self, cache_type: str, key: str) -> dict | None:
        cur = await self._db.execute(
            "SELECT value_json FROM cache WHERE cache_type=? AND cache_key=?",
            (cache_type, key),
        )
        row = await cur.fetchone()
        return json.loads(row[0]) if row else None

    async def put(
        self, cache_type: str, key: str, value: dict, model_version: str = ""
    ) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO cache "
            "(cache_type, cache_key, value_json, model_version, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (cache_type, key, json.dumps(value), model_version, time.time()),
        )
        await self._db.commit()

    # --- Creation cache ---

    async def get_creation(self, name: str) -> dict | None:
        return await self.get("creation", normalize_name(name))

    async def put_creation(
        self, name: str, value: dict, model_version: str = ""
    ) -> None:
        await self.put("creation", normalize_name(name), value, model_version)

    # --- Pairwise cache ---

    async def get_pairwise(self, name_a: str, name_b: str) -> dict | None:
        return await self.get("pairwise", pair_key(name_a, name_b))

    async def put_pairwise(
        self, name_a: str, name_b: str, value: dict, model_version: str = ""
    ) -> None:
        await self.put("pairwise", pair_key(name_a, name_b), value, model_version)

    async def invalidate_pairwise(self, name: str) -> int:
        """Delete all pairwise entries involving this object name.
        Returns count of deleted rows."""
        n = normalize_name(name)
        cur = await self._db.execute(
            "DELETE FROM cache WHERE cache_type='pairwise' "
            "AND (cache_key LIKE ? OR cache_key LIKE ?)",
            (f"{n}::%", f"%::{n}"),
        )
        await self._db.commit()
        return cur.rowcount or 0

    # --- Lifecycle ---

    async def close(self) -> None:
        await self._db.close()
