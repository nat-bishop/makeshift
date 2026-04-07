from __future__ import annotations

import asyncio
from dataclasses import dataclass

import structlog
from pydantic_ai import Agent

from app.creator.llm import build_model
from app.creator.questions import parse_int

logger = structlog.get_logger()


@dataclass
class CreatureBehavior:
    target_name: str
    movement: int  # 0=approach, 1=flee, 2=orbit, 3=ignore
    strength: int  # 0-100
    action: int  # 0=nothing, 1=damage, 2=heal, 3=add state, 4=remove state, 5=destroy, 6=take
    action_param: int  # damage/heal amount or state_id


SCENE_PREFIX = "Scene: [{scene_list}].\n"

MOVEMENT_PROMPT = (
    SCENE_PREFIX + "{creature} sees [{target}]."
    " 0=approach 1=flee 2=orbit 3=ignore. Reply with just the number."
)
STRENGTH_PROMPT = (
    SCENE_PREFIX + "How strongly does {creature} react to [{target}]?"
    " 0=ignores, 25=mild interest, 50=moderate, 75=strong drive, 100=absolute priority."
    " Reply with just the number."
)
ACTION_PROMPT = (
    SCENE_PREFIX + "{creature} is {movement_desc} [{target}] and {motivation}."
    " On arrival: 0=nothing 1=damage 2=heal 3=add state 4=remove state 5=destroy 6=take."
    " Reply with just the number."
)
PARAM_DAMAGE_PROMPT = (
    "{creature} will damage [{target}]. How much damage? 0-100. Reply with just the number."
)
PARAM_HEAL_PROMPT = (
    "{creature} will heal [{target}]. How much healing? 0-100. Reply with just the number."
)
PARAM_STATE_PROMPT = (
    "{creature} will {action} a state on [{target}]. Which?"
    " 1=on_fire 2=frozen 3=wet 4=electrified 5=poisoned 6=corroded 7=molten."
    " Reply with just the number."
)

MOVEMENT_DESCS = {0: "APPROACHING", 1: "FLEEING", 2: "ORBITING"}
MOTIVATIONS = {0: "wants to interact with it", 2: "is cautious about it"}


async def evaluate_creature_behaviors(
    creature_bp: dict,
    scene_bps: list[dict],
    scene_inventory: list[str],
) -> list[CreatureBehavior]:
    """3-stage sequential evaluation for one creature against all scene objects."""
    creature_name = creature_bp["name"]
    scene_str = ", ".join(scene_inventory)

    # Stage 1+1b: movement + strength (all pairs, parallel)
    async def _ask_movement(target_name: str) -> tuple[str, int]:
        prompt = MOVEMENT_PROMPT.format(
            scene_list=scene_str, creature=creature_name, target=target_name
        )
        agent = Agent(
            build_model(),
            output_type=str,
            model_settings={"max_tokens": 1, "temperature": 0.3},
        )
        r = await agent.run(prompt)
        val = parse_int(r.output)
        return (target_name, val if val in (0, 1, 2, 3) else 3)

    async def _ask_strength(target_name: str) -> tuple[str, int]:
        prompt = STRENGTH_PROMPT.format(
            scene_list=scene_str, creature=creature_name, target=target_name
        )
        agent = Agent(
            build_model(),
            output_type=str,
            model_settings={"max_tokens": 1, "temperature": 0.3},
        )
        r = await agent.run(prompt)
        return (target_name, parse_int(r.output))

    movement_results = await asyncio.gather(
        *[_ask_movement(bp["name"]) for bp in scene_bps], return_exceptions=True
    )
    strength_results = await asyncio.gather(
        *[_ask_strength(bp["name"]) for bp in scene_bps], return_exceptions=True
    )

    # Assemble stage 1 results
    behaviors = []
    stage2_pairs: list[tuple[int, CreatureBehavior]] = []
    for i, bp in enumerate(scene_bps):
        mv = movement_results[i][1] if not isinstance(movement_results[i], BaseException) else 3
        st = strength_results[i][1] if not isinstance(strength_results[i], BaseException) else 0
        cb = CreatureBehavior(
            target_name=bp["name"], movement=mv, strength=st, action=0, action_param=0
        )
        behaviors.append(cb)
        if mv in (0, 2):  # approach or orbit -> needs action evaluation
            stage2_pairs.append((i, cb))

    # Stage 2: action (approaching/orbiting pairs only, parallel)
    async def _ask_action(idx: int, cb: CreatureBehavior) -> tuple[int, int]:
        desc = MOVEMENT_DESCS.get(cb.movement, "APPROACHING")
        mot = MOTIVATIONS.get(cb.movement, "wants to interact with it")
        prompt = ACTION_PROMPT.format(
            scene_list=scene_str,
            creature=creature_name,
            target=cb.target_name,
            movement_desc=desc,
            motivation=mot,
        )
        agent = Agent(
            build_model(),
            output_type=str,
            model_settings={"max_tokens": 1, "temperature": 0.3},
        )
        r = await agent.run(prompt)
        return (idx, parse_int(r.output))

    if stage2_pairs:
        action_results = await asyncio.gather(
            *[_ask_action(idx, cb) for idx, cb in stage2_pairs], return_exceptions=True
        )
        for r in action_results:
            if not isinstance(r, BaseException):
                idx, action = r
                behaviors[idx].action = action

    # Stage 3: parameters (actions needing them, parallel)
    stage3_pairs = [(i, b) for i, b in enumerate(behaviors) if b.action in (1, 2, 3, 4)]

    async def _ask_param(idx: int, cb: CreatureBehavior) -> tuple[int, int]:
        if cb.action == 1:
            prompt = PARAM_DAMAGE_PROMPT.format(creature=creature_name, target=cb.target_name)
        elif cb.action == 2:
            prompt = PARAM_HEAL_PROMPT.format(creature=creature_name, target=cb.target_name)
        else:
            act = "add" if cb.action == 3 else "remove"
            prompt = PARAM_STATE_PROMPT.format(
                creature=creature_name, target=cb.target_name, action=act
            )
        agent = Agent(
            build_model(),
            output_type=str,
            model_settings={"max_tokens": 2, "temperature": 0.3},
        )
        r = await agent.run(prompt)
        return (idx, parse_int(r.output))

    if stage3_pairs:
        param_results = await asyncio.gather(
            *[_ask_param(idx, cb) for idx, cb in stage3_pairs], return_exceptions=True
        )
        for r in param_results:
            if not isinstance(r, BaseException):
                idx, param = r
                behaviors[idx].action_param = param

    # Filter out ignore (movement=3) from returned behaviors
    return [b for b in behaviors if b.movement != 3]
