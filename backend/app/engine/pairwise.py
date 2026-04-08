"""Pairwise interaction evaluation via LLM.

Two phases:
  1. Screening: 1 call per new object (~5-15 output tokens), identifies interesting pairs
  2. Full eval: 6 parallel 1-token calls per interesting pair

6 pairwise questions per pair:
  damage_a (0-100, 100=destroyed), damage_b (0-100, 100=destroyed),
  state_change_a (0-8), state_change_b (0-8),
  force_b (-100 to 100, negative=pull),
  continuous (0=instant/1=continuous)

State encoding:
  0 = none
  1-4 = add State(1-4): burning, frozen, wet, electrified
  5-8 = remove State(n-4)
"""

from __future__ import annotations

import asyncio
import re

import structlog

from app.cache.scene import PairwiseResult, SceneCache
from app.cache.store import CacheStore, normalize_name
from app.config import settings
from app.creator.llm import ask_bool, ask_int, ask_text
from app.models.blueprint import GameObjectBlueprint
from app.models.state import STATE_CHANGE_PROMPT

logger = structlog.get_logger()


def _obj_summary(bp: GameObjectBlueprint) -> str:
    """Compact object summary for LLM prompt context (input tokens are free)."""
    parts = [f"{bp.physics.mass_kg}kg", f"{bp.physics.height_cm}cm"]
    if bp.destructibility.armor > 50:
        parts.append(f"armor {bp.destructibility.armor}")
    if bp.has_field:
        parts.append(f"field {bp.field_range_cm}cm")
    if bp.autonomous:
        parts.append("creature")
    if bp.destructibility.indestructible:
        parts.append("indestructible")
    return f"{bp.name} ({', '.join(parts)})"


# ---- Screening ----


async def screen_pairs(
    new_obj: GameObjectBlueprint,
    scene_objects: list[GameObjectBlueprint],
) -> list[str]:
    """Screening: which scene objects interact interestingly with new_obj?

    Returns list of object names worth evaluating.
    On parse failure, returns ALL names (conservative fallback).
    """
    if not scene_objects:
        return []

    numbered = "\n".join(
        f"{i + 1}. {_obj_summary(o)}" for i, o in enumerate(scene_objects)
    )
    prompt = (
        f"New object: {_obj_summary(new_obj)}.\n"
        f"Scene objects:\n{numbered}\n"
        f"Which would interact interestingly with {new_obj.name}? "
        f"Reply with just the numbers separated by commas, or 'none'."
    )

    try:
        raw = await ask_text(prompt, max_tokens=30, default="none")
        if "none" in raw.lower():
            return []

        nums = [int(x) for x in re.findall(r"\d+", raw)]
        valid = [
            scene_objects[n - 1].name
            for n in nums
            if 1 <= n <= len(scene_objects)
        ]
        if not valid:
            logger.warning("screen_no_valid_indices", raw=raw)
            return [o.name for o in scene_objects]
        return valid
    except Exception:
        logger.warning("screen_failed", exc_info=True)
        return [o.name for o in scene_objects]


# ---- Full pairwise evaluation ----

# 6 questions. Each produces 1 token.
PAIR_QUESTIONS: list[tuple[str, str, str]] = [
    (
        "damage_a", "int",
        "{a_desc} collides with {b_desc}. Damage to {a}? "
        "0=none 10=scratch 25=moderate 50=severe 75=critical 100=destroyed",
    ),
    (
        "damage_b", "int",
        "{a_desc} collides with {b_desc}. Damage to {b}? "
        "0=none 10=scratch 25=moderate 50=severe 75=critical 100=destroyed",
    ),
    (
        "state_change_a", "state",
        "{a_desc} collides with {b_desc}. State change on {a}? " + STATE_CHANGE_PROMPT,
    ),
    (
        "state_change_b", "state",
        "{a_desc} collides with {b_desc}. State change on {b}? " + STATE_CHANGE_PROMPT,
    ),
    (
        "force_b", "signed",
        "{a_desc} collides with {b_desc}. "
        "Force on {b}? -100(pull) to 100(push), 0=none",
    ),
    (
        "continuous", "bool",
        "Is the interaction between {a} and {b} instant or continuous "
        "while touching? 0=instant 1=continuous",
    ),
]


