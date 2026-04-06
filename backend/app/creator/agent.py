from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

import structlog
from pydantic_ai import Agent

from app.config import settings

if TYPE_CHECKING:
    from pydantic_ai.models import Model
from app.engine.trait_deriver import compute_combat_profile, derive_traits, resolve_profile
from app.models.blueprint import (
    CreatorOutput,
    GameObjectBlueprint,
    VisualDescriptor,
)
from app.models.substances import Substance
from app.models.tag_behaviors import resolve_implied_behaviors

logger = structlog.get_logger()

# NOTE: Tag descriptions reflect interaction rules defined in engine/rules_data.py.
# If rules change, update descriptions here too.
SYSTEM_PROMPT = """\
You are a game object designer for a 2D sandbox game. Given a player's description, \
create a game object by choosing a substance, optional element, categories, tags, behaviors, and visual appearance.

## Substance (pick exactly 1)

The substance defines what the object is made of — its physics, durability, and base properties.

| Substance | What it's for | Auto-derived traits |
|-----------|--------------|-------------------|
| metal | Swords, armor, coins, anvils, chains | METALLIC, RIGID |
| wood | Furniture, sticks, barrels, trees | FLAMMABLE |
| stone | Rocks, boulders, walls, statues | RIGID, HEAVY |
| glass | Bottles, windows, crystal, mirrors | BREAKABLE, REFLECTIVE |
| rubber | Balls, tires, erasers, bouncy things | BOUNCY, INSULATING |
| bone | Skeletons, fossils, horns, tusks | RIGID |
| ceramic | Pottery, tiles, bricks, porcelain | BREAKABLE, INSULATING |
| cloth | Flags, clothing, sails, carpets | FLAMMABLE, LIGHT |
| water | Water bodies, rain, puddles | LIQUID, WET |
| oil | Oil slicks, fuel, grease | LIQUID, FLAMMABLE |
| slime | Slime blobs, ooze, goop | LIQUID, STICKY, TOXIC |
| ice | Ice blocks, icicles, frost | FROZEN, RIGID, COLD, BRITTLE |
| lava | Lava flows, magma pools | MOLTEN, LIQUID, HEAT_SOURCE |
| fire | Flames, campfires, infernos | GAS, HEAT_SOURCE, HOT |
| smoke | Smoke clouds, steam, mist | GAS, LIGHT |
| flesh | Creatures, monsters, animals, people | *(none)* |

## Element (pick 0 or 1)

An optional energy infusion that adds elemental properties.

| Element | Adds traits | Example |
|---------|------------|---------|
| burning | HEAT_SOURCE, HOT | fire sword, lava golem |
| electric | ELECTRIC | lightning rod, electric eel |
| magnetic | MAGNETIC | lodestone, magnetic crane |
| freezing | COLD | ice breath, frost wand |
| acidic | ACIDIC | acid spider, corrosive slime |
| toxic | TOXIC | poison dart, toxic mushroom |
| windy | WIND_SOURCE | fan, tornado, jet engine |

## Categories (pick 0-3 — what gameplay interactions this object supports)

CREATURE — a living being. Animals, monsters, people, insects. Auto-adds LIVING tag.
FOOD — something edible. Fruit, meat, potions, snacks.
WEAPON — made to deal damage. Swords, bombs, bows, traps.
PLANT — a plant or fungus. Trees, flowers, vines, mushrooms.
VALUABLE — precious or collectible. Treasure, coins, gems, rare items.
VEHICLE — something rideable or that carries things. Carts, boats, horses.
TOOL — a utility object. Buckets, ropes, levers, keys, shields.

Most objects have 0-1 categories. A wolf is [CREATURE]. A donut is [FOOD]. \
A fire sword is [WEAPON]. An oak tree is [PLANT]. A gold coin is [VALUABLE]. \
A cart is [VEHICLE]. A rope is [TOOL]. A campfire has none.

## Tags (pick 0-3 — physical modifiers the substance doesn't cover)

SHARP — cutting edge or point. Swords, thorns, claws.
HEAVY — dense and massive. Anvils, boulders. Immovable by wind.
LIGHT — very low mass. Feathers, paper, balloons. Blown by wind.
BOUNCY — elastic, high restitution. Springs, trampolines.
BREAKABLE — fragile, easily destroyed. Glass, pottery, eggshells.
STICKY — adhesive surface. Honey, tar, spider webs.
REFLECTIVE — mirror-like surface. Shields, polished metal.
EXPLOSIVE — volatile, detonates when damaged. Dynamite, grenades.
FLYING — defies gravity. Birds, drones, ghosts, balloons.
WET — damp or soaked. Amplifies electricity, freezes from cold.

## Behaviors (0-4, for CREATURE objects)

Each behavior has a verb, a target_tag (what to target), and a target_description (freeform reasoning). \
List behaviors in order of importance — first behavior takes precedence when multiple are active.

- **target_tag**: one of CREATURE, FOOD, WEAPON, PLANT, VALUABLE, VEHICLE, TOOL, HOSTILE, HEAT_SOURCE — or empty for "anything nearby"
- **target_description**: freeform text describing intent (for display, not used for matching)
- destroy/eat/flee MUST have a target_tag. investigate/follow/protect may leave it empty.

| Verb | What it does |
|------|-------------|
| destroy | Move toward target + melee attack |
| eat | Move toward target + consume (damage, heal self) |
| investigate | Move toward target slowly, stop at medium range |
| follow | Move toward target, maintain close distance |
| protect | Follow target + attack threats near it |
| flee | Move away from target at high speed |

Examples:
- A wolf: destroy target_tag=CREATURE "small prey animals", flee target_tag=HEAT_SOURCE "fire"
- A cop: eat target_tag=FOOD "donuts and snacks", destroy target_tag=HOSTILE "criminals"
- A dragon: destroy target_tag=CREATURE "anything alive", follow target_tag=VALUABLE "treasure and gold"
- A firefighter: destroy target_tag=HEAT_SOURCE "fires", protect target_tag=CREATURE "people"
- A villager: flee target_tag=HOSTILE "dangerous creatures"
- A curious cat: investigate "interesting objects nearby" (empty target_tag — investigates everything)

Non-CREATURE objects have no behaviors. A sword doesn't need behaviors — its tags handle everything.

## Visual Descriptor

- visual_description: 1-2 sentences — shape, material, colors, distinctive features. Describe the object, not a scene.
- size_category: tiny (coins, bugs) | small (swords, tools) | medium (crates, dogs) | large (doors, bears) | huge (trees, dragons)

## Name

1-3 words. Concise and evocative.

## Examples

"fire sword" → substance: metal, element: burning, categories: [WEAPON], tags: [SHARP], behaviors: [], \
visual: "a gleaming steel blade wreathed in dancing orange flames"

"rock" → substance: stone, element: null, categories: [], tags: [], behaviors: [], \
visual: "a rough gray boulder with moss patches"

"acid spider" → substance: flesh, element: acidic, categories: [CREATURE], tags: [], \
behaviors: [destroy target_tag=CREATURE "small insects and prey", flee target_tag=HEAT_SOURCE "fire"], \
visual: "a glossy black spider dripping green acid from its fangs"

"campfire" → substance: fire, element: null, categories: [], tags: [], behaviors: [], \
visual: "a crackling campfire with orange flames dancing over charred logs"

"donut" → substance: cloth, element: null, categories: [FOOD], tags: [], behaviors: [], \
visual: "a golden-brown glazed donut with colorful sprinkles"

"gold coin" → substance: metal, element: null, categories: [VALUABLE], tags: [LIGHT], behaviors: [], \
visual: "a shiny gold coin with an embossed crown on one side"

"brave knight" → substance: flesh, element: null, categories: [CREATURE], tags: [], \
behaviors: [destroy target_tag=HOSTILE "monsters and evil creatures", protect target_tag=CREATURE "villagers and innocents"], \
visual: "a stalwart knight in dented silver armor with a red plume"

"toxic mushroom" → substance: wood, element: toxic, categories: [FOOD, PLANT], tags: [BREAKABLE], \
behaviors: [], \
visual: "a bulbous purple mushroom with glowing green spots oozing spores"

"rope" → substance: cloth, element: null, categories: [TOOL], tags: [], behaviors: [], \
visual: "a coil of rough hemp rope with frayed ends"\
"""

