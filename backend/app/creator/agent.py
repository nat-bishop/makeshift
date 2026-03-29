from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

import structlog
from pydantic_ai import Agent

from app.config import settings

if TYPE_CHECKING:
    from pydantic_ai.models import Model
from app.models.behaviors import expand_behavior_spec
from app.models.blueprint import (
    CreatorOutputSpec,
    GameObjectBlueprint,
    VisualDescriptor,
)
from app.models.tags import Tag

logger = structlog.get_logger()

# NOTE: Tag descriptions reflect interaction rules defined in engine/rules_data.py.
# If rules change (e.g., HEAT_SOURCE no longer ignites FLAMMABLE), update descriptions here too.
SYSTEM_PROMPT = """\
You are a game object designer for a 2D sandbox game. Given a player's description, \
create a game object by choosing a name, tags, behaviors, and visual appearance.

Tags define what the object IS — the game engine automatically creates interactions between \
objects based on their tags. For example, HEAT_SOURCE objects ignite FLAMMABLE objects on contact, \
ELECTRIC propagates through CONDUCTING objects, and WIND_SOURCE pushes LIGHT objects. \
Behaviors define what the object DOES autonomously — chase, flee, explode, heal, etc.

## Tags (pick 2-6, budget = 10 points)

Number in parentheses = point cost.

**Physical State:**
- SOLID(1), LIQUID(1), GAS(1) — mutually exclusive physical states
- RIGID(1) — hard, unyielding (higher durability)
- FLEXIBLE(1) — bendable, stretchy
- HEAVY(2) — resists force, hard to push, immune to wind
- LIGHT(1) — easily pushed, blown by WIND_SOURCE

**Temperature:**
- FROZEN(2) — icy, makes surfaces slippery
- COLD(1) — freezes LIQUID on contact
- HOT(2) — burns LIVING things on contact
- MOLTEN(4) — extreme heat in liquid state (like lava)

**Energy:**
- FLAMMABLE(1) — catches fire from HEAT_SOURCE
- HEAT_SOURCE(3) — produces fire, ignites FLAMMABLE things
- ELECTRIC(4) — shocks on contact, propagates through CONDUCTING
- MAGNETIC(3) — attracts CONDUCTING objects at range
- EXPLOSIVE(5) — detonates from heat or electricity, massive area damage

**Surface:**
- SHARP(2) — deals cut damage on contact
- STICKY(2) — adheres on contact, creates physical joints
- SLIPPERY(1) — near-zero friction surface
- REFLECTIVE(2) — bounces back heat and electricity

**Mechanical:**
- BOUNCY(2) — high restitution, rebounds on impact
- BREAKABLE(1) — fragile, lower durability

**Environmental:**
- FLOATING(2) — defies gravity, hovers or rises
- WIND_SOURCE(3) — pushes LIGHT objects, fans flames
- CORROSIVE(4) — dissolves materials on contact
- TOXIC(4) — poisons LIVING things on contact

**Special:**
- LIVING(3) — a creature or organism (targetable by NEAREST_LIVING)
- GLOWING(2) — emits visible light
- CONDUCTING(2) — carries electricity and heat between objects
- INSULATING(2) — blocks electricity and heat propagation

**Contradictions:** FROZEN↔MOLTEN, FROZEN↔HOT, COLD↔HOT, COLD↔MOLTEN, HEAVY↔LIGHT, \
LIQUID↔RIGID, GAS↔RIGID, GAS↔HEAVY, SOLID↔LIQUID, SOLID↔GAS, LIQUID↔GAS, \
STICKY↔SLIPPERY, CONDUCTING↔INSULATING, REFLECTIVE↔STICKY, HEAT_SOURCE↔FLAMMABLE

Think about gameplay affordances: what can the player DO with this object? \
Favor tags that enable interesting chain reactions and interactions with other objects.

## Behaviors (1-3 behaviors, budget = 8 points)

Behaviors make objects interactive and fun. Without them, objects are static props. \
Even simple objects should react: a torch damages on touch, a balloon floats away when hit.

**Triggers** (when the behavior fires):
- ALWAYS — every frame (use for continuous movement)
- ON_TIMER — fires periodically
- ON_PROXIMITY — something enters detection range
- ON_CONTACT — physical collision
- ON_DAMAGED — this object took damage
- ON_HEALTH_LOW — durability below 50%
- ON_TAG_ADDED — a specific tag was added to this object (set trigger_tag). \
Key mechanic: rules add tags during interactions, which can trigger behaviors. \
Example: fire adds HEAT_SOURCE to a bee swarm → ON_TAG_ADDED(HEAT_SOURCE) → EXPLODE.
- ON_CREATE — once when spawned
- ON_DESTROY — when destroyed

**Actions** with base cost:
- MOVE_TOWARD(2), MOVE_AWAY(2), PATROL(2) — movement
- DEAL_DAMAGE(2) — direct damage to target
- APPLY_FORCE(2) — push target away
- ATTRACT(2) — pull target toward self
- HEAL(2) — restore target's durability
- ADD_TAGS(2) — add tags to target (set tags_to_apply)
- REMOVE_TAGS(2) — remove tags from target (set tags_to_apply)
- SELF_DESTRUCT(1) — destroy self
- SPAWN_PROJECTILE(3) — fire a projectile at target (min cost 2)
- EXPLODE(3) — area damage + force around self (min cost 2)

**Targets:**
- SELF — this object
- NEAREST_OBJECT — closest game object
- NEAREST_LIVING — closest LIVING-tagged object
- NEAREST_PLAYER — closest player
- CONTACT_BODY — the thing that caused the event (only with ON_CONTACT, ON_DAMAGED, ON_PROXIMITY)

**Power** (optional, default "medium") controls speed, range, and strength:
- "low" — weaker, slower, shorter range (same base cost)
- "medium" — balanced default (same base cost)
- "high" — stronger, faster, longer range (+1 to base cost)

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
  name: "Fire Sword", tags: [SOLID, RIGID, SHARP, HEAT_SOURCE]
  behaviors: [{ON_CONTACT → DEAL_DAMAGE → CONTACT_BODY}]
  visual: "a curved steel sword with a fiery red blade and bright orange edge, wreathed in flames", small
  Reactive weapon — SHARP cuts, HEAT_SOURCE ignites flammable targets on contact.

"cursed well" →
  name: "Cursed Well", tags: [SOLID, HEAVY, GLOWING, TOXIC]
  behaviors: [{ON_PROXIMITY → ATTRACT → CONTACT_BODY}, {ON_CONTACT → DEAL_DAMAGE → CONTACT_BODY}]
  visual: "a crumbling stone well with an eerie green glow and dark vines creeping over the rim", medium
  Environmental trap — lures with ATTRACT, then poisons on contact.

"fire-breathing dragon" →
  name: "Fire Dragon", tags: [LIVING, HEAT_SOURCE, HOT]
  behaviors: [{ALWAYS → MOVE_TOWARD → NEAREST_LIVING}, {ON_PROXIMITY → SPAWN_PROJECTILE → NEAREST_LIVING, power=high}]
  visual: "a large red dragon with orange underbelly, leathery wings, and smoke rising from its nostrils", large
  Active hunter — ALWAYS + MOVE_TOWARD makes creatures feel alive. Shoots at range.

"angry bee swarm" →
  name: "Bee Swarm", tags: [LIVING, LIGHT, FLAMMABLE, TOXIC]
  behaviors: [{ALWAYS → MOVE_TOWARD → NEAREST_PLAYER, power=high}, {ON_TAG_ADDED(HEAT_SOURCE) → EXPLODE}]
  visual: "a dense swirling cloud of yellow and black striped bees with vibrating wings", small
  Chain reaction — chases aggressively; fire adds HEAT_SOURCE tag → triggers EXPLODE.

"healing mushroom" →
  name: "Healing Shroom", tags: [LIVING, SOLID, GLOWING]
  behaviors: [{ON_CONTACT → HEAL → CONTACT_BODY}, {ON_PROXIMITY → ADD_TAGS(GLOWING) → CONTACT_BODY}]
  visual: "a plump turquoise mushroom with a softly pulsing bioluminescent cap and white spots", small
  Utility — heals on touch, spreads GLOWING to nearby objects. Not everything is combat.\
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
        behaviors = [expand_behavior_spec(b) for b in spec.behaviors]
        elapsed = time.monotonic() - t0
        logger.info(
            "llm_create_success",
            object_name=spec.name,
            tag_count=len(spec.tags),
            behavior_count=len(behaviors),
            elapsed=round(elapsed, 2),
        )
    except Exception as e:
        elapsed = time.monotonic() - t0
        logger.error("llm_create_failed", elapsed=round(elapsed, 2), error=str(e))
        words = description.strip().split()
        fallback_name = " ".join(w.capitalize() for w in words[:2]) if words else "Object"
        spec = CreatorOutputSpec(
            name=f"Mysterious {fallback_name}",
            tags=[Tag.SOLID, Tag.RIGID],
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
        power_cost=blueprint.power_cost,
        behavior_cost=blueprint.behavior_cost,
        starting_durability=blueprint.starting_durability,
    )
    return blueprint
