"""Unified object behavior: per-pair staged evaluation with composite actions.

Two sequential stages, each parallel internally:
  Stage 1: movement (0-2) + priority (0-3) — all subject x target pairs
  Stage 2: composite action pipeline — pairs where movement=approach OR priority>0
    Call 1: action (nothing/damage/heal/consume/push)
    Conditional follow-ups (parallel):
      - amount (damage/heal/push)
      - state_modifier + state_id (damage/heal/consume)
      - force_modifier (damage only)

State-aware: Stage 1 prompts include target's current active states,
so re-evaluation after state_changed produces meaningful results.

Scene-local, not persisted to cache.db.
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

import structlog

from app.cache.scene import BehaviorCache, BehaviorEntry
from app.creator.llm import ask_text
from app.creator.question_graph import run_questions
from app.models.blueprint import AFFORDANCE_LABELS, DURABILITY_NAMES, SURFACE_NAMES
from app.models.state import STATE_NAMES
from app.prompts.behavior import (
    ACTION_QUESTION,
    AMOUNT_QUESTION,
    FORCE_MODIFIER_QUESTION,
    STAGE1_INACTIVE_QUESTIONS,
    STAGE1_QUESTIONS,
    STATE_ACTION_QUESTION,
    STATE_ID_QUESTION,
    screen_pairs_prompt,
)

if TYPE_CHECKING:
    from app.models.blueprint import GameObjectBlueprint

logger = structlog.get_logger()


# Priority level → utility weight mapping (exported for client-side mirroring)
PRIORITY_WEIGHTS: dict[int, float] = {0: 0.0, 1: 25.0, 2: 60.0, 3: 100.0}


# ---------------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------------


def _obj_summary(bp: GameObjectBlueprint) -> str:
    """Compact object summary for screening prompts."""
    parts = [f"{bp.physics.mass_kg}kg", f"{bp.physics.height_cm}cm"]
    durability_name = DURABILITY_NAMES.get(bp.durability, "normal")
    parts.append(durability_name)
    parts.append(SURFACE_NAMES.get(bp.physics.surface, "normal-surface"))
    if bp.active:
        parts.append("active")
    return f"{bp.name} ({', '.join(parts)})"


def _target_context(bp: GameObjectBlueprint) -> str:
    """Compact target description for behavior prompts."""
    labels: list[str] = []
    if bp.active:
        labels.append("active")
    aff_label = AFFORDANCE_LABELS.get(bp.affordance)
    if aff_label:
        labels.append(aff_label)
    if labels:
        return f"{bp.name} ({', '.join(labels)})"
    return bp.name


def _state_context(active_states: list[int] | None) -> str:
    """Build state context string for behavioral prompts."""
    if not active_states:
        return ""
    names = [STATE_NAMES[s] for s in active_states if s in STATE_NAMES]
    if not names:
        return ""
    return f"[currently: {', '.join(names)}] "


_ACTION_VERBS: dict[int, str] = {1: "attack", 2: "heal", 3: "consume", 4: "push"}


# ---------------------------------------------------------------------------
# Screening
# ---------------------------------------------------------------------------


async def screen_pairs(
    new_obj: GameObjectBlueprint,
    scene_objects: list[GameObjectBlueprint],
) -> list[str]:
    """Bidirectional screening: which scene objects have interesting interactions
    with new_obj (in either direction)?

    Returns list of object names worth evaluating.
    On parse failure, returns ALL names (conservative fallback).
    """
    if not scene_objects:
        return []

    numbered = "\n".join(f"{i + 1}. {_obj_summary(o)}" for i, o in enumerate(scene_objects))
    prompt = screen_pairs_prompt(_obj_summary(new_obj), numbered, new_obj.name)

    try:
        raw = await ask_text(prompt, max_tokens=30, default="none")
        if "none" in raw.lower():
            logger.info(
                "screen_result",
                subject=new_obj.name,
                selected=[],
                candidates=[o.name for o in scene_objects],
                reason="llm_none",
            )
            return []

        nums = [int(x) for x in re.findall(r"\d+", raw)]
        valid = [scene_objects[n - 1].name for n in nums if 1 <= n <= len(scene_objects)]
        if not valid:
            logger.warning("screen_no_valid_indices", subject=new_obj.name, raw=raw)
            return [o.name for o in scene_objects]
        logger.info(
            "screen_result",
            subject=new_obj.name,
            selected=valid,
            candidates=[o.name for o in scene_objects],
        )
        return valid
    except Exception:
        logger.warning("screen_failed", subject=new_obj.name, exc_info=True)
        return [o.name for o in scene_objects]


# ---------------------------------------------------------------------------
# Stage 2: composite action pipeline (per pair)
# ---------------------------------------------------------------------------


_MOVEMENT_LABELS: dict[int, str] = {0: "approach", 1: "flee", 2: "ignore"}


def _subject_states_ctx(subject: GameObjectBlueprint) -> str:
    """Render subject's initial_states as a short phrase for state-choice prompts."""
    names = [STATE_NAMES[s] for s in subject.initial_states if s in STATE_NAMES]
    if not names:
        return ""
    return f" Subject currently embodies: {', '.join(names)}."


