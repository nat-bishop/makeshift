from __future__ import annotations

import time
import uuid

import structlog
from pydantic_ai import Agent

from app.models.blueprint import CreatorOutput, GameObjectBlueprint, VisualDescriptor
from app.models.tags import Tag

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are a game object designer for a 2D sandbox game. Given a player's text description, \
you create a game object by choosing a name, assigning tags, and describing its visual appearance.

## Available Tags (33 total)

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
- CLIMBABLE: Can be climbed by the player
- BREAKABLE: Can be destroyed by damage (lower durability)

**Interaction:**
- WEARABLE: Can be equipped by the player
- TOOL: Can be wielded as a tool/weapon by the player

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
Cost 2: HEAVY, FROZEN, HOT, SHARP, STICKY, REFLECTIVE, BOUNCY, CLIMBABLE, WEARABLE, TOOL, FLOATING, GLOWING, CONDUCTING, INSULATING
Cost 3: HEAT_SOURCE, MAGNETIC, WIND_SOURCE, LIVING
Cost 4: ELECTRIC, CORROSIVE, TOXIC, MOLTEN
Cost 5: EXPLOSIVE

## Contradictions (cannot coexist)

FROZEN↔MOLTEN, FROZEN↔HOT, COLD↔HOT, COLD↔MOLTEN, HEAVY↔LIGHT, LIQUID↔RIGID, \
GAS↔RIGID, GAS↔HEAVY, SOLID↔LIQUID, SOLID↔GAS, LIQUID↔GAS, STICKY↔SLIPPERY

## Rules

1. Choose 2-6 tags that best represent the object. Total cost must not exceed 10.
2. Never pair contradictory tags.
3. Think about gameplay affordances: what can the player DO with this object? Favor tags that enable interesting interactions.
4. The name should be concise (1-3 words).

## Visual Descriptor

- base_form: The basic shape/silhouette (e.g., "sword", "shield", "plank", "sphere", "cube", "bottle", "axe")
- material: What it appears made of (e.g., "metal", "wood", "crystal", "ice", "stone", "cloth")
- color_primary: Primary color as hex (e.g., "#FF4444")
- color_secondary: Secondary/accent color as hex (e.g., "#222222")
- visual_effects: List of visual effects like "glowing", "flaming", "sparkling", "dripping", "smoking", "frozen_particles"
- size_category: One of "tiny", "small", "medium", "large", "huge" — pick based on what the object naturally is

## Examples

"fire sword" → name="Fire Sword", tags=[SOLID, RIGID, SHARP, HEAT_SOURCE, TOOL], \
visual={base_form="sword", material="metal", color_primary="#CC3300", color_secondary="#FF6600", \
visual_effects=["flaming"], size_category="medium"}

"ice wall" → name="Ice Wall", tags=[SOLID, RIGID, FROZEN, COLD, BREAKABLE], \
visual={base_form="wall", material="ice", color_primary="#88CCFF", color_secondary="#FFFFFF", \
visual_effects=["frozen_particles"], size_category="large"}
"""

_agent: Agent[None, CreatorOutput] | None = None


def _get_agent() -> Agent[None, CreatorOutput]:
    global _agent
    if _agent is None:
        from app.config import settings

        _agent = Agent(
            settings.llm_model,
            output_type=CreatorOutput,
            retries=3,
            system_prompt=SYSTEM_PROMPT,
        )
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
        result = await agent.run(
            f"Create a game object for: {description}"
        )
        creator_output = result.output
        elapsed = time.monotonic() - t0
        usage = result.usage()
        logger.info(
            "llm_create_success",
            object_name=creator_output.name,
            tag_count=len(creator_output.tags),
            elapsed=round(elapsed, 2),
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
        )
    except Exception as e:
        elapsed = time.monotonic() - t0
        logger.error("llm_create_failed", elapsed=round(elapsed, 2), error=str(e))
        # Fallback: generic object with player's typed description as name
        words = description.strip().split()
        fallback_name = " ".join(w.capitalize() for w in words[:3]) if words else "Mysterious Object"
        creator_output = CreatorOutput(
            name=f"Mysterious {fallback_name}",
            tags=[Tag.SOLID, Tag.RIGID],
            visual_descriptor=VisualDescriptor(
                base_form="cube",
                material="stone",
                color_primary="#888888",
                color_secondary="#666666",
                visual_effects=["sparkling"],
                size_category="medium",
            ),
        )

    blueprint = GameObjectBlueprint(
        id=str(uuid.uuid4()),
        name=creator_output.name,
        description=description,
        tags=creator_output.tags,
        visual_descriptor=creator_output.visual_descriptor,
    )
    return blueprint
