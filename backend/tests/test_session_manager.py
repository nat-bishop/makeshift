"""Tests for SessionManager."""

import uuid
from collections.abc import AsyncIterator

import aiosqlite
import pytest
from app.models.blueprint import GameObjectBlueprint, PhysicsProperties
from app.models.session import Session, WorldObject
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
            states_json TEXT NOT NULL DEFAULT '[]',
            PRIMARY KEY (session_id, object_id),
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
        """
    )
    await db.commit()
    return db


def _make_blueprint(name: str = "test object") -> GameObjectBlueprint:
    return GameObjectBlueprint(
        id=str(uuid.uuid4()),
        name=name,
        description="test",
        visual_description="a gray stone cube",
        physics=PhysicsProperties(mass_kg=5.0, height_cm=30, surface=1, bounce=10, gravity=50),
        durability=2,
    )


@pytest.fixture
async def manager() -> AsyncIterator[SessionManager]:
    db = await _setup_db()
    yield SessionManager(db)
    await db.close()


# --- create_session ---


async def test_create_session(manager: SessionManager) -> None:
    session = await manager.create_session()

    assert isinstance(session, Session)
    uuid.UUID(session.id)  # validates it's a valid UUID
    assert session.budget_remaining == session.budget_limit
    assert session.budget_used == 0.0
    assert session.objects == []


# --- session_exists ---


async def test_session_exists_true(manager: SessionManager) -> None:
    session = await manager.create_session()
    assert await manager.session_exists(session.id) is True


async def test_session_exists_false(manager: SessionManager) -> None:
    assert await manager.session_exists("nonexistent") is False


# --- get_budget_info ---


async def test_get_budget_info(manager: SessionManager) -> None:
    session = await manager.create_session()

    info = await manager.get_budget_info(session.id)
    assert info is not None
    remaining, limit = info
    assert remaining == limit
    assert limit == session.budget_limit


async def test_get_budget_info_nonexistent(manager: SessionManager) -> None:
    assert await manager.get_budget_info("nonexistent") is None


# --- get_session ---


async def test_get_session(manager: SessionManager) -> None:
    session = await manager.create_session()

    bp = _make_blueprint("Rock")
    await manager.save_object(session.id, bp, x=10.0, y=20.0)

    loaded = await manager.get_session(session.id)
    assert loaded is not None
    assert loaded.id == session.id
    assert len(loaded.objects) == 1
    assert loaded.objects[0].blueprint.name == "Rock"
    assert loaded.objects[0].x == 10.0
    assert loaded.objects[0].y == 20.0


async def test_get_session_nonexistent(manager: SessionManager) -> None:
    assert await manager.get_session("nonexistent") is None


async def test_get_session_corrupt_json() -> None:
    """Corrupt blueprint_json rows are skipped gracefully (logged, not raised)."""
    db = await _setup_db()
    mgr = SessionManager(db)
    session = await mgr.create_session()

    # Insert a valid object
    bp = _make_blueprint("Good")
    await mgr.save_object(session.id, bp)

    # Insert a corrupt row directly
    await db.execute(
        "INSERT INTO objects (session_id, object_id, blueprint_json, x, y, durability)"
        " VALUES (?, 'bad', '{invalid json', 0, 0, 0)",
        (session.id,),
    )
    await db.commit()

    # get_session catches the exception and skips corrupt rows
    loaded = await mgr.get_session(session.id)
    assert loaded is not None
    assert len(loaded.objects) == 1
    assert loaded.objects[0].blueprint.name == "Good"
    await db.close()


# --- save_object ---


async def test_save_object(manager: SessionManager) -> None:
    session = await manager.create_session()

    bp = _make_blueprint("Sword")
    await manager.save_object(session.id, bp, x=5.0, y=15.0)

    loaded = await manager.get_session(session.id)
    assert loaded is not None
    assert len(loaded.objects) == 1
    obj = loaded.objects[0]
    assert obj.blueprint.name == "Sword"
    assert obj.object_id == bp.id
    assert obj.x == 5.0
    assert obj.y == 15.0


# --- save_objects_batch ---


async def test_save_objects_batch(manager: SessionManager) -> None:
    session = await manager.create_session()

    bps = [_make_blueprint(f"Item {i}") for i in range(5)]
    await manager.save_objects_batch(session.id, bps)

    loaded = await manager.get_session(session.id)
    assert loaded is not None
    assert len(loaded.objects) == 5
    names = {o.blueprint.name for o in loaded.objects}
    assert names == {f"Item {i}" for i in range(5)}


# --- save_state / _sync_objects ---


async def test_save_state_sync_objects(manager: SessionManager) -> None:
    session = await manager.create_session()

    bps = [_make_blueprint(f"Obj {i}") for i in range(3)]
    await manager.save_objects_batch(session.id, bps)

    # Sync with only the first object — others should be deleted
    keep = WorldObject(
        object_id=bps[0].id,
        blueprint=bps[0],
        x=1.0,
        y=2.0,
        hp=float(bps[0].starting_hp),
    )
    await manager.save_state(session.id, objects=[keep])

    loaded = await manager.get_session(session.id)
    assert loaded is not None
    assert len(loaded.objects) == 1
    assert loaded.objects[0].object_id == bps[0].id


async def test_save_state_empty_clears_all(manager: SessionManager) -> None:
    session = await manager.create_session()

    bps = [_make_blueprint(f"Obj {i}") for i in range(3)]
    await manager.save_objects_batch(session.id, bps)

    await manager.save_state(session.id, objects=[])

    loaded = await manager.get_session(session.id)
    assert loaded is not None
    assert len(loaded.objects) == 0


# --- reserve_budget ---


async def test_reserve_budget_success(manager: SessionManager) -> None:
    session = await manager.create_session()

    success, remaining = await manager.reserve_budget(session.id, 0.041)
    assert success is True
    assert remaining > 0


async def test_reserve_budget_insufficient(manager: SessionManager) -> None:
    db = await _setup_db()
    mgr = SessionManager(db)
    await db.execute(
        "INSERT INTO sessions (id, created_at, budget_limit, budget_used)"
        " VALUES ('s1', '2024-01-01', 0.05, 0.04)"
    )
    await db.commit()

    success, _ = await mgr.reserve_budget("s1", 0.041)
    assert success is False
    await db.close()


async def test_reserve_budget_nonexistent(manager: SessionManager) -> None:
    success, remaining = await manager.reserve_budget("nonexistent", 0.041)
    assert success is False
    assert remaining == -1.0
