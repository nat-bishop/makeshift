"""Creature behavior: per-pair staged evaluation with state context.

Three sequential stages, each parallel internally via run_questions():
  Stage 1: movement (0-2) + priority (0-3) — all creature x object pairs
  Stage 2: action (0-5) — approach pairs only (filtered)
  Stage 3: params — actions needing them (filtered)

State-aware: Phase 1 prompts include target's current active states,
so re-evaluation after state_changed produces meaningful results.

Scene-local, not persisted to cache.db.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

from app.cache.scene import BehaviorCache, BehaviorEntry
from app.creator.question_graph import Question, run_questions
from app.models.state import STATE_NAMES

if TYPE_CHECKING:
    from app.models.blueprint import GameObjectBlueprint

logger = structlog.get_logger()

_AFFORDANCE_LABELS: dict[int, str] = {0: "carryable", 1: "mountable", 2: "climbable"}


def _target_context(bp: GameObjectBlueprint) -> str:
    """Compact target description for creature prompts."""
    labels: list[str] = []
    if bp.autonomous:
        labels.append("creature")
    aff_label = _AFFORDANCE_LABELS.get(bp.affordance)
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


# Actions that need a follow-up parameter call
ACTIONS_NEEDING_PARAMS = {1, 2, 3, 4}  # damage, heal, add_state, remove_state

# Priority level → utility weight mapping (exported for client-side mirroring)
PRIORITY_WEIGHTS: dict[int, float] = {0: 0.0, 1: 25.0, 2: 60.0, 3: 100.0}

# ---- Question definitions per stage ----

STAGE1_QUESTIONS: list[Question] = [
    Question(
        "movement",
        "Scene: [{scene_list}]. {creature} sees {target}. {state_context}",
        "choice",
        default="ignore",
        instructions=(
            "How does this creature react to the target? "
            "approach=move toward it, flee=run away, ignore=no reaction. "
            "Return one word."
        ),
        choices=("approach", "flee", "ignore"),
        choice_map=(("approach", 0), ("flee", 1), ("ignore", 2)),
    ),
    Question(
        "priority",
        "Scene: [{scene_list}]. How strongly does {creature} react to {target}? {state_context}",
        "choice",
        default="ignore",
        instructions=(
            "How strongly does this creature react? "
            "ignore=no interest, mild=slight interest, moderate=clear drive, "
            "driven=high priority. Return one word."
        ),
        choices=("ignore", "mild", "moderate", "driven"),
        choice_map=(("ignore", 0), ("mild", 1), ("moderate", 2), ("driven", 3)),
    ),
]

STAGE2_QUESTION = Question(
    "action",
    "{creature} is approaching {target} and wants to interact with it.",
    "choice",
    default="nothing",
    instructions=(
        "What does this creature do to the target? "
        "nothing=no action, attack=damage/harm, heal=repair/help, "
        "ignite=add a state, cleanse=remove a state, consume=eat/absorb. "
        "Return one word."
    ),
    choices=("nothing", "attack", "heal", "ignite", "cleanse", "consume"),
    choice_map=(
        ("nothing", 0),
        ("attack", 1),
        ("heal", 2),
        ("ignite", 3),
        ("cleanse", 4),
        ("consume", 5),
    ),
)

STAGE3_AMOUNT = Question(
    "amount",
    "{creature} will {action_verb} {target}.",
    "int",
    0,
    100,
    20,
    instructions=(
        "How intense is this action? 0-100. "
        "5=scratch, 15=light, 30=moderate, 50=serious, 75=devastating, 100=lethal. "
        "Return only an integer."
    ),
)

STAGE3_STATE = Question(
    "state_id",
    "{creature} will {action_verb} a state on {target}.",
    "choice",
    default="burn",
    instructions=(
        "Which elemental state does this creature apply or remove? "
        "burn=fire/heat, freeze=ice/cold, wet=water/liquid, zap=electricity. "
        "Return one word."
    ),
    choices=("burn", "freeze", "wet", "zap"),
    choice_map=(("burn", 1), ("freeze", 2), ("wet", 3), ("zap", 4)),
)


def _collect_results(
    raw: list[dict[str, int | float | bool | str] | BaseException],
    target_names: list[str],
    event_name: str,
    creature_name: str,
) -> dict[str, dict[str, int | float | bool | str]]:
    """Zip gather results with target names, logging exceptions."""
    results: dict[str, dict[str, int | float | bool | str]] = {}
    for name, r in zip(target_names, raw, strict=True):
        if isinstance(r, BaseException):
            logger.warning(event_name, creature=creature_name, target=name, error=str(r))
        else:
            results[name] = r
    return results


async def evaluate_creature_behaviors(
    creature: GameObjectBlueprint,
    targets: list[GameObjectBlueprint],
    scene_inventory: list[str],
    scene: BehaviorCache,
    target_states: dict[str, list[int]] | None = None,
) -> dict[str, BehaviorEntry]:
    """Evaluate creature behavior toward all targets.

    Args:
        creature: The autonomous creature blueprint.
        targets: List of target blueprints.
        scene_inventory: Names of all objects in the scene.
        scene: BehaviorCache for storing results.
        target_states: Optional dict of target_name -> active state IDs.
            Used during state_changed re-evaluation to include runtime state
            in behavioral prompts.

    Returns target_name -> BehaviorEntry.
    Three sequential stages with filtering between each.
    """
    if not creature.autonomous or not targets:
        return {}

    scene_list = ", ".join(scene_inventory)
    behaviors: dict[str, BehaviorEntry] = {}
    bp_by_name: dict[str, GameObjectBlueprint] = {t.name: t for t in targets}
    target_states = target_states or {}

    # --- Stage 1: movement + priority (parallel, all pairs) ---

    target_names_s1 = [t.name for t in targets]
    stage1_raw = await asyncio.gather(
        *[
            run_questions(
                STAGE1_QUESTIONS,
                {
                    "scene_list": scene_list,
                    "creature": creature.name,
                    "target": _target_context(t),
                    "state_context": _state_context(target_states.get(t.name)),
                },
            )
            for t in targets
        ],
        return_exceptions=True,
    )
    stage1 = _collect_results(stage1_raw, target_names_s1, "creature_stage1_failed", creature.name)

    # Build stage1_results with defaults for failures
    stage1_results: list[tuple[str, int, int]] = []
    for t in targets:
        if t.name in stage1:
            r = stage1[t.name]
            stage1_results.append((t.name, int(r.get("movement", 2)), int(r.get("priority", 0))))
        else:
            stage1_results.append((t.name, 2, 0))  # ignore, no priority

    # Filter: only approach (0) continues to stage 2
    approaching = [(name, mv, st) for name, mv, st in stage1_results if mv == 0]

    # --- Stage 2: action (parallel, filtered pairs only) ---

    stage2: dict[str, int] = {}
    if approaching:
        target_names_s2 = [name for name, _, _ in approaching]
        stage2_raw = await asyncio.gather(
            *[
                run_questions(
                    [STAGE2_QUESTION],
                    {
                        "creature": creature.name,
                        "target": _target_context(bp_by_name[name]),
                    },
                )
                for name, _, _ in approaching
            ],
            return_exceptions=True,
        )
        s2_results = _collect_results(
            stage2_raw, target_names_s2, "creature_stage2_failed", creature.name
        )
        stage2 = {name: int(r.get("action", 0)) for name, r in s2_results.items()}

    # --- Stage 3: params (parallel, actions needing them) ---

    needs_params = [(n, a) for n, a in stage2.items() if a in ACTIONS_NEEDING_PARAMS]
    stage3: dict[str, dict[str, int | float | bool | str]] = {}
    if needs_params:
        target_names_s3 = [n for n, _ in needs_params]

        def _s3_question(action: int) -> Question:
            if action in (1, 2):
                return STAGE3_AMOUNT
            return STAGE3_STATE

        def _s3_context(name: str, action: int) -> dict[str, str]:
            if action in (1, 2):
                action_verb = "damage" if action == 1 else "heal"
            else:
                action_verb = "add" if action == 3 else "remove"
            return {"creature": creature.name, "action_verb": action_verb, "target": name}

        stage3_raw = await asyncio.gather(
            *[run_questions([_s3_question(a)], _s3_context(n, a)) for n, a in needs_params],
            return_exceptions=True,
        )
        s3_results = _collect_results(
            stage3_raw, target_names_s3, "creature_stage3_failed", creature.name
        )
        stage3 = {name: dict(r) for name, r in s3_results.items()}

    # --- Assemble all behaviors ---
    for name, movement, priority in stage1_results:
        action = stage2.get(name, 0)
        s3: dict[str, int | float | bool | str] = stage3.get(name, {})
        behavior = BehaviorEntry(
            movement=movement,
            priority=priority,
            action=action,
            amount=int(s3.get("amount", 0)),
            state_id=int(s3.get("state_id", 0)),
        )
        behaviors[name] = behavior
        scene.put_behavior(creature.name, name, behavior)

    logger.info(
        "creature_eval",
        creature=creature.name,
        pairs=len(stage1_results),
        approaching=len(approaching),
        needs_params=len(needs_params),
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
