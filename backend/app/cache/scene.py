"""In-memory per-session scene cache for O(1) runtime lookups.

Pairwise results mirror cache.db for fast access during collisions.
Creature behavior is scene-local only (prompts include scene inventory,
so results are scene-dependent and not worth persisting).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.cache.store import normalize_name, pair_key


@dataclass
class PairwiseResult:
    """Outcome of two objects colliding. 6 fields from 6 parallel LLM calls.

    damage 100 = instant destroy. force_b is signed: negative = pull, positive = push.
    State encoding: 0=none, 1-4=add State(n), 5-8=remove State(n-4).
    """

    damage_a: int  # 0-100, 100=destroyed
    damage_b: int  # 0-100, 100=destroyed
    state_change_a: int  # 0=none, 1-4=add, 5-8=remove
    state_change_b: int
    force_b: int  # -100 to 100 (negative=pull, positive=push)
    continuous: bool  # False=instant, True=continuous (re-apply on field tick)

    def to_dict(self) -> dict:
        return {
            "damage_a": self.damage_a,
            "damage_b": self.damage_b,
            "state_change_a": self.state_change_a,
            "state_change_b": self.state_change_b,
            "force_b": self.force_b,
            "continuous": self.continuous,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PairwiseResult:
        return cls(
            damage_a=d.get("damage_a", 0),
            damage_b=d.get("damage_b", 0),
            state_change_a=d.get("state_change_a", 0),
            state_change_b=d.get("state_change_b", 0),
            force_b=d.get("force_b", 0),
            continuous=d.get("continuous", False),
        )


@dataclass
class CreatureBehavior:
    """Per creature x target pair behavior. Scene-local, not persisted."""

    movement: int  # 0=approach, 1=flee, 2=orbit, 3=ignore
    priority: int  # 0-3 (0=ignore, 1=mild, 2=moderate, 3=driven)
    action: int  # 0=nothing,1=damage,2=heal,3=add_state,4=remove_state,5=destroy,6=take
    amount: int  # 0-100 damage/heal intensity (action 1,2)
    state_id: int  # 1-4 State enum value (action 3,4)

    def to_dict(self) -> dict:
        return {
            "movement": self.movement,
            "priority": self.priority,
            "action": self.action,
            "amount": self.amount,
            "state_id": self.state_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> CreatureBehavior:
        return cls(
            movement=d.get("movement", 3),
            priority=d.get("priority", 0),
            action=d.get("action", 0),
            amount=d.get("amount", 0),
            state_id=d.get("state_id", 0),
        )


def nothing_happens() -> PairwiseResult:
    """Safe default for uncached/unscreened collisions."""
    return PairwiseResult(0, 0, 0, 0, 0, False)


class SceneCache:
    """Per-session in-memory cache. Created when a session connects."""

    def __init__(self) -> None:
        self._pairwise: dict[str, PairwiseResult] = {}
        self._creature: dict[str, CreatureBehavior] = {}
        self._stale: set[str] = set()

    def get_pairwise(self, name_a: str, name_b: str) -> PairwiseResult | None:
        key = pair_key(name_a, name_b)
        return None if key in self._stale else self._pairwise.get(key)

    def put_pairwise(self, name_a: str, name_b: str, result: PairwiseResult) -> None:
        key = pair_key(name_a, name_b)
        self._pairwise[key] = result
        self._stale.discard(key)

    def mark_stale(self, name: str) -> list[str]:
        """Mark all pairs involving this object as stale. Returns stale keys."""
        n = normalize_name(name)
        stale_keys = [k for k in self._pairwise if n in k.split("::")]
        self._stale.update(stale_keys)
        return stale_keys

    def get_creature(self, creature: str, target: str) -> CreatureBehavior | None:
        return self._creature.get(pair_key(creature, target))

    def put_creature(self, creature: str, target: str, behavior: CreatureBehavior) -> None:
        self._creature[pair_key(creature, target)] = behavior

    def mark_creature_stale_for_target(self, target_name: str) -> list[str]:
        """Remove all creature behavior entries where target matches.

        Since pair_key sorts lexicographically, the target can be on either side.
        Returns keys of removed entries.
        """
        n = normalize_name(target_name)
        stale_keys = [k for k in self._creature if n in k.split("::")]
        for k in stale_keys:
            del self._creature[k]
        return stale_keys

    def mark_creature_stale_for_creature(self, creature_name: str) -> list[str]:
        """Remove all behavior entries where this creature is the source.

        Used when a creature's own state changes (e.g., zombie catches fire),
        since its behaviors toward other objects may differ.
        Same logic as mark_creature_stale_for_target — pair_key is sorted,
        so the creature name can be on either side.
        """
        n = normalize_name(creature_name)
        stale_keys = [k for k in self._creature if n in k.split("::")]
        for k in stale_keys:
            del self._creature[k]
        return stale_keys

    def clear_creature(self) -> None:
        self._creature.clear()

    def all_pairwise_for(self, name: str) -> dict[str, PairwiseResult]:
        """Return all pairwise entries involving name (for client delivery)."""
        n = normalize_name(name)
        return {k: v for k, v in self._pairwise.items() if n in k.split("::")}

    def all_creature_for(self, creature: str) -> dict[str, CreatureBehavior]:
        """Return all creature behavior entries for a creature."""
        n = normalize_name(creature)
        return {k: v for k, v in self._creature.items() if k.startswith(f"{n}::")}