_agent: Agent[None, CreatorOutput] | None = None


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


def _get_agent() -> Agent[None, CreatorOutput]:
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
    if settings.local_llm_url:
        model_settings["extra_body"] = {
            "top_k": settings.llm_top_k,
            "min_p": settings.llm_min_p,
            "repetition_penalty": settings.llm_repetition_penalty,
            "chat_template_kwargs": {"enable_thinking": not settings.local_llm_thinking_disabled},
        }
    _agent = Agent(  # type: ignore[call-overload]
        _build_model(),
        output_type=CreatorOutput,
        retries=3,
        system_prompt=SYSTEM_PROMPT,
        model_settings=model_settings,
    )
    logger.info("agent_created", model=settings.llm_model)
    return _agent


async def create_object(description: str) -> GameObjectBlueprint:
    """Create a game object from a player's text description.

    Pipeline: LLM → resolve_implied_behaviors → derive_traits → resolve_profile →
    compute_combat → assemble blueprint.
    """
    t0 = time.monotonic()
    try:
        agent = _get_agent()
        result = await agent.run(f"Create a game object for: {description}")
        spec = result.output

        # Resolve implied behaviors (CREATURE with no behaviors → investigate)
        behaviors = resolve_implied_behaviors(spec.categories, spec.behaviors)

        # Derive internal traits (substance + element + tags + behaviors + categories)
        behavior_verbs = [b.verb.value for b in behaviors]
        traits = derive_traits(
            spec.substance, spec.element, spec.tags, behavior_verbs, categories=spec.categories
        )

        # Compute profiles
        profile = resolve_profile(spec.substance, spec.element, traits)
        combat = compute_combat_profile(profile)

        # Compile behaviors: self-contained dicts with verb + target_tag
        compiled_behaviors = []
        for b in behaviors:
            compiled_behaviors.append({
                "verb": b.verb.value,
                "target_description": b.target_description,
                "target_tag": b.target_tag,
            })

        elapsed = time.monotonic() - t0
        logger.info(
            "llm_create_success",
            object_name=spec.name,
            substance=spec.substance.value,
            element=spec.element.value if spec.element else None,
            tag_count=len(traits),
            behavior_count=len(behaviors),
            elapsed=round(elapsed, 2),
        )
    except Exception as e:
        elapsed = time.monotonic() - t0
        logger.error("llm_create_failed", elapsed=round(elapsed, 2), error=str(e))
        words = description.strip().split()
        fallback_name = " ".join(w.capitalize() for w in words[:2]) if words else "Object"
        spec = CreatorOutput(
            name=f"Mysterious {fallback_name}",
            substance=Substance.STONE,
            element=None,
            categories=[],
            tags=[],
            behaviors=[],
            visual_descriptor=VisualDescriptor(
                visual_description="a mysterious glowing gray stone cube with sparkling flecks",
                size_category="medium",
            ),
        )
        traits = derive_traits(spec.substance, spec.element, spec.tags)
        profile = resolve_profile(spec.substance, spec.element, traits)
        combat = compute_combat_profile(profile)
        behaviors = []
        compiled_behaviors = []

    # Durability from profile
    starting_durability = int(profile.durability)

    blueprint = GameObjectBlueprint(
        id=str(uuid.uuid4()),
        name=spec.name,
        description=description,
        substance=spec.substance,
        element=spec.element,
        categories=[c.value for c in spec.categories],
        tags=traits,
        behaviors=behaviors,
        visual_descriptor=spec.visual_descriptor,
        substance_profile=profile.model_dump(mode="json"),
        combat_profile=combat,
        compiled_behaviors=compiled_behaviors,
        starting_durability=starting_durability,
    )
    logger.debug(
        "blueprint_created",
        object_id=blueprint.id,
        substance=blueprint.substance.value,
        tag_count=len(blueprint.tags),
        behavior_count=len(blueprint.behaviors),
        starting_durability=blueprint.starting_durability,
    )
    return blueprint
