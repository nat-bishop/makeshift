"""Collision rule evaluation via LLM — force only.

States are handled by per-object initial_states/susceptible_states + tick-based
propagation. Destruction is emergent via essential-state loss. This module
evaluates only the pairwise force between colliding objects.

Two phases:
  1. Screening: 1 call per new object (~5-15 output tokens), identifies interesting pairs
  2. Force eval: 1 parallel 1-token call per interesting pair via run_questions()
"""

from __future__ import annotations

import asyncio
import re

import structlog

from app.cache.scene import BehaviorCache, CollisionRule
from app.cache.store import CacheStore, normalize_name
from app.config import settings
from app.creator.llm import ask_text
from app.creator.question_graph import Question, run_questions
from app.models.blueprint import DURABILITY_NAMES, GameObjectBlueprint

logger = structlog.get_logger()


_SURFACE_NAMES = {0: "slick", 1: "normal", 2: "sticky"}

# Discrete force category → signed force value.
_FORCE_MAP: dict[int, int] = {0: 0, 1: -30, 2: -80, 3: 30, 4: 80}


def _obj_summary(bp: GameObjectBlueprint) -> str:
    """Compact object summary for LLM prompt context."""
    parts = [f"{bp.physics.mass_kg}kg", f"{bp.physics.height_cm}cm"]
    durability_name = DURABILITY_NAMES.get(bp.durability, "normal")
    parts.append(durability_name)
    parts.append(_SURFACE_NAMES.get(bp.physics.surface, "normal-surface"))
    if bp.autonomous:
        parts.append("creature")
    return f"{bp.name} ({', '.join(parts)})"


# ---- Force question (1 per pair) ----

FORCE_QUESTION = Question(
    "force_on_b",
    "{a_desc} contacts {b_desc}.",
    "choice",
    default="none",
    instructions=(
        "Two objects make contact in a 2D game. Does the first push or pull the "
        "second? none=no force, pull=weak pull, drag=strong pull, push=weak push, "
        "throw=strong push. Return one word."
    ),
    choices=("none", "pull", "drag", "push", "throw"),
    choice_map=(("none", 0), ("pull", 1), ("drag", 2), ("push", 3), ("throw", 4)),
)


# ---- Screening ----


async def screen_pairs(
    new_obj: GameObjectBlueprint,
    scene_objects: list[GameObjectBlueprint],
) -> list[str]:
    """Screening: which scene objects have interesting force interactions with new_obj?

    Returns list of object names worth evaluating.
    On parse failure, returns ALL names (conservative fallback).
    """
    if not scene_objects:
        return []

    numbered = "\n".join(f"{i + 1}. {_obj_summary(o)}" for i, o in enumerate(scene_objects))
    prompt = (
        f"New object: {_obj_summary(new_obj)}.\n"
        f"Scene objects:\n{numbered}\n"
        f"Which would have interesting physical force interactions "
        f"(pushing, pulling, magnetism, wind, repulsion) "
        f"with {new_obj.name}? Reply with just the numbers separated by commas, or 'none'."
    )

    try:
        raw = await ask_text(prompt, max_tokens=30, default="none")
        if "none" in raw.lower():
            return []

        nums = [int(x) for x in re.findall(r"\d+", raw)]
        valid = [scene_objects[n - 1].name for n in nums if 1 <= n <= len(scene_objects)]
        if not valid:
            logger.warning("screen_no_valid_indices", raw=raw)
            return [o.name for o in scene_objects]
        return valid
    except Exception:
        logger.warning("screen_failed", exc_info=True)
        return [o.name for o in scene_objects]


# ---- Collision rule evaluation ----


async def evaluate_collision(
    bp_a: GameObjectBlueprint,
    bp_b: GameObjectBlueprint,
    cache: CacheStore,
    scene: BehaviorCache,
) -> CollisionRule:
    """Evaluate collision force between two objects. 1 LLM call.

    Checks scene hot cache -> persistent cache -> LLM eval.
    A/B always in lexicographic order by name.
    """
    # Enforce sorted order
    if normalize_name(bp_a.name) > normalize_name(bp_b.name):
        bp_a, bp_b = bp_b, bp_a

    name_a, name_b = bp_a.name, bp_b.name

    # 1. Hot cache
    cached = scene.get_collision(name_a, name_b)
    if cached is not None:
        logger.debug("collision_hot_cache_hit", pair=f"{name_a}::{name_b}")
        return cached

    # 2. Persistent cache
    if settings.creation_cache_enabled:
        db_cached = await cache.get_collision(name_a, name_b)
        if db_cached is not None:
            logger.debug("collision_db_cache_hit", pair=f"{name_a}::{name_b}")
            result = CollisionRule.from_dict(db_cached)
            scene.put_collision(name_a, name_b, result)
            return result

    # 3. LLM evaluation: 1 call
    a_desc, b_desc = _obj_summary(bp_a), _obj_summary(bp_b)
    raw = await run_questions(
        [FORCE_QUESTION],
        {"a": name_a, "b": name_b, "a_desc": a_desc, "b_desc": b_desc},
    )

    force_category = int(raw.get("force_on_b", 0))
    force_value = _FORCE_MAP.get(force_category, 0)
    result = CollisionRule(force_on_b=force_value)

    # Write through
    scene.put_collision(name_a, name_b, result)
    if settings.creation_cache_enabled:
        await cache.put_collision(
            name_a,
            name_b,
            result.to_dict(),
            model_version=settings.llm_model,
            commit=False,
        )

    logger.info("collision_eval", pair=f"{name_a}::{name_b}", force=result.force_on_b)
    return result


# ---- Spawn integration (collision rules only) ----


async def collision_spawn_integration(
    new_obj: GameObjectBlueprint,
    scene_objects: list[GameObjectBlueprint],
    cache: CacheStore,
    scene: BehaviorCache,
    pre_screened: list[str] | None = None,
) -> dict[str, CollisionRule]:
    """Run screening + force eval for a newly spawned object.

    Called as a background task during sprite gen.
    Returns dict of target_name -> CollisionRule for all evaluated pairs.
    """
    if pre_screened is not None:
        interesting = pre_screened
    else:
        interesting = await screen_pairs(new_obj, scene_objects)

    if not interesting:
        return {}

    bp_by_name = {normalize_name(o.name): o for o in scene_objects}
    evals = []
    names = []
    for name in interesting:
        n = normalize_name(name)
        if n in bp_by_name:
            evals.append(evaluate_collision(new_obj, bp_by_name[n], cache, scene))
            names.append(name)

    evaluated = await asyncio.gather(*evals, return_exceptions=True)
    results: dict[str, CollisionRule] = {}
    for name, result in zip(names, evaluated, strict=True):
        if isinstance(result, CollisionRule):
            results[name] = result
        else:
            logger.warning("collision_eval_failed", target=name, error=str(result))

    await cache.flush()
    return results
