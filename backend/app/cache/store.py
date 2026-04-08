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

    async def exists(self, cache_type: str, key: str) -> bool:
        """Lightweight existence check without deserializing value."""
        cur = await self._db.execute(
            "SELECT 1 FROM cache WHERE cache_type=? AND cache_key=? LIMIT 1",
            (cache_type, key),
        )
        return (await cur.fetchone()) is not None

    async def put(
        self, cache_type: str, key: str, value: dict, model_version: str = "",
        *, commit: bool = True,
    ) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO cache "
            "(cache_type, cache_key, value_json, model_version, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (cache_type, key, json.dumps(value), model_version, time.time()),
        )
        if commit:
            await self._db.commit()

    async def flush(self) -> None:
        """Commit pending writes. Call after batched put(..., commit=False) calls."""
        await self._db.commit()

    # --- Creation cache ---

    async def get_creation(self, name: str) -> dict | None:
        return await self.get("creation", normalize_name(name))

    async def exists_creation(self, name: str) -> bool:
        return await self.exists("creation", normalize_name(name))

    async def put_creation(
        self, name: str, value: dict, model_version: str = ""
    ) -> None:
        await self.put("creation", normalize_name(name), value, model_version)

    # --- Pairwise cache ---

    async def get_pairwise(self, name_a: str, name_b: str) -> dict | None:
        return await self.get("pairwise", pair_key(name_a, name_b))

    async def exists_pairwise(self, name_a: str, name_b: str) -> bool:
        return await self.exists("pairwise", pair_key(name_a, name_b))

    async def put_pairwise(
        self, name_a: str, name_b: str, value: dict, model_version: str = "",
        *, commit: bool = True,
    ) -> None:
        await self.put("pairwise", pair_key(name_a, name_b), value, model_version, commit=commit)

    async def get_all_for_names(
        self, cache_type: str, names: list[str]
    ) -> dict[str, dict]:
        """Fetch all cache entries for all N*(N-1)/2 pairs from a list of names."""
        normalized = sorted({normalize_name(n) for n in names})
        keys = []
        for i, a in enumerate(normalized):
            for b in normalized[i + 1 :]:
                keys.append(f"{a}::{b}")

        if not keys:
            return {}

        placeholders = ",".join("?" for _ in keys)
        cur = await self._db.execute(
            f"SELECT cache_key, value_json FROM cache "
            f"WHERE cache_type=? AND cache_key IN ({placeholders})",
            (cache_type, *keys),
        )
        results = {}
        async for row in cur:
            results[row[0]] = json.loads(row[1])
        return results

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
