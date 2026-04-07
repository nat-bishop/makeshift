from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

import structlog
from pydantic_ai import Agent

from app.cache.manager import CacheManager
from app.creator.llm import build_model
from app.creator.questions import (
    CREATION_QUESTIONS,
    DESTRUCTION_QUESTION,
    VISUAL_QUESTION,
    Question,
    parse_bool,
)
from app.models.blueprint import GameObjectBlueprint, VisualDescriptor

logger = structlog.get_logger()

_background_tasks: set[asyncio.Task[Any]] = set()


async def _ask(question: Question, name: str) -> tuple[str, Any]:
    """Ask one LLM question, return (key, parsed_value)."""
    prompt = question.prompt_template.format(name=name)
    agent = Agent(
        build_model(),
        output_type=str,
        model_settings={"max_tokens": question.max_tokens, "temperature": 0.3},
    )
    result = await agent.run(prompt)
    return (question.key, question.parse(result.output))


async def create_object(description: str, cache: CacheManager) -> GameObjectBlueprint:
    """V3 creation: cache check -> parallel fan-out -> assemble blueprint."""
    name = description.strip()
    cache_key = CacheManager.normalize_key(name)

    # Check creation cache
    cached = await cache.get("creation", cache_key)
    if cached:
        logger.info("creation_cache_hit", name=name)
        return GameObjectBlueprint(id=str(uuid.uuid4()), description=description, **cached)

    t0 = time.monotonic()

    # Fan-out: all questions in parallel
    all_questions = CREATION_QUESTIONS + [VISUAL_QUESTION, DESTRUCTION_QUESTION]
    results = await asyncio.gather(
        *[_ask(q, name) for q in all_questions],
        return_exceptions=True,
    )

    # Assemble, handle failures with defaults
    props: dict[str, Any] = {}
    for i, r in enumerate(results):
        q = all_questions[i]
        if isinstance(r, Exception):
            logger.warning("question_failed", key=q.key, error=str(r))
            if q.key == "visual_description":
                props[q.key] = f"a {name}"
            elif q.key == "destruction_result_name":
                props[q.key] = "nothing"
            elif q.parse == parse_bool:
                props[q.key] = False
            else:
                props[q.key] = 0
        else:
            props[q.key] = r[1]

    # Clamp
    props["mass_kg"] = max(0.001, min(100000, props.get("mass_kg", 1.0)))
    props["height_cm"] = max(1, min(5000, props.get("height_cm", 50)))
    for k in ("friction", "bounce", "gravity", "armor", "hp"):
        props[k] = max(0, min(100, props.get(k, 50)))
    props["field_range_cm"] = max(0, min(5000, props.get("field_range_cm", 0)))
    props["affordance"] = max(0, min(3, props.get("affordance", 3)))
    if not props.get("has_field"):
        props["field_range_cm"] = 0

    # Derive size_category from height
    h = props["height_cm"]
    if h <= 5:
        size_cat = "tiny"
    elif h <= 40:
        size_cat = "small"
    elif h <= 150:
        size_cat = "medium"
    elif h <= 400:
        size_cat = "large"
    else:
        size_cat = "huge"

    # Handle destruction result
    destruction_name = props.get("destruction_result_name", "nothing")
    if str(destruction_name).lower() in ("nothing", "none", ""):
        destruction_name = ""

    blueprint_data = {
        "name": name,
        "mass_kg": props["mass_kg"],
        "height_cm": props["height_cm"],
        "friction": props["friction"],
        "bounce": props["bounce"],
        "gravity": props["gravity"],
        "armor": props["armor"],
        "hp": props["hp"],
        "indestructible": bool(props.get("indestructible", False)),
        "has_field": bool(props.get("has_field", False)),
        "field_range_cm": props["field_range_cm"],
        "autonomous": bool(props.get("autonomous", False)),
        "affordance": props["affordance"],
        "visual_descriptor": {
            "visual_description": props.get("visual_description", f"a {name}"),
            "size_category": size_cat,
        },
        "destruction_result_name": destruction_name,
    }

    await cache.set("creation", cache_key, blueprint_data)

    # If destruction result is non-empty, pre-cache its creation too (background)
    if destruction_name:
        task = asyncio.create_task(_precache_destruction_result(str(destruction_name), cache))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    elapsed = time.monotonic() - t0
    logger.info("object_created", name=name, elapsed=round(elapsed, 2))
    return GameObjectBlueprint(id=str(uuid.uuid4()), description=description, **blueprint_data)


async def _precache_destruction_result(name: str, cache: CacheManager) -> None:
    """Pre-cache the destruction result blueprint so destruction feels instant."""
    cache_key = CacheManager.normalize_key(name)
    if await cache.exists("creation", cache_key):
        return
    try:
        await create_object(name, cache)
        logger.info("destruction_result_precached", name=name)
    except Exception as e:
        logger.warning("destruction_result_precache_failed", name=name, error=str(e))
