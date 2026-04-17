"""V3 Creator pipeline: decomposed parallel LLM calls + creation cache.

Flow:
  1. Check creation cache (description -> cached blueprint)
  2. Fan-out: name + all questions in parallel (all use {description})
     - Unconditional: mass, height, surface, bounce, gravity,
       durability, active, affordance, visual_description,
       initial_state (5-way pick), susceptible state bools (4)
     - Gated on active: speed
     - Gated on durability<6: destruction_result_name
  3. Parse and assemble GameObjectBlueprint
  4. Cache creation result
  5. Return blueprint
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import TYPE_CHECKING

import structlog

from app.config import settings
from app.creator.llm import ask_text
from app.creator.question_graph import run_questions
from app.models.blueprint import (
    GameObjectBlueprint,
    PhysicsProperties,
)
from app.prompts.creation import ALL_CREATION_QUESTIONS, NAME_QUESTION

if TYPE_CHECKING:
    from app.cache.store import CacheStore

logger = structlog.get_logger()


async def create_object(description: str, cache: CacheStore) -> GameObjectBlueprint:
    """Create a V3 game object from a player description.

    Checks creation cache first. On miss, runs gated parallel LLM calls.
    Returns a complete GameObjectBlueprint ready for the client.
    """
    t0 = time.monotonic()

    # 1. Check creation cache (keyed by description for exact-match reuse)
    if settings.creation_cache_enabled:
        cached = await cache.get_creation(description)
        if cached is not None:
            logger.debug("creation_cache_hit", description=description)
            return GameObjectBlueprint(id=str(uuid.uuid4()), description=description, **cached)

    # 2. Fan-out: name + all questions in parallel (all use {description})
    raw_name, answers = await asyncio.gather(
        ask_text(
            NAME_QUESTION.prompt.format(description=description),
            max_tokens=NAME_QUESTION.max_tokens,
            default=str(NAME_QUESTION.default),
        ),
        run_questions(ALL_CREATION_QUESTIONS, {"description": description}),
    )
    words = raw_name.split()
    name = " ".join(words[:5]) if len(words) > 5 else raw_name
    if not name.strip():
        name = description.split()[0].capitalize() if description.strip() else "Object"

    # 4. Assemble
    physics = PhysicsProperties(
        mass_kg=float(answers.get("mass_kg", 1.0)),
        height_cm=int(answers.get("height_cm", 30)),
        surface=int(answers.get("surface", 1)),
        bounce=int(answers.get("bounce", 10)),
        gravity=int(answers.get("gravity", 50)),
    )

    # Collect initial/susceptible states from answers.
    # initial_state is a single-pick enum (0=none, 1=burning, 2=frozen, 3=wet, 4=electrified);
    # susceptibility remains 4 independent booleans because materials genuinely combine.
    initial_state = int(answers.get("initial_state", 0))
    initial_states = [initial_state] if initial_state else []
    _SUSCEPTIBLE_KEYS = {
        1: "catches_fire",
        2: "can_freeze",
        3: "gets_wet",
        4: "conducts_electricity",
    }
    susceptible_states = [sid for sid, key in _SUSCEPTIBLE_KEYS.items() if answers.get(key)]

    destruction_raw = str(answers.get("destruction_result_name", "nothing"))
    destruction_name = "" if destruction_raw in ("nothing", "none", "") else destruction_raw

    blueprint_data = {
        "name": name,
        "visual_description": str(answers.get("visual_description", f"a {description}")),
        "physics": physics.model_dump(),
        "durability": int(answers.get("durability", 2)),
        "affordance": int(answers.get("affordance", 3)),
        "active": bool(answers.get("active", False)),
        "speed": int(answers.get("speed", 2)),
        "initial_states": initial_states,
        "susceptible_states": susceptible_states,
        "destruction_result_name": destruction_name,
    }

    # 5. Cache
    if settings.creation_cache_enabled:
        await cache.put_creation(description, blueprint_data, model_version=settings.llm_model)

    # 6. Build blueprint
    blueprint = GameObjectBlueprint(id=str(uuid.uuid4()), description=description, **blueprint_data)  # type: ignore[arg-type]

    elapsed = time.monotonic() - t0
    logger.info("v3_create", name=name, elapsed=f"{elapsed:.2f}s")
    return blueprint
