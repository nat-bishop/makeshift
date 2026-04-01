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

Tags define what the object IS — its material, physical properties, and nature. The game \
engine automatically creates interactions between objects based on their tags.

Common behaviors are already handled by tags:
- HOSTILE + LIVING → automatically chases creatures and flees when hurt
- LIVING (alone) → wanders passively
- EXPLOSIVE → detonates when damaged
Don't write a signature behavior for things tags already do.

The signature behavior is for ONE unique action that makes this specific object unusual — \
ranged attacks, healing, tag mutation, or reactive transformations. Most objects don't need one.

## Tags (pick 2-5 — more tags = richer interactions)

**Physical State:**
- LIQUID — fluid that flows and pools. Water, oil, slime. NOT for solid objects that are wet (use WET).
- GAS — airborne, dispersed substance. Smoke, steam, poison clouds.
- RIGID — hard, unyielding material (200 HP). Stone, metal, bone, hardwood.
- HEAVY — dense and massive. Anvils, boulders, safes. Immovable by wind or pushing.
- LIGHT — very low mass, easily blown around. Feathers, paper, balloons, leaves. Pushed by \
players, launched by WIND_SOURCE. NOT for sturdy objects that just aren't heavy — a springboard or wooden shield isn't LIGHT.

**Temperature:**
- FROZEN — encased in ice or made of ice. Ice blocks, frozen food, frost crystals. Brittle and slippery.
- COLD — actively radiates cold. Freezers, ice elementals, snow clouds.
- MOLTEN — superheated liquid. Lava, molten metal, magma.

**Energy:**
- FLAMMABLE — combustible material. Wood, cloth, paper, dry plants, oil. Ignited by HEAT_SOURCE or ELECTRIC sparks.
- HEAT_SOURCE — actively produces heat or fire. Torches, campfires, fire elementals.
- ELECTRIC — carries or produces electrical charge. Lightning bolts, live wires, electric eels. Propagates through METALLIC and LIQUID.
- MAGNETIC — generates a magnetic field. Magnets, lodestones, electromagnetic devices. Pulls METALLIC objects at range.
- EXPLOSIVE — volatile, detonates under stress. Dynamite, grenades, gas canisters. Auto-detonates when damaged.

**Surface:**
- SHARP — has a cutting edge or point. Swords, thorns, broken glass, claws.
- STICKY — adhesive, viscous surface. Honey, tar, spider webs, glue. Slows nearby to 25% speed.
- REFLECTIVE — smooth, mirror-like surface. Shields, mirrors, polished metal. Resists energy and acid.

**Mechanical:**
- BOUNCY — elastic, high restitution. Rubber balls, springs, trampolines.
- BREAKABLE — fragile, easily destroyed (50 HP). Glass, pottery, eggshells.

**Environmental:**
- FLOATING — buoyant, defies gravity. Balloons, ghosts, clouds, bubbles.
- WIND_SOURCE — produces strong air currents. Fans, tornados, bellows, jet engines. Pushes LIGHT, disperses GAS.
- ACIDIC — corrosive chemical. Acid pools, chemical waste, digestive fluid.
- TOXIC — poisonous substance. Venom, toxic mushrooms, noxious fumes. Cascades through GAS.
- WET — damp or soaked. Muddy, slimy, rain-soaked. Amplifies ELECTRIC shock, freezes from COLD, resists fire.

**Special:**
- LIVING — biological creature or organism. Animals, monsters, insects. NOT machines or vehicles.
- METALLIC — made of metal. Swords, armor, coins, chains. Conducts heat and electricity.
- INSULATING — blocks energy transfer. Rubber coating, ceramic, thick glass.
- HOSTILE — aggressive and dangerous. Deals damage and knockback to nearby creatures. Two HOSTILE objects fight each other.

**Contradictions (cannot coexist):** FROZEN↔MOLTEN, FROZEN↔HEAT_SOURCE, COLD↔HEAT_SOURCE, COLD↔MOLTEN, \
HEAVY↔LIGHT, LIQUID↔RIGID, GAS↔RIGID, GAS↔HEAVY, LIQUID↔GAS, \
METALLIC↔INSULATING, WET↔MOLTEN, WET↔HEAT_SOURCE

Every tag creates new interaction surfaces — a wooden barrel with just [RIGID] is boring, \
but add BREAKABLE (smashable), FLAMMABLE (burnable), HEAVY (immovable) and it comes alive. \
Simple objects like a rock or feather need 2-3 tags. Creatures, mechanisms, and multi-material \
objects should use 4-5 to capture what makes them interesting.

