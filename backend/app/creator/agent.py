from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

import structlog
from pydantic_ai import Agent

from app.config import settings

if TYPE_CHECKING:
    from pydantic_ai.models import Model
from app.embeddings import compute_object_embeddings
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
create a game object by choosing a substance, optional element, tags, behaviors, and visual appearance.

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
| flesh | Creatures, monsters, animals, people | *(none — add LIVING)* |

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

## Tags (pick 0-3 — independent modifiers the substance doesn't cover)

SHARP — cutting edge or point. Swords, thorns, claws.
HEAVY — dense and massive. Anvils, boulders. Immovable by wind.
LIGHT — very low mass. Feathers, paper, balloons. Blown by wind.
BOUNCY — elastic, high restitution. Springs, trampolines.
BREAKABLE — fragile, easily destroyed. Glass, pottery, eggshells.
STICKY — adhesive surface. Honey, tar, spider webs.
REFLECTIVE — mirror-like surface. Shields, polished metal.
EXPLOSIVE — volatile, detonates when damaged. Dynamite, grenades.
FLYING — defies gravity. Birds, drones, ghosts, balloons.
LIVING — biological creature. Animals, monsters, insects. NOT machines.
WET — damp or soaked. Amplifies electricity, freezes from cold.
HOSTILE — aggressive. Deals damage to nearby creatures. Use for non-living threats (spike traps, force fields). Living creatures get HOSTILE auto-derived from destroy behavior.

## Behaviors (0-4, for LIVING creatures)

Each behavior is a verb + freeform target describing what/who this creature cares about. \
List behaviors in order of importance — first behavior takes precedence when multiple are active.

| Verb | What it does |
|------|-------------|
| destroy | Move toward target + melee attack |
| eat | Move toward target + consume (damage, heal self) |
| investigate | Move toward target slowly, stop at medium range |
| follow | Move toward target, maintain close distance |
| protect | Follow target + attack threats near it |
| flee | Move away from target at high speed |

Examples:
- A donut-obsessed cop: eat → "food, especially donuts", destroy → "criminals", flee → "ghosts"
- A brave warrior: destroy → "enemies and monsters", protect → "innocent people"
- A cowardly villager: flee → "anything dangerous", investigate → "interesting things"
- A hungry wolf: destroy → "small prey animals", flee → "fire and loud noises"

Non-living objects usually have no behaviors. A sword doesn't need behaviors — its tags handle everything.

## Visual Descriptor

- visual_description: 1-2 sentences — shape, material, colors, distinctive features. Describe the object, not a scene.
- size_category: tiny (coins, bugs) | small (swords, tools) | medium (crates, dogs) | large (doors, bears) | huge (trees, dragons)

## Name

1-3 words. Concise and evocative.

## Examples

"fire sword" → substance: metal, element: burning, tags: [SHARP], behaviors: [], \
visual: "a gleaming steel blade wreathed in dancing orange flames"

"rock" → substance: stone, element: null, tags: [], behaviors: [], \
visual: "a rough gray boulder with moss patches"

"acid spider" → substance: flesh, element: acidic, tags: [LIVING], \
behaviors: [destroy → "small insects and prey", flee → "fire and larger creatures"], \
visual: "a glossy black spider dripping green acid from its fangs"

"campfire" → substance: fire, element: null, tags: [], behaviors: [], \
visual: "a crackling campfire with orange flames dancing over charred logs"

"ice wall" → substance: ice, element: null, tags: [], behaviors: [], \
visual: "a towering wall of translucent blue ice with frost crystals"

"rubber duck" → substance: rubber, element: null, tags: [LIGHT], behaviors: [], \
visual: "a cheerful yellow rubber duck with an orange beak"

"brave knight" → substance: flesh, element: null, tags: [LIVING], \
behaviors: [destroy → "monsters and evil creatures", protect → "villagers and innocents"], \
visual: "a stalwart knight in dented silver armor with a red plume"

"toxic mushroom" → substance: wood, element: toxic, tags: [BREAKABLE], behaviors: [], \
visual: "a bulbous purple mushroom with glowing green spots oozing spores"\
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

    Pipeline: LLM → derive_traits → resolve_profile → compute_combat →
    compute_embeddings → assemble blueprint.
    """
    t0 = time.monotonic()
    try:
        agent = _get_agent()
        result = await agent.run(f"Create a game object for: {description}")
        spec = result.output

        # Resolve implied behaviors
        behaviors = resolve_implied_behaviors(spec.tags, spec.behaviors)

        # Derive internal traits
        behavior_verbs = [b.verb.value for b in behaviors]
        traits = derive_traits(spec.substance, spec.element, spec.tags, behavior_verbs)

        # Compute profiles
        profile = resolve_profile(spec.substance, spec.element, traits)
        combat = compute_combat_profile(profile)

        # Compute embeddings
        identity_emb, behavior_embs = await compute_object_embeddings(
            name=spec.name,
            visual_description=spec.visual_descriptor.visual_description,
            size_category=spec.visual_descriptor.size_category,
            tags=traits,
            behavior_targets=[b.target for b in behaviors],
        )

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
        identity_emb = []
        behavior_embs = []

    # Durability from profile
    starting_durability = int(profile.durability)

    blueprint = GameObjectBlueprint(
        id=str(uuid.uuid4()),
        name=spec.name,
        description=description,
        substance=spec.substance,
        element=spec.element,
        tags=traits,
        behaviors=behaviors,
        visual_descriptor=spec.visual_descriptor,
        substance_profile=profile.model_dump(mode="json"),
        combat_profile=combat,
        identity_embedding=identity_emb,
        behavior_embeddings=behavior_embs,
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