async def evaluate_pair(
    bp_a: GameObjectBlueprint,
    bp_b: GameObjectBlueprint,
    cache: CacheStore,
    scene: SceneCache,
) -> PairwiseResult:
    """Full pairwise evaluation: 6 parallel 1-token calls.

    Checks scene cache -> persistent cache -> LLM eval.
    A/B always in lexicographic order by name.
    """
    # Enforce sorted order
    if normalize_name(bp_a.name) > normalize_name(bp_b.name):
        bp_a, bp_b = bp_b, bp_a

    name_a, name_b = bp_a.name, bp_b.name

    # 1. Scene cache (hot path, O(1))
    cached = scene.get_pairwise(name_a, name_b)
    if cached is not None:
        logger.debug("pairwise_scene_cache_hit", pair=f"{name_a}::{name_b}")
        return cached

    # 2. Persistent cache
    if settings.creation_cache_enabled:
        db_cached = await cache.get_pairwise(name_a, name_b)
        if db_cached is not None:
            logger.debug("pairwise_cache_hit", pair=f"{name_a}::{name_b}")
            result = PairwiseResult.from_dict(db_cached)
            scene.put_pairwise(name_a, name_b, result)
            return result

    # 3. LLM evaluation: 6 parallel calls
    a_desc, b_desc = _obj_summary(bp_a), _obj_summary(bp_b)
    fmt = {"a": name_a, "b": name_b, "a_desc": a_desc, "b_desc": b_desc}

    async def _ask(field: str, qtype: str, template: str) -> tuple[str, int | bool]:
        prompt = template.format(**fmt)
        if qtype == "bool":
            return (field, await ask_bool(prompt))
        elif qtype == "state":
            return (field, await ask_int(prompt, 0, 8, 0))
        elif qtype == "signed":
            return (field, await ask_int(prompt, -100, 100, 0))
        else:
            return (field, await ask_int(prompt))

    raw_results = await asyncio.gather(
        *[_ask(f, t, p) for f, t, p in PAIR_QUESTIONS]
    )
    raw = dict(raw_results)

    result = PairwiseResult(
        damage_a=int(raw["damage_a"]),
        damage_b=int(raw["damage_b"]),
        state_change_a=int(raw["state_change_a"]),
        state_change_b=int(raw["state_change_b"]),
        force_b=int(raw["force_b"]),
        continuous=bool(raw["continuous"]),
    )

    # Write through to both caches
    scene.put_pairwise(name_a, name_b, result)
    if settings.creation_cache_enabled:
        await cache.put_pairwise(
            name_a, name_b, result.to_dict(), model_version=settings.llm_model,
            commit=False,
        )

    logger.info(
        "pairwise_eval",
        pair=f"{name_a}::{name_b}",
        damage=f"{result.damage_a}/{result.damage_b}",
        state=f"{result.state_change_a}/{result.state_change_b}",
    )
    return result


# ---- Spawn integration ----


async def spawn_integration(
    new_obj: GameObjectBlueprint,
    scene_objects: list[GameObjectBlueprint],
    cache: CacheStore,
    scene: SceneCache,
) -> dict[str, PairwiseResult]:
    """Run screening + full eval for a newly spawned object.

    Called as a background task during sprite gen (~2-5s window).
    Returns dict of target_name -> PairwiseResult for all evaluated pairs.
    """
    interesting = await screen_pairs(new_obj, scene_objects)
    if not interesting:
        return {}

    bp_by_name = {normalize_name(o.name): o for o in scene_objects}
    evals = []
    names = []
    for name in interesting:
        n = normalize_name(name)
        if n in bp_by_name:
            evals.append(evaluate_pair(new_obj, bp_by_name[n], cache, scene))
            names.append(name)

    evaluated = await asyncio.gather(*evals, return_exceptions=True)
    results: dict[str, PairwiseResult] = {}
    for name, result in zip(names, evaluated, strict=True):
        if isinstance(result, PairwiseResult):
            results[name] = result
        else:
            logger.warning("pairwise_eval_failed", target=name, error=str(result))

    # Batch-commit all pairwise writes at once
    await cache.flush()
    return results
