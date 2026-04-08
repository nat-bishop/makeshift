"""Creature behavior: per-pair staged evaluation.

Three sequential stages, each parallel internally:
  Stage 1: movement (0-3) + strength (0-100) — all creature x object pairs
  Stage 2: action (0-6) — approach/orbit pairs only (filtered)
  Stage 3: params — actions needing them (filtered)

Scene-local, not persisted to cache.db (prompts include scene inventory
for context-aware decisions).
"""

from __future__ import annotations

import asyncio

import structlog

from app.cache.scene import CreatureBehavior, SceneCache
from app.creator.llm import ask_int
from app.models.blueprint import GameObjectBlueprint
from app.models.state import STATE_LIST_PROMPT

logger = structlog.get_logger()

# Actions that need a follow-up parameter call
ACTIONS_NEEDING_PARAMS = {1, 2, 3, 4}  # damage, heal, add_state, remove_state

# Movement motivation templates for seeding stage 2
MOVEMENT_MOTIVATION = {0: "wants to interact with", 2: "is cautious about"}

# ---- Prompt templates ----

STAGE1_MOVEMENT = (
    "Scene: [{scene_list}].\n"
    "{creature} sees {target}. How does it react?\n"
    "0=approach 1=flee 2=orbit 3=ignore"
)

STAGE1_STRENGTH = (
    "Scene: [{scene_list}].\n"
    "How strongly does {creature} react to {target}?\n"
    "0=ignores 25=mild interest 50=moderate 75=strong drive 100=absolute priority"
)

STAGE2_ACTION = (
    "{creature} is {movement_verb} {target} and {motivation} it.\n"
    "On arrival: 0=nothing 1=damage 2=heal 3=add state 4=remove state 5=destroy 6=take"
)

STAGE3_AMOUNT = "{creature} will {action_verb} {target}. How much (0-100)?"

STAGE3_STATE = (
    "{creature} will {action_verb} a state on {target}. Which?\n"
    + STATE_LIST_PROMPT
)


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

    async def _stage1(target: GameObjectBlueprint) -> tuple[str, int, int]:
        movement, strength = await asyncio.gather(
            ask_int(
                STAGE1_MOVEMENT.format(
                    scene_list=scene_list,
                    creature=creature.name,
                    target=target.name,
                ),
                0, 3, 3,
            ),
            ask_int(
                STAGE1_STRENGTH.format(
                    scene_list=scene_list,
                    creature=creature.name,
                    target=target.name,
                ),
                0, 100, 0,
            ),
        )
        return (target.name, movement, strength)

    stage1_results = await asyncio.gather(*[_stage1(t) for t in targets])

    # Filter: only approach (0) and orbit (2) continue to stage 2
    approach_orbit = [
        (name, mv, st) for name, mv, st in stage1_results if mv in (0, 2)
    ]

    # --- Stage 2: action (parallel, filtered pairs only) ---

    async def _stage2(name: str, movement: int) -> tuple[str, int]:
        mv_verb = "APPROACHING" if movement == 0 else "ORBITING"
        motivation = MOVEMENT_MOTIVATION[movement]
        action = await ask_int(
            STAGE2_ACTION.format(
                creature=creature.name,
                movement_verb=mv_verb,
                target=name,
                motivation=motivation,
            ),
            0, 6, 0,
        )
        return (name, action)

    stage2: dict[str, int] = {}
    if approach_orbit:
        s2_results = await asyncio.gather(
            *[_stage2(name, mv) for name, mv, _ in approach_orbit]
        )
        stage2 = dict(s2_results)

    # --- Stage 3: params (parallel, actions needing them) ---

    async def _stage3(name: str, action: int) -> tuple[str, int]:
        if action in (1, 2):  # damage/heal -> amount
            action_verb = "damage" if action == 1 else "heal"
            amount = await ask_int(
                STAGE3_AMOUNT.format(
                    creature=creature.name, action_verb=action_verb, target=name
                ),
                0, 100, 20,
            )
            return (name, amount)
        elif action in (3, 4):  # add/remove state -> state id
            action_verb = "add" if action == 3 else "remove"
            state_id = await ask_int(
                STAGE3_STATE.format(
                    creature=creature.name, action_verb=action_verb, target=name
                ),
                1, 7, 1,
            )
            return (name, state_id)
        return (name, 0)

    needs_params = [
        (n, a) for n, a in stage2.items() if a in ACTIONS_NEEDING_PARAMS
    ]
    stage3: dict[str, int] = {}
    if needs_params:
        s3_results = await asyncio.gather(
            *[_stage3(n, a) for n, a in needs_params]
        )
        stage3 = dict(s3_results)

    # --- Assemble all behaviors ---
    for name, movement, strength in stage1_results:
        action = stage2.get(name, 0)
        param = stage3.get(name, 0)
        behavior = CreatureBehavior(
            movement=movement, strength=strength, action=action, param=param
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
    strength: int, distance: float, perception_range: float, is_flee: bool
) -> float:
    """Priority resolution: highest utility wins per frame.

    utility = strength / (1 + distance / perception_range)
    Flee gets 1.5x multiplier (survival bias).
    """
    base = strength / (1.0 + distance / max(perception_range, 1.0))
    return base * 1.5 if is_flee else base
