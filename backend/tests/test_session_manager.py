"""Tests for SessionManager budget reservation."""

import aiosqlite
from app.sessions.manager import SessionManager


async def _setup_db() -> aiosqlite.Connection:
    """Create an in-memory database with the required schema."""
    db = await aiosqlite.connect(":memory:")
    await db.execute(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            budget_used REAL NOT NULL DEFAULT 0.0,
            budget_limit REAL NOT NULL DEFAULT 1.0
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE objects (
            session_id TEXT NOT NULL,
            object_id TEXT NOT NULL,
            blueprint_json TEXT NOT NULL,
            x REAL NOT NULL DEFAULT 0.0,
            y REAL NOT NULL DEFAULT 0.0,
            durability REAL NOT NULL DEFAULT 0.0,
            PRIMARY KEY (session_id, object_id),
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
        """
    )
    await db.commit()
    return db


async def test_reserve_budget_success():
    db = await _setup_db()
    await db.execute(
        "INSERT INTO sessions (id, created_at, budget_limit)"
        " VALUES ('s1', '2024-01-01', 1.0)"
    )
    await db.commit()
    manager = SessionManager(db)

    success, remaining = await manager.reserve_budget("s1", 0.041)
    assert success is True
    assert remaining > 0
    await db.close()


async def test_reserve_budget_insufficient():
    db = await _setup_db()
    await db.execute(
        "INSERT INTO sessions (id, created_at, budget_limit, budget_used)"
        " VALUES ('s1', '2024-01-01', 0.05, 0.04)"
    )
    await db.commit()
    manager = SessionManager(db)

    success, _ = await manager.reserve_budget("s1", 0.041)
    assert success is False
    await db.close()


async def test_reserve_budget_nonexistent_session():
    db = await _setup_db()
    manager = SessionManager(db)

    success, remaining = await manager.reserve_budget("nonexistent", 0.041)
    assert success is False
    assert remaining == 0.0
    await db.close()


async def test_reserve_budget_concurrent():
    """Two concurrent reserves where budget allows only one."""
    db = await _setup_db()
    await db.execute(
        "INSERT INTO sessions (id, created_at, budget_limit)"
        " VALUES ('s1', '2024-01-01', 0.05)"
    )
    await db.commit()
    manager = SessionManager(db)

    import asyncio

    results = await asyncio.gather(
        manager.reserve_budget("s1", 0.041),
        manager.reserve_budget("s1", 0.041),
    )
    successes = [r[0] for r in results]
    assert successes.count(True) == 1
    assert successes.count(False) == 1
    await db.close()
