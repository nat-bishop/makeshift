"""Unified cache backed by SQLite (cache.db), separate from game.db.

Two cache types:
  - creation: object name -> physics/affordance/etc (persistent, global)
  - collision: sorted pair key -> force-only collision rule (persistent, global)

Creature behavior is scene-local and lives only in BehaviorCache (scene.py).
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
        self,
        cache_type: str,
        key: str,
        value: dict,
        model_version: str = "",
        *,
        commit: bool = True,
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

    async def put_creation(self, name: str, value: dict, model_version: str = "") -> None:
        await self.put("creation", normalize_name(name), value, model_version)

    # --- Collision cache (force-only pairwise rules) ---

    async def get_collision(self, name_a: str, name_b: str) -> dict | None:
        # Also check legacy "pairwise" type for backwards compat
        result = await self.get("collision", pair_key(name_a, name_b))
        if result is None:
            result = await self.get("pairwise", pair_key(name_a, name_b))
        return result

    async def put_collision(
        self,
        name_a: str,
        name_b: str,
        value: dict,
        model_version: str = "",
        *,
        commit: bool = True,
    ) -> None:
        await self.put("collision", pair_key(name_a, name_b), value, model_version, commit=commit)

    async def get_all_collisions_for_names(self, names: list[str]) -> dict[str, dict]:
        """Fetch all collision entries for all N*(N-1)/2 pairs from a list of names."""
        normalized = sorted({normalize_name(n) for n in names})
        keys = [f"{a}::{b}" for i, a in enumerate(normalized) for b in normalized[i + 1 :]]

        if not keys:
            return {}

        placeholders = ",".join("?" for _ in keys)
        cur = await self._db.execute(
            f"SELECT cache_key, value_json FROM cache "
            f"WHERE cache_type IN ('collision', 'pairwise') AND cache_key IN ({placeholders})",
            (*keys,),
        )
        results: dict[str, dict] = {}
        async for row in cur:
            results[row[0]] = json.loads(row[1])
        return results

    # --- Lifecycle ---

    async def close(self) -> None:
        await self._db.close()