async def _evaluate_pair_action(
    subject: GameObjectBlueprint,
    target_name: str,
    target_bp: GameObjectBlueprint,
    movement: int,
    priority: int,
) -> dict[str, int]:
    """Run the composite action pipeline for one pair.

    Call 1: primary action (conditioned on Stage 1 movement + priority)
    Then conditional parallel follow-ups based on action type.
    STATE_ACTION and STATE_ID see the subject's own initial_states so
    element-based reactions (fire→burn, ice→freeze) stay coherent.
    Returns dict with keys: action, amount, state_action, state_id, force.
    """
    ctx = {
        "subject": subject.name,
        "target": _target_context(target_bp),
        "movement_label": _MOVEMENT_LABELS.get(movement, "ignore"),
        "priority": priority,
        "subject_states": _subject_states_ctx(subject),
    }

    # Call 1: primary action
    r1 = await run_questions([ACTION_QUESTION], ctx)
    action = int(r1.get("action", 0))

    if action == 0:  # nothing
        return {"action": 0, "amount": 0, "state_action": 0, "state_id": 0, "force": 0}

    action_verb = _ACTION_VERBS.get(action, "affect")
    action_ctx = {**ctx, "action_verb": action_verb}

    # Build parallel follow-up tasks
    tasks: list[tuple[str, asyncio.Task[dict]]] = []

    # Amount: fires for damage(1), heal(2), push(4). NOT consume(3).
    if action in (1, 2, 4):
        amount_fut = asyncio.ensure_future(run_questions([AMOUNT_QUESTION], action_ctx))
        tasks.append(("amount", amount_fut))

    # State modifier: fires for damage(1), heal(2), consume(3). NOT push(4).
    if action in (1, 2, 3):
        tasks.append(
            (
                "state",
                asyncio.ensure_future(run_questions([STATE_ACTION_QUESTION], action_ctx)),
            )
        )

    # Force modifier: fires for damage(1) ONLY.
    if action == 1:
        tasks.append(
            (
                "force",
                asyncio.ensure_future(run_questions([FORCE_MODIFIER_QUESTION], action_ctx)),
            )
        )

    # Await all parallel follow-ups
    results_map: dict[str, dict] = {}
    if tasks:
        raw_results = await asyncio.gather(*[t for _, t in tasks], return_exceptions=True)
        for (label, _), result in zip(tasks, raw_results, strict=True):
            if not isinstance(result, BaseException):
                results_map[label] = result
            else:
                logger.warning("action_followup_failed", label=label, error=str(result))

    amount = int(results_map.get("amount", {}).get("amount", 0))
    state_action = int(results_map.get("state", {}).get("state_action", 0))
    force = int(results_map.get("force", {}).get("force", 0))

    # Sequential: state_id if state_action != 0
    state_id = 0
    if state_action != 0:
        state_verb = "apply" if state_action == 1 else "remove"
        sid_result = await run_questions(
            [STATE_ID_QUESTION],
            {**action_ctx, "state_verb": state_verb},
        )
        state_id = int(sid_result.get("state_id", 0))

    return {
        "action": action,
        "amount": amount,
        "state_action": state_action,
        "state_id": state_id,
        "force": force,
    }


# ---------------------------------------------------------------------------
# Main evaluation
# ---------------------------------------------------------------------------


def _collect_results(
    raw: list[dict[str, int | float | bool | str] | BaseException],
    target_names: list[str],
    event_name: str,
    subject_name: str,
) -> dict[str, dict[str, int | float | bool | str]]:
    """Zip gather results with target names, logging exceptions."""
    results: dict[str, dict[str, int | float | bool | str]] = {}
    for name, r in zip(target_names, raw, strict=True):
        if isinstance(r, BaseException):
            logger.warning(event_name, subject=subject_name, target=name, error=str(r))
        else:
            results[name] = r
    return results


