from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

import aiosqlite

from app.models.blueprint import GameObjectBlueprint
from app.models.session import (
    EquipmentSlot,
    InventorySlot,
    Session,
    WorldObject,
)


class SessionManager:
    """Manages game sessions with aiosqlite persistence."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def create_session(self) -> Session:
        """Create a new session with default state."""
        session_id = str(uuid.uuid4())
        created_at = datetime.now(UTC).isoformat()

        await self._db.execute(
            "INSERT INTO sessions (id, created_at, budget_used, level_progress)"
            " VALUES (?, ?, 0.0, 0)",
            (session_id, created_at),
        )

        # Initialize 8 empty inventory slots
        for slot in range(8):
            await self._db.execute(
                "INSERT INTO inventory (session_id, slot, object_id) VALUES (?, ?, NULL)",
                (session_id, slot),
            )

        # Initialize 3 equipment slots
        for slot_name in ("hand", "back", "head"):
            await self._db.execute(
                "INSERT INTO equipment (session_id, slot_name, object_id) VALUES (?, ?, NULL)",
                (session_id, slot_name),
            )

        await self._db.commit()

        return Session(
            id=session_id,
            created_at=created_at,
            budget_used=0.0,
            level_progress=0,
            objects=[],
            inventory=[InventorySlot(slot=i) for i in range(8)],
            equipment=[
                EquipmentSlot(slot_name="hand"),
                EquipmentSlot(slot_name="back"),
                EquipmentSlot(slot_name="head"),
            ],
        )

    async def get_session(self, session_id: str) -> Session | None:
        """Load a session from the database."""
        cursor = await self._db.execute(
            "SELECT id, created_at, budget_used, level_progress FROM sessions WHERE id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        sid, created_at, budget_used, level_progress = row

        # Load objects
        obj_cursor = await self._db.execute(
            "SELECT object_id, blueprint_json, x, y, durability FROM objects WHERE session_id = ?",
            (session_id,),
        )
        objects = []
        async for obj_row in obj_cursor:
            object_id, blueprint_json, x, y, durability = obj_row
            blueprint = GameObjectBlueprint.model_validate_json(blueprint_json)
            objects.append(
                WorldObject(
                    object_id=object_id,
                    blueprint=blueprint,
                    x=x,
                    y=y,
                    durability=durability,
                )
            )

        # Load inventory
        inv_cursor = await self._db.execute(
            "SELECT slot, object_id FROM inventory WHERE session_id = ? ORDER BY slot",
            (session_id,),
        )
        inventory = []
        async for inv_row in inv_cursor:
            slot, object_id = inv_row
            inventory.append(InventorySlot(slot=slot, object_id=object_id))

        # Load equipment
        eq_cursor = await self._db.execute(
            "SELECT slot_name, object_id FROM equipment WHERE session_id = ?",
            (session_id,),
        )
        equipment = []
        async for eq_row in eq_cursor:
            slot_name, object_id = eq_row
            equipment.append(EquipmentSlot(slot_name=slot_name, object_id=object_id))

        return Session(
            id=sid,
            created_at=created_at,
            budget_used=budget_used,
            level_progress=level_progress,
            objects=objects,
            inventory=inventory,
            equipment=equipment,
        )

    async def save_object(
        self,
        session_id: str,
        blueprint: GameObjectBlueprint,
        x: float = 0.0,
        y: float = 0.0,
    ) -> None:
        """Save or update a world object in the session."""
        blueprint_json = blueprint.model_dump_json()
        durability = float(blueprint.starting_durability)

        await self._db.execute(
            """
            INSERT OR REPLACE INTO objects (session_id, object_id, blueprint_json, x, y, durability)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, blueprint.id, blueprint_json, x, y, durability),
        )
        await self._db.commit()

    async def _replace_rows(
        self,
        table: str,
        session_id: str,
        rows: Sequence[Any],
        to_tuple_fn: Callable[[str, Any], tuple[Any, ...]],
    ) -> None:
        """DELETE all rows for a session in *table*, then INSERT new ones."""
        await self._db.execute(
            f"DELETE FROM {table} WHERE session_id = ?", (session_id,)
        )
        for row in rows:
            values = to_tuple_fn(session_id, row)
            placeholders = ", ".join("?" for _ in values)
            await self._db.execute(
                f"INSERT INTO {table} VALUES ({placeholders})", values,
            )

    async def save_state(
        self,
        session_id: str,
        objects: list[WorldObject],
        inventory: list[InventorySlot],
        equipment: list[EquipmentSlot],
        level_progress: int,
    ) -> None:
        """Batch sync of full session state."""
        # Update session level progress
        await self._db.execute(
            "UPDATE sessions SET level_progress = ? WHERE id = ?",
            (level_progress, session_id),
        )

        await self._replace_rows(
            "objects", session_id, objects,
            lambda sid, obj: (
                sid, obj.object_id, obj.blueprint.model_dump_json(),
                obj.x, obj.y, obj.durability,
            ),
        )
        await self._replace_rows(
            "inventory", session_id, inventory,
            lambda sid, inv: (sid, inv.slot, inv.object_id),
        )
        await self._replace_rows(
            "equipment", session_id, equipment,
            lambda sid, eq: (sid, eq.slot_name, eq.object_id),
        )

        await self._db.commit()

    async def track_cost(self, session_id: str, amount: float) -> float:
        """Add cost to session budget and return new total."""
        await self._db.execute(
            "UPDATE sessions SET budget_used = budget_used + ? WHERE id = ?",
            (amount, session_id),
        )
        await self._db.commit()

        cursor = await self._db.execute(
            "SELECT budget_used FROM sessions WHERE id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0.0
