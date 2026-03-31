from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

import structlog
from pydantic_ai import Agent

from app.config import settings

if TYPE_CHECKING:
    from pydantic_ai.models import Model
from app.models.behaviors import expand_behavior_spec, parse_behavior_string
from app.models.blueprint import (
    CreatorOutputSpec,
    GameObjectBlueprint,
    VisualDescriptor,
)
from app.models.tag_behaviors import resolve_implied_behaviors
from app.models.tags import Tag

logger = structlog.get_logger()

# NOTE: Tag descriptions reflect interaction rules defined in engine/rules_data.py.
# If rules change (e.g., HEAT_SOURCE no longer ignites FLAMMABLE), update descriptions here too.
SYSTEM_PROMPT = """\
You are a game object designer for a 2D sandbox game. Given a player's description, \
create a game object by choosing a name, tags, an optional signature behavior, and visual appearance.

Tags define what the object IS — the game engine automatically creates interactions between \
objects based on their tags. For example, HEAT_SOURCE objects ignite FLAMMABLE objects, \
ELECTRIC propagates through METALLIC objects, and WIND_SOURCE pushes LIGHT objects.

Common behaviors are already handled by tags:
- HOSTILE + LIVING → automatically chases creatures and flees when hurt
- LIVING (alone) → wanders passively
- EXPLOSIVE → detonates when damaged
Don't write a signature behavior for things tags already do.

The signature behavior is for ONE unique action that makes this specific object unusual — \
ranged attacks, healing, tag mutation, or reactive transformations. Most objects don't need one.

## Tags (pick 1-4)

**Physical State:**
- LIQUID — fluid, extinguishes fire, spreads WET to nearby objects, freezes via COLD
- GAS — ultra-light, dispersed by wind, ionized by electricity into plasma
- RIGID — hard, unyielding (higher durability: 200 HP)
- HEAVY — resists force, hard to push, immune to wind, crushes breakable things
- LIGHT — easily pushed, blown by WIND_SOURCE

**Temperature:**
- FROZEN — icy, slippery surface, shatters breakable things, melts from heat
- COLD — freezes LIQUID and WET things, solidifies MOLTEN, conducts through METALLIC
- MOLTEN — extreme heat in liquid state (like lava), ignites flammable, destroys breakable

**Energy:**
- FLAMMABLE — catches fire from HEAT_SOURCE or ELECTRIC sparks. Great for chain reactions.
- HEAT_SOURCE — produces fire, ignites FLAMMABLE, melts FROZEN, evaporates LIQUID, dries WET
- ELECTRIC — shocks on contact, propagates through METALLIC and LIQUID (cascade!), ionizes GAS
- MAGNETIC — attracts METALLIC objects at range with continuous pull field
- EXPLOSIVE — detonates from heat or electricity, massive area damage. Auto-detonates when damaged.

**Surface:**
- SHARP — deals cut damage on contact to LIVING and BREAKABLE
- STICKY — slows everything nearby to 25% speed, area denial trap
- REFLECTIVE — bounces back heat, electricity, and resists acid

**Mechanical:**
- BOUNCY — high restitution, rebounds dramatically on impact
- BREAKABLE — fragile (50 HP), vulnerable to almost everything

**Environmental:**
- FLOATING — defies gravity, hovers or rises. Launched by wind, cancelled by heavy.
- WIND_SOURCE — pushes LIGHT objects, disperses GAS, launches FLOATING. Largest range field.
- ACIDIC — dissolves materials on contact. Corrodes breakable and rigid, dissolves metallic, \
burns living. Resisted by REFLECTIVE.
- TOXIC — poisons LIVING things at medium range. Cascades toxic cloud through GAS.
- WET — damp/soaked. Amplifies ELECTRIC shock (45 vs 30 dmg), freezes easier near COLD, \
resists fire. Applied automatically by nearby LIQUID objects.

**Special:**
- LIVING — a creature or organism. HOSTILE creatures chase; non-HOSTILE ones wander.
- METALLIC — conducts electricity and heat, attracted by magnets, dissolved by acid
- INSULATING — blocks electricity and heat propagation (powerful defensive modifier)
- HOSTILE — aggressive danger aura: deals damage + knockback at close range. \
Two HOSTILE objects clash and fight each other. HOSTILE + LIVING auto-chases.

**Contradictions (cannot coexist):** FROZEN↔MOLTEN, FROZEN↔HEAT_SOURCE, COLD↔HEAT_SOURCE, COLD↔MOLTEN, \
HEAVY↔LIGHT, LIQUID↔RIGID, GAS↔RIGID, GAS↔HEAVY, LIQUID↔GAS, \
METALLIC↔INSULATING, WET↔MOLTEN, WET↔HEAT_SOURCE

Think about gameplay: what can the player DO with this object? Favor tags that create \
chain reactions and interactions. Every tag should earn its slot.

## Signature Behavior (optional — most objects don't need one)

The signature is ONE unique behavior that makes this object special beyond what its tags do. \
Objects without a signature still interact richly through tags and rules alone.

**When to add a signature:**
- Ranged attack: a dragon breathes fire, a turret shoots projectiles
- Healing: a mushroom heals nearby creatures
- Tag mutation: an ice wall freezes things on contact (adds FROZEN tag)
- Reactive transformation: a bee swarm explodes when set on fire

**When NOT to add a signature:**
- Chasing/fleeing — HOSTILE + LIVING handles this automatically
- Wandering — LIVING handles this automatically
- Detonating when hit — EXPLOSIVE handles this automatically
- Contact damage — SHARP, HEAT_SOURCE, HOSTILE handle this via tags
- Pushing/pulling — WIND_SOURCE, MAGNETIC, HOSTILE handle this via tags

**Format:** TRIGGER -> ACTION or TRIGGER -> ACTION -> TARGET, power=POWER

Triggers: ALWAYS, ON_TIMER, ON_PROXIMITY, ON_CONTACT, ON_DAMAGED, ON_HEALTH_LOW, ON_TAG_ADDED(TAG)
Actions: MOVE_TOWARD, MOVE_AWAY, SPAWN_PROJECTILE, EXPLODE, HEAL, ADD_TAGS(TAG1, TAG2), SELF_DESTRUCT
Targets (optional — auto-inferred when omitted): SELF, NEAREST_LIVING, NEAREST_PLAYER
Power (optional, default "medium"): low, medium, high

Target is auto-inferred: ON_CONTACT/ON_DAMAGED → the colliding body, \
ON_PROXIMITY/ALWAYS → nearest creature, ON_TIMER/ON_HEALTH_LOW/ON_TAG_ADDED → self.

## Visual Descriptor

- visual_description: 1-2 sentences describing the object's appearance — shape, material, colors, \
distinctive features. Describe the object itself, not a scene or environment.
- size_category: relative to the player (small-to-medium sized). \
"tiny" = coins, bugs, keys; "small" = swords, tools, small animals; \
"medium" = crates, dogs, chairs; "large" = doors, boulders, bears; "huge" = trees, buildings, dragons

## Name

1-3 words. Concise and evocative.

## Examples

"fire sword" →
  name: "Fire Sword", tags: [RIGID, SHARP, HEAT_SOURCE], signature: null
  SHARP cuts on contact. HEAT_SOURCE ignites flammable targets. No signature needed — it's a weapon.

"fire-breathing dragon" →
  name: "Fire Dragon", tags: [LIVING, HOSTILE, HEAT_SOURCE, HEAVY]
  signature: "ON_PROXIMITY -> SPAWN_PROJECTILE -> NEAREST_LIVING, power=high"
  HOSTILE + LIVING auto-chases. HEAT_SOURCE ignites. Signature adds ranged fire breath.

"angry bee swarm" →
  name: "Bee Swarm", tags: [LIVING, LIGHT, FLAMMABLE, HOSTILE]
  signature: "ON_TAG_ADDED(HEAT_SOURCE) -> EXPLODE"
  Chain reaction: fire adds HEAT_SOURCE via rules → triggers EXPLODE signature.

"healing mushroom" →
  name: "Healing Shroom", tags: [LIVING]
  signature: "ON_PROXIMITY -> HEAL -> NEAREST_LIVING"
  LIVING makes it wander. Signature adds healing aura. Minimal tags, clear purpose.

"ice wall" →
  name: "Ice Wall", tags: [RIGID, FROZEN, HEAVY]
  signature: "ON_CONTACT -> ADD_TAGS(FROZEN)"
  Signature freezes things on contact (adds FROZEN tag). Tags handle durability and physics.

"guard dog" →
  name: "Guard Dog", tags: [LIVING, SHARP, HOSTILE, RIGID]
  signature: null
  HOSTILE + LIVING auto-chases. SHARP cuts on contact. HOSTILE field damages nearby. \
  No signature needed — tags fully express the concept.\
"""