## Signature Behavior (optional — most objects don't need one)

The signature is ONE unique behavior that makes this object special beyond what its tags do. \
Objects without a signature still interact richly through tags and rules alone.

**When to add a signature:**
- Ranged attack: a dragon breathes fire, a turret shoots projectiles
- Healing: a mushroom heals whoever kicks it
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
ADD_TAGS and ON_TAG_ADDED only accept tags from the tag list above — no custom or invented tags.
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
  name: "Fire Sword", tags: [RIGID, SHARP, HEAT_SOURCE, FLAMMABLE], signature: null
  RIGID because it's solid metal. SHARP because it has a blade. HEAT_SOURCE because it's \
  on fire. FLAMMABLE because the handle is wood — it can catch fire too! No signature needed.

"campfire" →
  name: "Campfire", tags: [HEAT_SOURCE, FLAMMABLE, BREAKABLE], signature: "ON_PROXIMITY -> HEAL -> NEAREST_LIVING, power=low"
  HEAT_SOURCE because it produces fire. FLAMMABLE means the fire can spread to it too. \
  BREAKABLE means it can be destroyed. Signature adds unique healing aura that tags can't provide.

"acid spider" →
  name: "Acid Spider", tags: [LIVING, HOSTILE, ACIDIC, LIGHT], signature: "ON_PROXIMITY -> SPAWN_PROJECTILE -> NEAREST_LIVING, power=medium"
  HOSTILE + LIVING auto-chases and flees when hurt. ACIDIC dissolves on contact. \
  LIGHT because it's a small creature. Signature adds ranged acid spit — the one thing tags can't do.

"death flower" →
  name: "Toxic Bloom", tags: [RIGID, BREAKABLE, TOXIC, FLAMMABLE], signature: "ON_DAMAGED -> EXPLODE"
  Looks harmless. TOXIC because it's poisonous. BREAKABLE because it's fragile. \
  FLAMMABLE because it's a plant. Signature: explodes into a toxic cloud when destroyed.

"ice wall" →
  name: "Ice Wall", tags: [RIGID, FROZEN, HEAVY, REFLECTIVE], signature: "ON_CONTACT -> ADD_TAGS(FROZEN)"
  RIGID because it's solid. FROZEN because it's made of ice. HEAVY because it's a wall. \
  REFLECTIVE because ice has a shiny surface. Signature freezes things on contact.

"wooden chair" →
  name: "Oak Chair", tags: [RIGID, BREAKABLE, FLAMMABLE, LIGHT], signature: null
  A simple mundane object — but 4 tags make it interactive. RIGID because it's solid wood. \
  BREAKABLE because it can be smashed. FLAMMABLE because wood burns. LIGHT because wind \
  blows it around. No signature needed.

"cowardly slime" →
  name: "Scaredy Slime", tags: [LIVING, WET, LIQUID, STICKY], signature: "ON_PROXIMITY -> MOVE_AWAY -> NEAREST_LIVING, power=high"
  LIVING because it's a creature. WET because it's slimy. LIQUID because it's a fluid blob. \
  STICKY because slime is adhesive. Signature overrides the default wander with flee — personality!

## Common Mistakes

DON'T use LIQUID for solid objects. A banana is not a liquid. A rope is not a liquid. \
LIQUID means the object flows like water. Use WET if something is damp.

DON'T use LIVING for machines or vehicles. A helicopter is not alive. A jetpack is not alive. \
LIVING means a biological creature. For machines that move, use a signature behavior.

DON'T make signatures that duplicate what tags do. If the object has HOSTILE + LIVING, \
it already chases — don't add a MOVE_TOWARD signature. If it has EXPLOSIVE, it already \
detonates — don't add an EXPLODE signature.

DON'T settle for 1-2 tags when the object has more properties. Ask: what is it made of? \
Is it fragile or tough? Can it burn, conduct, or corrode? A wooden barrel is RIGID + \
BREAKABLE + FLAMMABLE + HEAVY — each tag is something true about the object.

DON'T write multiple signatures — only ONE is allowed. No semicolons or commas to chain them.

DON'T use SELF as a target for MOVE_TOWARD or MOVE_AWAY — you can't move toward yourself. \
Use NEAREST_LIVING or NEAREST_PLAYER.

DON'T forget the tag in ON_TAG_ADDED — write ON_TAG_ADDED(HEAT_SOURCE), not ON_TAG_ADDED alone.\
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
            tags=[Tag.RIGID, Tag.BREAKABLE],
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
