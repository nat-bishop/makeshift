"""Creature behavior: per-pair staged evaluation.

Three sequential stages, each parallel internally via run_questions():
  Stage 1: movement (0-3) + priority (0-3) — all creature x object pairs
  Stage 2: action (0-6) — approach/orbit pairs only (filtered)
  Stage 3: params — actions needing them (filtered)

Scene-local, not persisted to cache.db (prompts include scene inventory
for context-aware decisions).
"""

from __future__ import annotations

import asyncio

import structlog

from app.cache.scene import CreatureBehavior, SceneCache
from app.creator.question_graph import Question, run_questions
from app.models.blueprint import GameObjectBlueprint
from app.models.state import STATE_LIST_PROMPT

logger = structlog.get_logger()

# Actions that need a follow-up parameter call
ACTIONS_NEEDING_PARAMS = {1, 2, 3, 4}  # damage, heal, add_state, remove_state

# Movement motivation templates for seeding stage 2
MOVEMENT_MOTIVATION = {0: "wants to interact with", 2: "is cautious about"}

# ---- Question definitions per stage ----

# Priority level → utility weight mapping
PRIORITY_WEIGHTS: dict[int, float] = {0: 0.0, 1: 25.0, 2: 60.0, 3: 100.0}

STAGE1_QUESTIONS: list[Question] = [
    Question(
        "movement",
        "Scene: [{scene_list}].\n"
        "{creature} sees {target}. How does it react?\n"
        "0=approach 1=flee 2=orbit 3=ignore",
        "int",
        0,
        3,
        3,
    ),
    Question(
        "priority",
        "Scene: [{scene_list}].\n"
        "How strongly does {creature} react to {target}?\n"
        "0=ignore 1=mild interest 2=moderate drive 3=high priority",
        "int",
        0,
        3,
        0,
    ),
]

STAGE2_QUESTION = Question(
    "action",
    "{creature} is {movement_verb} {target} and {motivation} it.\n"
    "What does {creature} do to {target}?\n"
    "0=nothing 1=damage/attack 2=heal/repair/extinguish 3=add state "
    "4=remove state 5=destroy 6=take/eat/consume",
    "int",
    0,
    6,
    0,
)

STAGE3_AMOUNT = Question(
    "amount",
    "{creature} will {action_verb} {target}. How much (0-100)?\n"
    "5=scratch 15=light 30=moderate 50=serious 75=devastating 100=lethal",
    "int",
    0,
    100,
    20,
)

STAGE3_STATE = Question(
    "state_id",
    "{creature} will {action_verb} a state on {target}. Which?\n" + STATE_LIST_PROMPT,
    "int",
    1,
    4,
    1,
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
    scene: SceneCache,
) -> dict[str, CreatureBehavior]:
    """Evaluate creature behavior toward all targets.

    Returns target_name -> CreatureBehavior.
    Three sequential stages with filtering between each.
    """
    if not creature.autonomous or not targets:
        return {}

    scene_list = ", ".join(scene_inventory)
    behaviors: dict[str, CreatureBehavior] = {}

    # --- Stage 1: movement + strength (parallel, all pairs) ---

    target_names_s1 = [t.name for t in targets]
    stage1_raw = await asyncio.gather(
        *[
            run_questions(
                STAGE1_QUESTIONS,
                {"scene_list": scene_list, "creature": creature.name, "target": t.name},
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
            stage1_results.append((t.name, int(r.get("movement", 3)), int(r.get("priority", 0))))
        else:
            stage1_results.append((t.name, 3, 0))  # ignore, no priority

    # Filter: only approach (0) and orbit (2) continue to stage 2
    approach_orbit = [(name, mv, st) for name, mv, st in stage1_results if mv in (0, 2)]

    # --- Stage 2: action (parallel, filtered pairs only) ---

    stage2: dict[str, int] = {}
    if approach_orbit:
        target_names_s2 = [name for name, _, _ in approach_orbit]
        stage2_raw = await asyncio.gather(
            *[
                run_questions(
                    [STAGE2_QUESTION],
                    {
                        "creature": creature.name,
                        "movement_verb": "APPROACHING" if mv == 0 else "ORBITING",
                        "target": name,
                        "motivation": MOVEMENT_MOTIVATION[mv],
                    },
                )
                for name, mv, _ in approach_orbit
            ],
            return_exceptions=True,
        )
        s2_results = _collect_results(
            stage2_raw, target_names_s2, "creature_stage2_failed", creature.name
        )
        stage2 = {name: int(r.get("action", 0)) for name, r in s2_results.items()}

    # --- Stage 3: params (parallel, actions needing them) ---

    needs_params = [(n, a) for n, a in stage2.items() if a in ACTIONS_NEEDING_PARAMS]
    stage3: dict[str, int] = {}
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
        s3 = stage3.get(name, {})
        behavior = CreatureBehavior(
            movement=movement,
            priority=priority,
            action=action,
            amount=int(s3.get("amount", 0)),
            state_id=int(s3.get("state_id", 0)),
        )
        behaviors[name] = behavior
        scene.put_creature(creature.name, name, behavior)

    logger.info(
        "creature_eval",
        creature=creature.name,
        pairs=len(stage1_results),
        approach_orbit=len(approach_orbit),
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