_agent: Agent[None, CreatorOutputSpec] | None = None


def _build_model() -> Model | str:
    """Route to local SGLang (OpenAI-compatible) or cloud based on LOCAL_LLM_URL."""
    if settings.local_llm_url:
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        model = OpenAIChatModel(
            settings.llm_model,
            provider=OpenAIProvider(base_url=settings.local_llm_url, api_key="unused"),
        )
        logger.info("llm_model_built", model=settings.llm_model, base_url=settings.local_llm_url)
        return model

    logger.info("llm_model_built", model=settings.llm_model)
    return settings.llm_model


def _get_agent() -> Agent[None, CreatorOutputSpec]:
    global _agent
    if _agent is not None:
        logger.debug("agent_cached")
        return _agent
    model_settings: dict = {
        "timeout": settings.llm_timeout_seconds,
        "temperature": settings.llm_temperature,
        "top_p": settings.llm_top_p,
        "presence_penalty": settings.llm_presence_penalty,
    }
    # Pass SGLang-specific params via extra_body (top_k, min_p, repetition_penalty, thinking)
    if settings.local_llm_url:
        model_settings["extra_body"] = {
            "top_k": settings.llm_top_k,
            "min_p": settings.llm_min_p,
            "repetition_penalty": settings.llm_repetition_penalty,
            "chat_template_kwargs": {"enable_thinking": not settings.local_llm_thinking_disabled},
        }
    _agent = Agent(  # type: ignore[call-overload]
        _build_model(),
        output_type=CreatorOutputSpec,
        retries=3,
        system_prompt=SYSTEM_PROMPT,
        model_settings=model_settings,
    )
    logger.info("agent_created", model=settings.llm_model)
    return _agent


