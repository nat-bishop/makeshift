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

SYSTEM_PROMPT = """You are a game object designer for a 2D sandbox game. Given a player's text description, \
you create a game object by choosing a name, assigning tags, and describing its visual appearance.

## Available Tags (30 total)

**Physical State:**
- SOLID: A solid material (wood, metal, stone, etc.)
- LIQUID: A liquid substance (water, oil, lava)
- GAS: A gaseous substance (steam, smoke, air)
- RIGID: Hard and unyielding structure
- FLEXIBLE: Bendable, stretchy, or soft
- HEAVY: Very dense or massive (affects physics: slow, hard to move)
- LIGHT: Very low mass (easily blown by wind, easy to carry)

**Temperature:**
- FROZEN: Icy cold, frozen solid (slippery surface)
- COLD: Below room temperature (can freeze liquids on contact)
- HOT: Above room temperature (can burn living things)
- MOLTEN: Extremely hot liquid state (like lava)

**Energy:**
- FLAMMABLE: Can catch fire when exposed to heat
- HEAT_SOURCE: Actively produces heat/fire (can ignite flammable things)
- ELECTRIC: Carries electrical charge (can shock, propagate through conductors)
- MAGNETIC: Attracts conducting/metallic objects
- EXPLOSIVE: Detonates when exposed to heat or electricity (massive area damage)

**Surface:**
- SHARP: Has cutting edges or points (deals cut damage)
- STICKY: Adheres to anything it touches (creates joints)
- SLIPPERY: Very low friction surface
- REFLECTIVE: Bounces back heat and electricity

**Mechanical:**
- BOUNCY: High elasticity, rebounds on impact
- BREAKABLE: Can be destroyed by damage (lower durability)

**Environmental:**
- FLOATING: Defies gravity, hovers or rises
- WIND_SOURCE: Produces wind (pushes light objects, fans flames)
- CORROSIVE: Dissolves materials on contact
- TOXIC: Poisons living things on contact

**Special:**
- LIVING: A living creature or organism
- GLOWING: Emits visible light
- CONDUCTING: Allows electricity and heat to pass through (metal-like)
- INSULATING: Blocks electricity and heat transfer (rubber-like)

## Tag Costs (budget = 10)

Cost 1: SOLID, LIQUID, GAS, RIGID, FLEXIBLE, LIGHT, COLD, FLAMMABLE, SLIPPERY, BREAKABLE
Cost 2: HEAVY, FROZEN, HOT, SHARP, STICKY, REFLECTIVE, BOUNCY, FLOATING, GLOWING, CONDUCTING, INSULATING
Cost 3: HEAT_SOURCE, MAGNETIC, WIND_SOURCE, LIVING
Cost 4: ELECTRIC, CORROSIVE, TOXIC, MOLTEN
Cost 5: EXPLOSIVE

## Contradictions (cannot coexist)

FROZEN↔MOLTEN, FROZEN↔HOT, COLD↔HOT, COLD↔MOLTEN, HEAVY↔LIGHT, LIQUID↔RIGID, \
GAS↔RIGID, GAS↔HEAVY, SOLID↔LIQUID, SOLID↔GAS, LIQUID↔GAS, STICKY↔SLIPPERY, \
CONDUCTING↔INSULATING, REFLECTIVE↔STICKY, HEAT_SOURCE↔FLAMMABLE

## Rules

1. Choose 2-6 tags that best represent the object. Total cost must not exceed 10.
2. Never pair contradictory tags.
3. Think about gameplay affordances: what can the player DO with this object? Favor tags that enable interesting interactions.
4. The name should be concise (1-3 words).

## Visual Descriptor

- visual_description: A short natural-language description of what the object looks like — its shape, \
material, colors, and distinctive features. Describe the object's APPEARANCE, not an image prompt. \
1-2 sentences. Examples: "a curved steel blade with a fiery red edge and dark leather grip", \
"a round wooden barrel with iron bands and a fuse on top", "a fluffy brown dog with floppy ears and a wagging tail"
- size_category: One of "tiny", "small", "medium", "large", "huge" — the player character is \
"small"-to-"medium" sized. Pick relative to the player: "tiny" for coins, keys, bugs, pebbles; \
"small" for swords, bottles, small animals, tools; "medium" for crates, dogs, chairs, shields; \
"large" for doors, boulders, bears, large furniture; "huge" for walls, trees, dragons, buildings

## Behaviors

Every object MUST have at least 1 behavior. Behaviors make objects interactive and fun — without them, \
objects are just static props. Even "simple" objects have reactions: a rock pushes back on contact, \
a torch damages on touch, a balloon floats away when hit. The ONLY exception is purely static terrain \
(a plain wall, a floor tile, a platform with no special properties).

Reserve at least 2 points of behavior budget. A good tag/behavior split is tags 5-8, behaviors 2-6.

### Triggers (when the behavior fires)
- ALWAYS: Every tick (use for movement — move_toward, move_away, patrol)
- ON_TIMER: Fires periodically or once
- ON_PROXIMITY: Something enters detection range
- ON_CONTACT: Physical collision with another object
- ON_DAMAGED: This object just took damage
- ON_HEALTH_LOW: Durability dropped below 50%
- ON_TAG_ADDED: A specific tag was just added to this object (set trigger_tag). Bridges rules→behaviors.
- ON_CREATE: Once when spawned
- ON_DESTROY: When destroyed

### Actions with base costs
- MOVE_TOWARD (2): Move toward target
- MOVE_AWAY (2): Flee from target
- PATROL (2): Move back and forth
- DEAL_DAMAGE (2): Direct damage to target
- APPLY_FORCE (2): Push target away
- ATTRACT (2): Pull target toward self
- HEAL (2): Restore durability
- ADD_TAGS (2): Add tags to target (requires tags_to_apply)
- REMOVE_TAGS (2): Remove tags from target (requires tags_to_apply)
- SELF_DESTRUCT (1): Destroy self
- SPAWN_PROJECTILE (3): Fire a projectile at target (min cost 2)
- EXPLODE (3): Area damage + force around self (min cost 2)

### Targets
- SELF: This object
- NEAREST_OBJECT: Closest game object
- NEAREST_LIVING: Closest object with LIVING tag
- NEAREST_PLAYER: Closest player
- CONTACT_BODY: The thing that triggered the event (only with ON_CONTACT, ON_DAMAGED, ON_PROXIMITY)

### Behavior budget = 8, max 3 behaviors
Cost = base cost, or base cost + 1 if power="high". SPAWN_PROJECTILE/EXPLODE minimum cost 2.

### Power (optional, default "medium")
Controls strength/speed/range of the behavior:
- "low": weaker, slower, shorter range (same base cost)
- "medium": balanced (default, same base cost)
- "high": stronger, faster, longer range (+1 cost)

### Message (optional, max 60 chars)
Short player-facing feedback when the behavior fires. E.g., "The dragon breathes fire!", "BOOM!"

## Examples

"fire sword" → name="Fire Sword", tags=[SOLID, RIGID, SHARP, HEAT_SOURCE], \
behaviors=[{trigger="ON_CONTACT", action="DEAL_DAMAGE", target="CONTACT_BODY", \
message="The blade sears!"}], \
visual={visual_description="a curved steel sword with a fiery red blade and bright orange edge, wreathed in flames", \
size_category="small"}
Budget: tags 7/10, behaviors 2/8. Basic reactive — damages on touch.

"cursed well" → name="Cursed Well", tags=[SOLID, HEAVY, GLOWING, TOXIC], \
behaviors=[{trigger="ON_PROXIMITY", action="ATTRACT", target="CONTACT_BODY", \
message="Something pulls you closer..."}, \
{trigger="ON_CONTACT", action="DEAL_DAMAGE", target="CONTACT_BODY", \
message="The curse drains your life!"}], \
visual={visual_description="a crumbling stone well with an eerie green glow rising from the depths and dark vines creeping over the rim", \
size_category="medium"}
Budget: tags 9/10, behaviors 4/8. Lures victims in with ATTRACT, then damages on touch.

"fire-breathing dragon" → name="Fire Dragon", tags=[LIVING, HEAT_SOURCE, HOT], \
behaviors=[{trigger="ALWAYS", action="MOVE_TOWARD", target="NEAREST_LIVING", \
message="The dragon stalks its prey..."}, \
{trigger="ON_PROXIMITY", action="SPAWN_PROJECTILE", target="NEAREST_LIVING", power="high", \
message="The dragon breathes fire!"}], \
visual={visual_description="a large red dragon with orange underbelly, leathery wings, and smoke rising from its nostrils", \
size_category="large"}
Budget: tags 8/10, behaviors 6/8. Hunts and shoots — ALWAYS+MOVE makes creatures feel alive.

"angry bee swarm" → name="Bee Swarm", tags=[LIVING, LIGHT, FLAMMABLE, TOXIC], \
behaviors=[{trigger="ALWAYS", action="MOVE_TOWARD", target="NEAREST_PLAYER", power="high", \
message="The swarm buzzes angrily!"}, \
{trigger="ON_TAG_ADDED", trigger_tag="HEAT_SOURCE", action="EXPLODE", \
message="The swarm bursts into flames!"}], \
visual={visual_description="a dense swirling cloud of yellow and black striped bees with vibrating wings", \
size_category="small"}
Budget: tags 9/10, behaviors 6/8. Chases aggressively; if fire hits, HEAT_SOURCE tag → triggers EXPLODE chain reaction.

"healing mushroom" → name="Healing Shroom", tags=[LIVING, SOLID, GLOWING], \
behaviors=[{trigger="ON_CONTACT", action="HEAL", target="CONTACT_BODY", \
message="Restorative spores!"}, \
{trigger="ON_PROXIMITY", action="ADD_TAGS", target="CONTACT_BODY", \
tags_to_apply=["GLOWING"], message="You begin to glow..."}], \
visual={visual_description="a plump turquoise mushroom with a softly pulsing bioluminescent cap and white spots", \
size_category="small"}
Budget: tags 6/10, behaviors 4/8. Heals on touch and spreads GLOWING to nearby objects — not everything is combat.

"clockwork spider" → name="Clockwork Spider", tags=[SOLID, RIGID, SHARP, CONDUCTING, LIVING], \
behaviors=[{trigger="ALWAYS", action="PATROL", target="NEAREST_OBJECT", \
message="Tick-tick-tick..."}, \
{trigger="ON_DAMAGED", action="MOVE_AWAY", target="CONTACT_BODY", power="high", \
message="It skitters away!"}], \
visual={visual_description="a brass mechanical spider with visible gears, jointed steel legs, and glowing blue optical sensors", \
size_category="small"}
Budget: tags 9/10, behaviors 5/8. Patrols and flees when hurt — gives the object personality.
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
    _agent = Agent(
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
