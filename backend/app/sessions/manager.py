import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import aiosqlite

from app.config import settings
from app.models.blueprint import GameObjectBlueprint
from app.models.session import (
    EquipmentSlots,
    InventorySlot,
    Session,
    WorldObject,
)


class SessionManager:
    """Manages game sessions with aiosqlite persistence."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def session_exists(self, session_id: str) -> bool:
        """Check if a session exists without loading full state."""
        cursor = await self._db.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,))
        return await cursor.fetchone() is not None

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
        return budget_limit - budget_used, budget_limit

    async def create_session(self) -> Session:
        """Create a new session with default state."""
        session_id = str(uuid.uuid4())
        created_at = datetime.now(UTC).isoformat()
        budget_limit = settings.session_budget_usd

        await self._db.execute(
            "INSERT INTO sessions (id, created_at, budget_used, budget_limit,"
            " current_level, levels_completed)"
            " VALUES (?, ?, 0.0, ?, 1, '[]')",
            (session_id, created_at, budget_limit),
        )

        # Initialize 8 empty inventory slots
        await self._db.executemany(
            "INSERT INTO inventory (session_id, slot, object_id) VALUES (?, ?, NULL)",
            [(session_id, slot) for slot in range(8)],
        )

        # Initialize equipment (single row with JSON)
        await self._db.execute(
            "INSERT INTO equipment (session_id, equipment_json) VALUES (?, ?)",
            (session_id, EquipmentSlots().model_dump_json()),
        )

        await self._db.commit()

        return Session(
            id=session_id,
            created_at=created_at,
            budget_used=0.0,
            budget_limit=budget_limit,
            current_level=1,
            levels_completed=[],
            objects=[],
            inventory=[InventorySlot(slot=i) for i in range(8)],
            equipment=EquipmentSlots(),
        )

    async def get_session(self, session_id: str) -> Session | None:
        """Load a session from the database."""
        cursor = await self._db.execute(
            "SELECT id, created_at, budget_used, budget_limit,"
            " current_level, levels_completed"
            " FROM sessions WHERE id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        sid, created_at, budget_used, budget_limit, current_level, levels_completed_json = row

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
            "SELECT equipment_json FROM equipment WHERE session_id = ?",
            (session_id,),
        )
        eq_row = await eq_cursor.fetchone()
        equipment = EquipmentSlots.model_validate_json(eq_row[0]) if eq_row else EquipmentSlots()

        return Session(
            id=sid,
            created_at=created_at,
            budget_used=budget_used,
            budget_limit=budget_limit,
            current_level=current_level,
            levels_completed=json.loads(levels_completed_json) if levels_completed_json else [],
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
        *,
        commit: bool = True,
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
        if commit:
            await self._db.commit()

    async def save_objects_batch(
        self,
        session_id: str,
        blueprints: Sequence[GameObjectBlueprint],
    ) -> None:
        """Save multiple objects in a single transaction."""
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
                    float(bp.starting_durability),
                )
                for bp in blueprints
            ],
        )
        await self._db.commit()

    async def _sync_objects(self, session_id: str, objects: list[WorldObject]) -> None:
        """Sync objects: remove deleted, upsert current."""
        if not objects:
            await self._db.execute(
                "DELETE FROM objects WHERE session_id = ?",
                (session_id,),
            )
            return

        current_ids = [obj.object_id for obj in objects]
        placeholders = ",".join("?" for _ in current_ids)
        await self._db.execute(
            f"DELETE FROM objects WHERE session_id = ? AND object_id NOT IN ({placeholders})",
            (session_id, *current_ids),
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
                    obj.durability,
                )
                for obj in objects
            ],
        )

    async def _sync_inventory(self, session_id: str, inventory: list[InventorySlot]) -> None:
        """Sync inventory slots via upsert (fixed 8 slots, no deletion needed)."""
        await self._db.executemany(
            "INSERT OR REPLACE INTO inventory (session_id, slot, object_id) VALUES (?, ?, ?)",
            [(session_id, inv.slot, inv.object_id) for inv in inventory],
        )

    async def save_state(
        self,
        session_id: str,
        objects: list[WorldObject] | None = None,
        inventory: list[InventorySlot] | None = None,
        equipment: EquipmentSlots | None = None,
        current_level: int | None = None,
        levels_completed: list[int] | None = None,
    ) -> None:
        """Batch sync of session state. Only provided fields are updated."""
        dirty = False

        if current_level is not None or levels_completed is not None:
            updates = []
            params: list[Any] = []
            if current_level is not None:
                updates.append("current_level = ?")
                params.append(current_level)
            if levels_completed is not None:
                updates.append("levels_completed = ?")
                params.append(json.dumps(levels_completed))
            params.append(session_id)
            await self._db.execute(
                f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?",
                tuple(params),
            )
            dirty = True

        if objects is not None:
            await self._sync_objects(session_id, objects)
            dirty = True

        if inventory is not None:
            await self._sync_inventory(session_id, inventory)
            dirty = True

        if equipment is not None:
            await self._db.execute(
                "UPDATE equipment SET equipment_json = ? WHERE session_id = ?",
                (equipment.model_dump_json(), session_id),
            )
            dirty = True

        if dirty:
            await self._db.commit()

    async def track_cost(self, session_id: str, amount: float, *, commit: bool = True) -> float:
        """Add cost to session budget and return new total."""
        await self._db.execute(
            "UPDATE sessions SET budget_used = budget_used + ? WHERE id = ?",
            (amount, session_id),
        )
        if commit:
            await self._db.commit()

        cursor = await self._db.execute(
            "SELECT budget_used FROM sessions WHERE id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0.0

    async def track_cost_and_save_object(
        self,
        session_id: str,
        amount: float,
        blueprint: GameObjectBlueprint,
    ) -> float:
        """Track cost and save object in a single transaction."""
        new_total = await self.track_cost(session_id, amount, commit=False)
        await self.save_object(session_id, blueprint, commit=False)
        await self._db.commit()
        return new_total