async def create_object(description: str) -> GameObjectBlueprint:
    """Create a game object from a player's text description.

    Uses the LLM to generate tags and visual description, then wraps
    into a full GameObjectBlueprint with computed fields. Falls back
    to a generic object on failure.
    """
    t0 = time.monotonic()
    try:
        agent = _get_agent()
        result = await agent.run(f"Create a game object for: {description}")
        spec = result.output

        # Parse explicit signature behavior if present
        explicit_behavior = None
        if spec.signature:
            explicit_behavior = expand_behavior_spec(parse_behavior_string(spec.signature))

        # Resolve implied behaviors from tags + merge with explicit
        behaviors = resolve_implied_behaviors(spec.tags, explicit_behavior)

        elapsed = time.monotonic() - t0
        logger.info(
            "llm_create_success",
            object_name=spec.name,
            tag_count=len(spec.tags),
            behavior_count=len(behaviors),
            has_signature=spec.signature is not None,
            elapsed=round(elapsed, 2),
        )
    except Exception as e:
        elapsed = time.monotonic() - t0
        logger.error("llm_create_failed", elapsed=round(elapsed, 2), error=str(e))
        words = description.strip().split()
        fallback_name = " ".join(w.capitalize() for w in words[:2]) if words else "Object"
        spec = CreatorOutputSpec(
            name=f"Mysterious {fallback_name}",
            tags=[Tag.RIGID],
            visual_descriptor=VisualDescriptor(
                visual_description="a mysterious glowing gray stone cube with sparkling flecks",
                size_category="medium",
            ),
        )
        behaviors = []

    blueprint = GameObjectBlueprint(
        id=str(uuid.uuid4()),
        name=spec.name,
        description=description,
        tags=spec.tags,
        behaviors=behaviors,
        visual_descriptor=spec.visual_descriptor,
    )
    logger.debug(
        "blueprint_created",
        object_id=blueprint.id,
        tag_count=len(blueprint.tags),
        behavior_count=len(blueprint.behaviors),
        starting_durability=blueprint.starting_durability,
    )
    return blueprint
