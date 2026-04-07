import json
import re
import time

import aiosqlite


_CACHE_DDL = """CREATE TABLE IF NOT EXISTS cache (
    cache_type TEXT NOT NULL, cache_key TEXT NOT NULL,
    value_json TEXT NOT NULL, model_version TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (cache_type, cache_key))"""


class CacheManager:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    @classmethod
    async def ensure_schema(cls, db: aiosqlite.Connection) -> None:
        await db.execute(_CACHE_DDL)
        await db.commit()

    @staticmethod
    def normalize_key(name: str) -> str:
        return re.sub(r"\s+", " ", name.strip().lower())

    @staticmethod
    def pair_key(name_a: str, name_b: str) -> str:
        a = CacheManager.normalize_key(name_a)
        b = CacheManager.normalize_key(name_b)
        return f"{min(a, b)}::{max(a, b)}"

    async def get(self, cache_type: str, key: str) -> dict | None:
        cursor = await self._db.execute(
            "SELECT value_json FROM cache WHERE cache_type = ? AND cache_key = ?",
            (cache_type, key),
        )
        row = await cursor.fetchone()
        return json.loads(row[0]) if row else None

    async def set(self, cache_type: str, key: str, value: dict) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO cache (cache_type, cache_key, value_json, model_version,"
            " created_at) VALUES (?, ?, ?, ?, ?)",
            (cache_type, key, json.dumps(value), "", time.time()),
        )
        await self._db.commit()

    async def exists(self, cache_type: str, key: str) -> bool:
        cursor = await self._db.execute(
            "SELECT 1 FROM cache WHERE cache_type = ? AND cache_key = ?",
            (cache_type, key),
        )
        return await cursor.fetchone() is not None

    async def get_by_prefix(self, cache_type: str, prefix: str) -> dict[str, dict]:
        """Return all entries whose key starts with prefix. For bulk scene loading."""
        cursor = await self._db.execute(
            "SELECT cache_key, value_json FROM cache WHERE cache_type = ? AND cache_key LIKE ?",
            (cache_type, f"{prefix}%"),
        )
        return {row[0]: json.loads(row[1]) async for row in cursor}

    async def get_all_for_names(self, cache_type: str, names: list[str]) -> dict[str, dict]:
        """Return all pairwise entries involving any of the given names."""
        keys = []
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                keys.append(self.pair_key(a, b))
        if not keys:
            return {}
        placeholders = ",".join("?" for _ in keys)
        cursor = await self._db.execute(
            f"SELECT cache_key, value_json FROM cache"  # noqa: S608
            f" WHERE cache_type = ? AND cache_key IN ({placeholders})",
            (cache_type, *keys),
        )
        return {row[0]: json.loads(row[1]) async for row in cursor}
