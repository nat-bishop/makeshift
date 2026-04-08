"""V3 Creator pipeline: decomposed parallel LLM calls + creation cache.

Flow:
  1. Check creation cache (description -> cached blueprint)
  2. Generate name (~3 tokens, sequential — other prompts use it)
  3. Fan-out: 12 parallel 1-token calls + visual description (~25 tokens)
  4. Parse and assemble GameObjectBlueprint
  5. Cache creation result
  6. Return blueprint
"""

from __future__ import annotations

import asyncio
import time
import uuid

import structlog

from app.cache.store import CacheStore
from app.config import settings
from app.creator.llm import ask_bool, ask_float, ask_int, ask_text
from app.creator.questions import (
    CREATION_QUESTIONS,
    DESTRUCTION_PROMPT,
    NAME_PROMPT,
    VISUAL_PROMPT,
    Question,
)
from app.models.blueprint import (
    Destructibility,
    GameObjectBlueprint,
    PhysicsProperties,
)

logger = structlog.get_logger()


async def _ask_question(q: Question, name: str) -> tuple[str, int | float | bool]:
    """Dispatch one question to the appropriate ask_* function."""
    prompt = q.prompt.format(name=name)
    if q.qtype == "float":
        return (q.key, await ask_float(prompt, float(q.lo), float(q.hi), float(q.default)))
    elif q.qtype == "bool":
        return (q.key, await ask_bool(prompt))
    else:
        return (q.key, await ask_int(prompt, int(q.lo), int(q.hi), int(q.default)))


async def _ask_visual(name: str, description: str) -> tuple[str, str]:
    prompt = VISUAL_PROMPT.format(name=name, description=description)
    text = await ask_text(prompt, max_tokens=40, default=f"a {description}")
    return ("visual_description", text)


async def _ask_destruction(name: str) -> tuple[str, str]:
    prompt = DESTRUCTION_PROMPT.format(name=name)
    text = await ask_text(prompt, max_tokens=8, default="nothing")
    return ("destruction_result_name", text.strip().lower())


async def create_object(description: str, cache: CacheStore) -> GameObjectBlueprint:
    """Create a V3 game object from a player description.

    Checks creation cache first. On miss, runs 13 parallel LLM calls.
    Returns a complete GameObjectBlueprint ready for the client.
    """
    t0 = time.monotonic()

    # 1. Check creation cache (keyed by description for exact-match reuse)
    cached = await cache.get_creation(description)
    if cached is not None:
        logger.info("creation_cache_hit", description=description)
        return GameObjectBlueprint(
            id=str(uuid.uuid4()), description=description, **cached
        )

    # 2. Generate name (~3 tokens, must run first — other prompts reference it)
    raw_name = await ask_text(
        NAME_PROMPT.format(description=description),
        max_tokens=8,
        default=description,
    )
    words = raw_name.split()
    name = " ".join(words[:3]) if len(words) > 3 else raw_name
    if not name.strip():
        name = description.split()[0].capitalize() if description.strip() else "Object"

    # 3. Fan-out: all questions + visual description in parallel
    tasks: list = [_ask_question(q, name) for q in CREATION_QUESTIONS]
    tasks.append(_ask_visual(name, description))
    tasks.append(_ask_destruction(name))

    results_list = await asyncio.gather(*tasks, return_exceptions=True)

    # Collect results, using defaults for any failures
    answers: dict = {}
    for r in results_list:
        if isinstance(r, tuple) and len(r) == 2:
            answers[r[0]] = r[1]
        elif isinstance(r, BaseException):
            logger.warning("creation_question_failed", error=str(r))

    # 4. Assemble
    has_field = bool(answers.get("has_field", False))
    field_range = int(answers.get("field_range_cm", 0)) if has_field else 0

    physics = PhysicsProperties(
        mass_kg=float(answers.get("mass_kg", 1.0)),
        height_cm=int(answers.get("height_cm", 30)),
        friction=int(answers.get("friction", 50)),
        bounce=int(answers.get("bounce", 10)),
        gravity=int(answers.get("gravity", 50)),
    )
    destructibility = Destructibility(
        armor=int(answers.get("armor", 30)),
        hp=int(answers.get("hp", 50)),
        indestructible=bool(answers.get("indestructible", False)),
    )

    destruction_raw = str(answers.get("destruction_result_name", "nothing"))
    destruction_name = "" if destruction_raw in ("nothing", "none", "") else destruction_raw

    blueprint_data = {
        "name": name,
        "visual_description": str(answers.get("visual_description", f"a {description}")),
        "physics": physics.model_dump(),
        "destructibility": destructibility.model_dump(),
        "affordance": int(answers.get("affordance", 3)),
        "autonomous": bool(answers.get("autonomous", False)),
        "has_field": has_field,
        "field_range_cm": field_range,
        "destruction_result_name": destruction_name,
    }

    # 5. Cache
    await cache.put_creation(
        description, blueprint_data, model_version=settings.llm_model
    )

    # 6. Build blueprint
    blueprint = GameObjectBlueprint(
        id=str(uuid.uuid4()), description=description, **blueprint_data
    )

    elapsed = time.monotonic() - t0
    logger.info("v3_create", name=name, elapsed=f"{elapsed:.2f}s")
    return blueprint
