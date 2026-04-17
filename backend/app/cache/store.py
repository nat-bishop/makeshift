"""Unified cache backed by SQLite (cache.db), separate from game.db.

Cache types:
  - creation: object name -> physics/affordance/etc (persistent, global)
  - projectile: projectile name -> ProjectileBlueprint dict (persistent, global)

Object behavior is scene-local and lives only in BehaviorCache (scene.py).
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
    """Lexicographically sorted, '::'-joined, normalized. For symmetric relationships."""
    a, b = normalize_name(name_a), normalize_name(name_b)
    return f"{a}::{b}" if a <= b else f"{b}::{a}"


def directed_key(subject: str, target: str) -> str:
    """Directed '::'-joined, normalized. For asymmetric relationships (behaviors)."""
    return f"{normalize_name(subject)}::{normalize_name(target)}"


class CacheStore:
    """Async SQLite cache for creation entries."""

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

    # --- Projectile cache ---

    async def get_projectile(self, name: str) -> dict | None:
        return await self.get("projectile", normalize_name(name))

    async def exists_projectile(self, name: str) -> bool:
        return await self.exists("projectile", normalize_name(name))

    async def put_projectile(self, name: str, value: dict, model_version: str = "") -> None:
        await self.put("projectile", normalize_name(name), value, model_version)

    # --- Lifecycle ---

    async def close(self) -> None:
        await self._db.close()
