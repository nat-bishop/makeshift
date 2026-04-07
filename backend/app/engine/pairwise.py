from __future__ import annotations

import asyncio

import structlog
from pydantic_ai import Agent

from app.cache.manager import CacheManager
from app.creator.llm import build_model
from app.creator.questions import parse_int
from app.models.pairwise import PairwiseResult
from app.ws.handler import send_pairwise_ready

logger = structlog.get_logger()


def _obj_summary(bp: dict) -> str:
    parts = [f"{bp['name']}: {bp['mass_kg']}kg, armor {bp['armor']}, hp {bp['hp']}"]
    if bp.get("has_field"):
        parts.append(f"field {bp['field_range_cm']}cm")
    if bp.get("states"):
        parts.append(f"[{', '.join(bp['states'])}]")
    return ", ".join(parts)


SCREENING_PROMPT = """New object: {new_summary}.
Scene objects:
{scene_list}
Which scene objects would interact interestingly with {new_name}? List their numbers separated \
by commas. If none, reply "none"."""

PAIRWISE_QUESTIONS = [
    (
        "damage_a",
        "[{a}] collides with [{b}]. Damage to {a_name}? 0-100."
        " Reply with just the number.",
    ),
    (
        "damage_b",
        "[{a}] collides with [{b}]. Damage to {b_name}? 0-100."
        " Reply with just the number.",
    ),
    (
        "state_change_a",
        "[{a}] collides with [{b}]. State change on {a_name}? 0=none, 1=add on_fire,"
        " 2=add frozen, 3=add wet, 4=add electrified, 5=add poisoned, 6=add corroded,"
        " 7=add molten, 8=remove on_fire, 9=remove frozen, 10=remove wet,"
        " 11=remove electrified, 12=remove poisoned, 13=remove corroded, 14=remove molten."
        " Reply with just the number.",
    ),
    (
        "state_change_b",
        "[{a}] collides with [{b}]. State change on {b_name}? 0=none, 1=add on_fire,"
        " 2=add frozen, 3=add wet, 4=add electrified, 5=add poisoned, 6=add corroded,"
        " 7=add molten, 8=remove on_fire, 9=remove frozen, 10=remove wet,"
        " 11=remove electrified, 12=remove poisoned, 13=remove corroded, 14=remove molten."
        " Reply with just the number.",
    ),
    (
        "force_b",
        "[{a}] collides with [{b}]. How much force pushes {b_name}? 0-100 (0=none, 30=nudge,"
        " 70=strong, 100=explosion). Reply with just the number.",
    ),
    (
        "direction_b",
        "[{a}] collides with [{b}]. Does {a_name} push or pull {b_name}?"
        " 0=push 1=pull. Reply with just 0 or 1.",
    ),
    (
        "destroy_a",
        "[{a}] collides with [{b}]. Is {a_name} destroyed?"
        " 0=no 1=yes. Reply with just 0 or 1.",
    ),
    (
        "destroy_b",
        "[{a}] collides with [{b}]. Is {b_name} destroyed?"
        " 0=no 1=yes. Reply with just 0 or 1.",
    ),
    (
        "mode",
        "[{a}] collides with [{b}]. Instant or continuous effect?"
        " 0=instant 1=continuous (ongoing while touching). Reply with just 0 or 1.",
    ),
]


async def screen_pairs(
    new_bp: dict, scene_bps: list[dict], cache: CacheManager
) -> list[int]:
    """Identify interesting pairs via single screening call."""
    if not scene_bps:
        return []
    scene_list = "\n".join(f"{i + 1}. {_obj_summary(bp)}" for i, bp in enumerate(scene_bps))
    prompt = SCREENING_PROMPT.format(
        new_summary=_obj_summary(new_bp),
        new_name=new_bp["name"],
        scene_list=scene_list,
    )
    agent = Agent(
        build_model(),
        output_type=str,
        model_settings={"max_tokens": 30, "temperature": 0.3},
    )
    result = await agent.run(prompt)
    text = result.output.strip()
    if "none" in text.lower():
        return []
    import re

    indices = [int(m) - 1 for m in re.findall(r"\d+", text)]  # 1-indexed -> 0-indexed
    return [i for i in indices if 0 <= i < len(scene_bps)]


async def evaluate_pair(bp_a: dict, bp_b: dict, cache: CacheManager) -> PairwiseResult:
    """Evaluate one pair: 9 parallel 1-token calls. Cache result."""
    pair_key = CacheManager.pair_key(bp_a["name"], bp_b["name"])
    cached = await cache.get("pairwise", pair_key)
    if cached:
        return PairwiseResult(**cached)

    # Lexicographic A/B order
    names = sorted([bp_a["name"].lower(), bp_b["name"].lower()])
    a_bp = bp_a if bp_a["name"].lower() == names[0] else bp_b
    b_bp = bp_b if bp_b["name"].lower() == names[1] else bp_a
    a_sum, b_sum = _obj_summary(a_bp), _obj_summary(b_bp)

    async def _ask_pairwise(key: str, template: str) -> tuple[str, int]:
        prompt = template.format(a=a_sum, b=b_sum, a_name=a_bp["name"], b_name=b_bp["name"])
        agent = Agent(
            build_model(),
            output_type=str,
            model_settings={"max_tokens": 2, "temperature": 0.3},
        )
        r = await agent.run(prompt)
        return (key, parse_int(r.output.strip()))

    results = await asyncio.gather(
        *[_ask_pairwise(k, t) for k, t in PAIRWISE_QUESTIONS],
        return_exceptions=True,
    )
    props = {}
    for i, r in enumerate(results):
        k = PAIRWISE_QUESTIONS[i][0]
        props[k] = r[1] if not isinstance(r, BaseException) else 0

    result = PairwiseResult(
        damage_a=min(100, max(0, props.get("damage_a", 0))),
        damage_b=min(100, max(0, props.get("damage_b", 0))),
        state_change_a=min(14, max(0, props.get("state_change_a", 0))),
        state_change_b=min(14, max(0, props.get("state_change_b", 0))),
        force_b=min(100, max(0, props.get("force_b", 0))),
        direction_b=1 if props.get("direction_b", 0) else 0,
        destroy_a=bool(props.get("destroy_a", 0)),
        destroy_b=bool(props.get("destroy_b", 0)),
        mode=1 if props.get("mode", 0) else 0,
    )
    await cache.set("pairwise", pair_key, result.model_dump())
    return result


async def evaluate_new_object(
    new_bp: dict, scene_bps: list[dict], cache: CacheManager, session_id: str
) -> None:
    """Screen + full-eval all interesting pairs for a newly spawned object."""
    interesting = await screen_pairs(new_bp, scene_bps, cache)
    logger.info(
        "pairwise_screening",
        new=new_bp["name"],
        interesting=len(interesting),
        total=len(scene_bps),
    )

    async def _eval_and_notify(other_bp: dict) -> None:
        result = await evaluate_pair(new_bp, other_bp, cache)
        pair_key = CacheManager.pair_key(new_bp["name"], other_bp["name"])
        await send_pairwise_ready(session_id, pair_key, result.model_dump())

    await asyncio.gather(*[_eval_and_notify(scene_bps[i]) for i in interesting])
