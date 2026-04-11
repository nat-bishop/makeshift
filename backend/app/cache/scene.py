"""In-memory per-session caches for collision rules and creature behavior.

CollisionRule: force-only pairwise result, persisted to cache.db.
BehaviorEntry: per creature x target behavioral data, scene-local only.
BehaviorCache: in-memory session cache for behavioral entries.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.cache.store import normalize_name, pair_key


@dataclass(frozen=True)
class CollisionRule:
    """Force-only pairwise collision result. Persisted to cache.db.

    Force is mapped from choice categories:
    none=0, pull=-30, drag=-80, push=30, throw=80.
    """

    force_on_b: int = 0  # signed: negative=pull, positive=push

    def to_dict(self) -> dict:
        return {"force_on_b": self.force_on_b}

    @classmethod
    def from_dict(cls, d: dict) -> CollisionRule:
        return cls(force_on_b=d.get("force_on_b", 0))


@dataclass
class BehaviorEntry:
    """Per creature x target behavioral data. Scene-local, not persisted.

    One entry per autonomous side of a pair — if both are autonomous,
    two entries exist (one keyed creature::target each way).
    """

    movement: int = 2  # 0=approach, 1=flee, 2=ignore
    priority: int = 0  # 0-3 (0=ignore, 1=mild, 2=moderate, 3=driven)
    action: int = 0  # 0=nothing,1=damage,2=heal,3=add_state,4=remove_state,5=consume
    amount: int = 0  # 0-100 damage/heal intensity (action 1,2)
    state_id: int = 0  # 1-4 State enum value (action 3,4)

    def to_dict(self) -> dict:
        return {
            "movement": self.movement,
            "priority": self.priority,
            "action": self.action,
            "amount": self.amount,
            "state_id": self.state_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> BehaviorEntry:
        return cls(
            movement=d.get("movement", 2),
            priority=d.get("priority", 0),
            action=d.get("action", 0),
            amount=d.get("amount", 0),
            state_id=d.get("state_id", 0),
        )


def no_force() -> CollisionRule:
    """Safe default for uncached collisions."""
    return CollisionRule()


class BehaviorCache:
    """Per-session in-memory cache for creature behavior.

    Collision rules are NOT stored here — they live in CacheStore (SQLite).
    A thin read-through dict (_collision_hot) avoids async DB reads at runtime.
    """

    def __init__(self) -> None:
        self._behavior: dict[str, BehaviorEntry] = {}
        self._collision_hot: dict[str, CollisionRule] = {}

    # ---- Collision (read-through hot cache of CacheStore) ----

    def get_collision(self, name_a: str, name_b: str) -> CollisionRule | None:
        return self._collision_hot.get(pair_key(name_a, name_b))

    def put_collision(self, name_a: str, name_b: str, rule: CollisionRule) -> None:
        self._collision_hot[pair_key(name_a, name_b)] = rule

    # ---- Behavior (scene-local, creature pairs only) ----

    def get_behavior(self, creature: str, target: str) -> BehaviorEntry | None:
        return self._behavior.get(pair_key(creature, target))

    def put_behavior(self, creature: str, target: str, entry: BehaviorEntry) -> None:
        self._behavior[pair_key(creature, target)] = entry

    def invalidate_behavior(self, name: str) -> list[str]:
        """Remove all behavior entries involving this object. Returns removed keys."""
        n = normalize_name(name)
        stale_keys = [k for k in self._behavior if n in k.split("::")]
        for k in stale_keys:
            del self._behavior[k]
        return stale_keys

    def all_behavior_for(self, creature: str) -> dict[str, BehaviorEntry]:
        """Return all behavior entries for a creature (for client delivery)."""
        n = normalize_name(creature)
        return {k: v for k, v in self._behavior.items() if n in k.split("::")}
