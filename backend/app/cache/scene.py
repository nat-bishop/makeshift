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
    """Outcome of two objects colliding. 9 fields from 9 parallel LLM calls."""

    damage_a: int  # 0-100
    damage_b: int  # 0-100
    state_change_a: int  # 0=none, 1-7=add State(n), 8-14=remove State(n-7)
    state_change_b: int
    force_b: int  # 0-100 magnitude
    push_pull: int  # 0=push, 1=pull
    destroy_a: bool
    destroy_b: bool
    continuous: bool  # False=instant, True=continuous (re-apply on field tick)

    def to_dict(self) -> dict:
        return {
            "damage_a": self.damage_a,
            "damage_b": self.damage_b,
            "state_change_a": self.state_change_a,
            "state_change_b": self.state_change_b,
            "force_b": self.force_b,
            "push_pull": self.push_pull,
            "destroy_a": self.destroy_a,
            "destroy_b": self.destroy_b,
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
            push_pull=d.get("push_pull", 0),
            destroy_a=d.get("destroy_a", False),
            destroy_b=d.get("destroy_b", False),
            continuous=d.get("continuous", False),
        )


@dataclass
class CreatureBehavior:
    """Per creature x target pair behavior. Scene-local, not persisted."""

    movement: int  # 0=approach, 1=flee, 2=orbit, 3=ignore
    strength: int  # 0-100
    action: int  # 0=nothing,1=damage,2=heal,3=add_state,4=remove_state,5=destroy,6=take
    param: int  # damage/heal amount or state_id (1-7)

    def to_dict(self) -> dict:
        return {
            "movement": self.movement,
            "strength": self.strength,
            "action": self.action,
            "param": self.param,
        }

    @classmethod
    def from_dict(cls, d: dict) -> CreatureBehavior:
        return cls(
            movement=d.get("movement", 3),
            strength=d.get("strength", 0),
            action=d.get("action", 0),
            param=d.get("param", 0),
        )


def nothing_happens() -> PairwiseResult:
    """Safe default for uncached/unscreened collisions."""
    return PairwiseResult(0, 0, 0, 0, 0, 0, False, False, False)


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

    def put_creature(
        self, creature: str, target: str, behavior: CreatureBehavior
    ) -> None:
        self._creature[pair_key(creature, target)] = behavior

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
