import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import aiosqlite
import structlog

from app.config import settings
from app.models.blueprint import GameObjectBlueprint
from app.models.session import (
    Session,
    WorldObject,
)

logger = structlog.get_logger()


class SessionManager:
    """Manages game sessions with aiosqlite persistence."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def session_exists(self, session_id: str) -> bool:
        """Check if a session exists without loading full state."""
        cursor = await self._db.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,))
        exists = await cursor.fetchone() is not None
        logger.debug("session_exists_check", session_id=session_id, exists=exists)
        return exists

    async def get_budget_info(self, session_id: str) -> tuple[float, float] | None:
        """Return (budget_remaining, budget_limit) or None if session doesn't exist."""
        cursor = await self._db.execute(
            "SELECT budget_limit, budget_used FROM sessions WHERE id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        budget_limit, budget_used = row
        remaining = budget_limit - budget_used
        logger.debug(
            "budget_info", session_id=session_id, remaining=remaining, limit=budget_limit
        )
        return remaining, budget_limit

    async def create_session(self) -> Session:
        """Create a new session with default state."""
        session_id = str(uuid.uuid4())
        created_at = datetime.now(UTC).isoformat()
        budget_limit = settings.session_budget_usd

        await self._db.execute(
            "INSERT INTO sessions (id, created_at, budget_used, budget_limit)"
            " VALUES (?, ?, 0.0, ?)",
            (session_id, created_at, budget_limit),
        )
        await self._db.commit()
        logger.info("session_db_created", session_id=session_id, budget_limit=budget_limit)

        return Session(
            id=session_id,
            created_at=created_at,
            budget_used=0.0,
            budget_limit=budget_limit,
            objects=[],
        )

    async def get_session(self, session_id: str) -> Session | None:
        """Load a session from the database."""
        cursor = await self._db.execute(
            "SELECT id, created_at, budget_used, budget_limit FROM sessions WHERE id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            logger.debug("session_not_found", session_id=session_id)
            return None

        sid, created_at, budget_used, budget_limit = row

        # Load objects
        obj_cursor = await self._db.execute(
            "SELECT object_id, blueprint_json, x, y, durability FROM objects WHERE session_id = ?",
            (session_id,),
        )
        objects = []
        async for obj_row in obj_cursor:
            object_id, blueprint_json, x, y, durability = obj_row
            try:
                blueprint = GameObjectBlueprint.model_validate_json(blueprint_json)
            except Exception:
                logger.warning("object_json_corrupt", object_id=object_id, session_id=session_id)
                continue
            objects.append(
                WorldObject(
                    object_id=object_id,
                    blueprint=blueprint,
                    x=x,
                    y=y,
                    hp=durability,
                )
            )

        session = Session(
            id=sid,
            created_at=created_at,
            budget_used=budget_used,
            budget_limit=budget_limit,
            objects=objects,
        )
        logger.debug(
            "session_loaded",
            session_id=sid,
            objects=len(objects),
        )
        return session

    async def get_object_blueprint(
        self, session_id: str, object_id: str
    ) -> GameObjectBlueprint | None:
        """Look up a single object's blueprint by session and object ID."""
        cursor = await self._db.execute(
            "SELECT blueprint_json FROM objects WHERE session_id = ? AND object_id = ?",
            (session_id, object_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return GameObjectBlueprint.model_validate_json(row[0])

    async def save_object(
        self,
        session_id: str,
        blueprint: GameObjectBlueprint,
        x: float = 0.0,
        y: float = 0.0,
        *,
        commit: bool = True,
    ) -> None:
        """Save or update a world object in the session."""
        blueprint_json = blueprint.model_dump_json()
        durability = float(blueprint.destructibility.hp)

        await self._db.execute(
            """
            INSERT OR REPLACE INTO objects (session_id, object_id, blueprint_json, x, y, durability)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, blueprint.id, blueprint_json, x, y, durability),
        )
        logger.debug("object_saved", session_id=session_id, object_id=blueprint.id)
        if commit:
            await self._db.commit()

    async def save_objects_batch(
        self,
        session_id: str,
        blueprints: Sequence[GameObjectBlueprint],
    ) -> None:
        """Save multiple objects in a single transaction."""
        logger.debug("objects_batch_saving", count=len(blueprints))
        await self._db.executemany(
            """
            INSERT OR REPLACE INTO objects
                (session_id, object_id, blueprint_json, x, y, durability)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    session_id,
                    bp.id,
                    bp.model_dump_json(),
                    0.0,
                    0.0,
                    float(bp.destructibility.hp),
                )
                for bp in blueprints
            ],
        )
        await self._db.commit()
        logger.debug("objects_batch_saved", session_id=session_id, count=len(blueprints))

    async def _sync_objects(self, session_id: str, objects: list[WorldObject]) -> None:
        """Sync objects: remove deleted, upsert current."""
        if not objects:
            await self._db.execute(
                "DELETE FROM objects WHERE session_id = ?",
                (session_id,),
            )
            logger.debug("sync_objects_cleared", session_id=session_id)
            return

        current_ids = [obj.object_id for obj in objects]
        placeholders = ",".join("?" for _ in current_ids)
        delete_cursor = await self._db.execute(
            f"DELETE FROM objects WHERE session_id = ? AND object_id NOT IN ({placeholders})",
            (session_id, *current_ids),
        )
        logger.debug(
            "sync_objects",
            session_id=session_id,
            deleted=delete_cursor.rowcount,
            upserted=len(objects),
        )
        await self._db.executemany(
            """
            INSERT OR REPLACE INTO objects
                (session_id, object_id, blueprint_json, x, y, durability)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    session_id,
                    obj.object_id,
                    obj.blueprint.model_dump_json(),
                    obj.x,
                    obj.y,
                    obj.hp,
                )
                for obj in objects
            ],
        )

    async def save_state(
        self,
        session_id: str,
        objects: list[WorldObject] | None = None,
    ) -> None:
        """Batch sync of session state. Only provided fields are updated."""
        if objects is not None:
            await self._sync_objects(session_id, objects)
            await self._db.commit()
            logger.debug("state_saved", object_count=len(objects))

    async def reserve_budget(self, session_id: str, amount: float) -> tuple[bool, float]:
        """Atomically reserve budget if sufficient funds remain.

        Returns (success, budget_remaining). Uses a conditional UPDATE to avoid
        the read-check-write race window. Returns -1.0 for remaining if session
        doesn't exist (sentinel value).
        """
        cursor = await self._db.execute(
            "UPDATE sessions SET budget_used = budget_used + ?"
            " WHERE id = ? AND budget_used + ? <= budget_limit",
            (amount, session_id, amount),
        )
        await self._db.commit()

        row_cursor = await self._db.execute(
            "SELECT budget_limit - budget_used FROM sessions WHERE id = ?",
            (session_id,),
        )
        row = await row_cursor.fetchone()
        if row is None:
            logger.warning("budget_reserve_session_not_found", session_id=session_id)
            return False, -1.0
        remaining: float = row[0]
        if cursor.rowcount == 0:
            logger.warning(
                "budget_reserve_insufficient",
                session_id=session_id,
                requested=amount,
                remaining=remaining,
            )
            return False, remaining
        logger.debug("budget_reserved", amount=amount, remaining=remaining)
        return True, remaining