async def evaluate_behaviors(
    subject: GameObjectBlueprint,
    targets: list[GameObjectBlueprint],
    scene: BehaviorCache,
    target_states: dict[str, list[int]] | None = None,
) -> dict[str, BehaviorEntry]:
    """Evaluate subject's behavior toward all targets.

    Args:
        subject: The object whose behavior we're evaluating.
        targets: List of target blueprints.
        scene: BehaviorCache for storing results.
        target_states: Optional dict of target_name -> active state IDs.
            Used during state_changed re-evaluation.

    Returns target_name -> BehaviorEntry.
    """
    if not targets:
        return {}

    behaviors: dict[str, BehaviorEntry] = {}
    bp_by_name: dict[str, GameObjectBlueprint] = {t.name: t for t in targets}
    target_states = target_states or {}

    # --- Stage 1: priority always; movement only for active subjects ---

    # Inactive subjects can't move (MoveSpeed=0 in Godot ObjectBehavior.cs), so
    # skip the movement question and hard-code movement=2 (ignore). Saves one
    # LLM call per pair and prevents the "approach with no movement" contradiction.
    stage1_questions = STAGE1_QUESTIONS if subject.active else STAGE1_INACTIVE_QUESTIONS

    target_names_s1 = [t.name for t in targets]
    stage1_raw = await asyncio.gather(
        *[
            run_questions(
                stage1_questions,
                {
                    "subject": subject.name,
                    "target": _target_context(t),
                    "state_context": _state_context(target_states.get(t.name)),
                },
            )
            for t in targets
        ],
        return_exceptions=True,
    )
    stage1 = _collect_results(stage1_raw, target_names_s1, "behavior_stage1_failed", subject.name)

    stage1_results: list[tuple[str, int, int]] = []
    for t in targets:
        if t.name in stage1:
            r = stage1[t.name]
            movement = int(r.get("movement", 2)) if subject.active else 2
            stage1_results.append((t.name, movement, int(r.get("priority", 0))))
        else:
            stage1_results.append((t.name, 2, 0))  # ignore, no priority

    # Filter: approach (0) OR priority > 0 (captures reactive objects)
    active_pairs = [(name, mv, pri) for name, mv, pri in stage1_results if mv == 0 or pri > 0]

    # --- Stage 2: composite action pipeline (parallel across pairs) ---

    stage2: dict[str, dict[str, int]] = {}
    if active_pairs:
        pair_names = [name for name, _, _ in active_pairs]
        stage2_raw = await asyncio.gather(
            *[
                _evaluate_pair_action(subject, name, bp_by_name[name], mv, pri)
                for name, mv, pri in active_pairs
            ],
            return_exceptions=True,
        )
        for name, result in zip(pair_names, stage2_raw, strict=True):
            if isinstance(result, BaseException):
                logger.warning(
                    "behavior_stage2_failed", subject=subject.name, target=name, error=str(result)
                )
            else:
                stage2[name] = result

    # --- Assemble all behaviors ---
    for name, movement, priority in stage1_results:
        s2 = stage2.get(name, {})
        behavior = BehaviorEntry(
            movement=movement,
            priority=priority,
            action=int(s2.get("action", 0)),
            amount=int(s2.get("amount", 0)),
            state_action=int(s2.get("state_action", 0)),
            state_id=int(s2.get("state_id", 0)),
            force=int(s2.get("force", 0)),
        )
        behaviors[name] = behavior
        scene.put_behavior(subject.name, name, behavior)

    pair_breakdown = [
        {
            "target": name,
            "movement": b.movement,
            "priority": b.priority,
            "action": b.action,
            "amount": b.amount,
            "state_action": b.state_action,
            "state_id": b.state_id,
            "force": b.force,
        }
        for name, b in behaviors.items()
    ]
    logger.info(
        "behavior_eval",
        subject=subject.name,
        pairs=len(stage1_results),
        active=len(active_pairs),
        entries=pair_breakdown,
    )
    return behaviors


def compute_utility(
    priority: int, distance: float, perception_range: float, is_flee: bool
) -> float:
    """Priority resolution: highest utility wins per frame.

    Maps priority (0-3) to weight via PRIORITY_WEIGHTS, then applies
    distance falloff: utility = weight / (1 + distance / perception_range).
    Flee gets 1.5x multiplier (survival bias).
    """
    weight = PRIORITY_WEIGHTS.get(priority, 0.0)
    base = weight / (1.0 + distance / max(perception_range, 1.0))
    return base * 1.5 if is_flee else base
