"""In-memory per-session cache for object behavior.

BehaviorEntry: per subject x target behavioral data, scene-local only.
BehaviorCache: in-memory session cache for behavioral entries.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.cache.store import directed_key, normalize_name


@dataclass
class BehaviorEntry:
    """Per subject x target behavioral data. Scene-local, not persisted.

    One entry per directed pair — if both objects have behaviors,
    two entries exist (one keyed subject::target each way).

    Actions are composite: primary action + optional state modifier + optional delivery.
    Action enum: 0=nothing, 1=damage, 2=heal, 3=consume, 4=push
    State action: 0=nothing, 1=add_state, 2=remove_state
    Delivery: 0=contact, 1=projectile. Knockback emerges from impactor momentum
    (contact lunge, projectile mass x velocity) — no separate force flag.
    """

    movement: int = 2  # 0=approach, 1=flee, 2=ignore
    priority: int = 0  # 0-3 (0=ignore, 1=mild, 2=moderate, 3=driven)
    action: int = 0  # 0=nothing, 1=damage, 2=heal, 3=consume, 4=push
    amount: int = 0  # 0-100 intensity (damage/heal/push)
    state_action: int = 0  # 0=nothing, 1=add_state, 2=remove_state
    state_id: int = 0  # 1-4 State enum value (if state_action != 0)
    delivery: int = 0  # 0=contact, 1=projectile (for damage/heal/push)
    projectile_name: str = ""  # e.g. "missile", "arrow"; "" when delivery=contact

    def to_dict(self) -> dict:
        return {
            "movement": self.movement,
            "priority": self.priority,
            "action": self.action,
            "amount": self.amount,
            "state_action": self.state_action,
            "state_id": self.state_id,
            "delivery": self.delivery,
            "projectile_name": self.projectile_name,
        }

    @classmethod
    def from_dict(cls, d: dict) -> BehaviorEntry:
        return cls(
            movement=d.get("movement", 2),
            priority=d.get("priority", 0),
            action=d.get("action", 0),
            amount=d.get("amount", 0),
            state_action=d.get("state_action", 0),
            state_id=d.get("state_id", 0),
            delivery=d.get("delivery", 0),
            projectile_name=d.get("projectile_name", ""),
        )


class BehaviorCache:
    """Per-session in-memory cache for object behavior (scene-local)."""

    def __init__(self) -> None:
        self._behavior: dict[str, BehaviorEntry] = {}

    def get_behavior(self, subject: str, target: str) -> BehaviorEntry | None:
        return self._behavior.get(directed_key(subject, target))

    def put_behavior(self, subject: str, target: str, entry: BehaviorEntry) -> None:
        self._behavior[directed_key(subject, target)] = entry

    def invalidate_behavior(self, name: str) -> list[str]:
        """Remove all behavior entries involving this object. Returns removed keys."""
        n = normalize_name(name)
        stale_keys = [k for k in self._behavior if n in k.split("::")]
        for k in stale_keys:
            del self._behavior[k]
        return stale_keys
