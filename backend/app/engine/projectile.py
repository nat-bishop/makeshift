"""Projectile blueprint generation.

Triggered when an object's behavior eval produces at least one entry with
`delivery=projectile`. Runs physics + visual LLM calls in parallel, then
renders a sprite via FLUX. Result is cached by name so multiple firers
that shoot the same kind of projectile (e.g. two helicopters firing
"missile") reuse one blueprint + one sprite.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import structlog

from app.config import settings
from app.creator.question_graph import run_questions
from app.models.blueprint import (
    PhysicsProperties,
    ProjectileBlueprint,
)
from app.prompts.creation import CREATION_QUESTIONS, VISUAL_QUESTION

if TYPE_CHECKING:
    from app.cache.store import CacheStore

logger = structlog.get_logger()


# Physics questions a projectile actually needs, lifted by key from the canonical
# creation question list so prompt text stays in one place. Assertion guards
# against a rename in prompts/creation.py silently dropping a field.
_PROJECTILE_PHYSICS_KEYS = ("mass_kg", "height_cm", "gravity")
_PROJECTILE_QUESTIONS = [
    *[q for q in CREATION_QUESTIONS if q.key in _PROJECTILE_PHYSICS_KEYS],
    VISUAL_QUESTION,
]
assert len(_PROJECTILE_QUESTIONS) == len(_PROJECTILE_PHYSICS_KEYS) + 1, (
    f"Projectile question lookup missed a key from CREATION_QUESTIONS — "
    f"expected {_PROJECTILE_PHYSICS_KEYS}, got {[q.key for q in _PROJECTILE_QUESTIONS]}"
)


async def create_projectile(
    name: str,
    cache: CacheStore,
) -> ProjectileBlueprint:
    """Generate (or fetch cached) a ProjectileBlueprint for *name*.

    Checks the projectile cache first. On miss: parallel LLM calls for
    physics + visual, then FLUX text-to-image. Stores the result under the
    normalized projectile name so later firers with the same projectile
    name hit the cache.
    """
    from app.cache.store import normalize_name
    from app.images.pipeline import generate_static_sprite, get_cached_sprite_path
    from app.prompts.image import build_text_to_image_prompt

    norm = normalize_name(name)

    if settings.creation_cache_enabled:
        cached = await cache.get_projectile(norm)
        if cached is not None:
            logger.debug("projectile_cache_hit", name=norm)
            return ProjectileBlueprint(**cached)

    t0 = time.monotonic()

    answers = await run_questions(_PROJECTILE_QUESTIONS, {"description": name})

    physics = PhysicsProperties(
        mass_kg=float(answers.get("mass_kg", 0.5)),
        height_cm=int(answers.get("height_cm", 20)),
        surface=1,
        bounce=0,
        gravity=int(answers.get("gravity", 55)),
    )
    visual_description = str(answers.get("visual_description", f"a {name}"))

    # Render the sprite via FLUX (cached per prompt hash on disk)
    prompt = build_text_to_image_prompt(name, visual_description)
    cache_path = get_cached_sprite_path(prompt)
    sprite_url = f"/static/sprites/{cache_path.name}"

    if not cache_path.exists():
        try:
            sprite_bytes = await generate_static_sprite(prompt)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(sprite_bytes)
        except (RuntimeError, TimeoutError, OSError, ValueError):
            logger.error("projectile_sprite_failed", name=norm, exc_info=True)
            sprite_url = ""

    blueprint = ProjectileBlueprint(
        name=norm,
        visual_description=visual_description,
        physics=physics,
        sprite_url=sprite_url,
    )

    if settings.creation_cache_enabled and sprite_url:
        await cache.put_projectile(
            norm,
            blueprint.model_dump(mode="json"),
            model_version=settings.llm_model,
        )

    elapsed = time.monotonic() - t0
    logger.info(
        "projectile_generated",
        name=norm,
        mass_kg=physics.mass_kg,
        elapsed=f"{elapsed:.2f}s",
    )
    return blueprint


_inflight: dict[str, asyncio.Task[ProjectileBlueprint]] = {}


async def get_or_create_projectile(
    name: str,
    cache: CacheStore,
) -> ProjectileBlueprint:
    """Deduplicate concurrent generations of the same projectile name.

    If two firers spawn at the same time and both pick "missile", only one
    create_projectile() call runs; the second awaits the same Task.
    """
    from app.cache.store import normalize_name

    norm = normalize_name(name)
    existing = _inflight.get(norm)
    if existing is not None and not existing.done():
        return await existing

    async def _run() -> ProjectileBlueprint:
        try:
            return await create_projectile(norm, cache)
        finally:
            _inflight.pop(norm, None)

    task = asyncio.create_task(_run())
    _inflight[norm] = task
    return await task


def trigger_projectile_generation(
    session_id: str,
    entries: list[dict],
    cache: CacheStore,
    background_tasks: set[asyncio.Task],
) -> None:
    """Inspect behavior entries, kick off projectile generation in the background
    for every unique projectile_name with delivery=projectile, and broadcast
    `projectile_ready` to the session once each blueprint is ready.

    Caller passes its own task set so completed tasks can be GC'd properly.
    """
    names = {
        str(entry.get("projectile_name", "")).strip()
        for entry in entries
        if int(entry.get("delivery", 0)) == 1
    }
    names.discard("")
    if not names:
        return

    from app.ws.handler import send_projectile_ready

    async def _gen_and_send(name: str) -> None:
        try:
            blueprint = await get_or_create_projectile(name, cache)
            if blueprint.sprite_url:
                await send_projectile_ready(
                    session_id,
                    blueprint.model_dump(mode="json"),
                )
            else:
                logger.warning("projectile_no_sprite", name=name)
        except Exception:
            logger.warning("projectile_trigger_failed", name=name, exc_info=True)

    for name in names:
        task = asyncio.create_task(_gen_and_send(name))
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)
