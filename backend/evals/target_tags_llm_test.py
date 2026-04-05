"""Test: does the LLM reliably output target_tags on behaviors?

Calls the actual creator LLM with a modified prompt that includes target_tags,
then checks if the outputs make sense for a variety of creature descriptions.

Usage:
    cd backend && uv run python -m evals.target_tags_llm_test
"""

from __future__ import annotations

import asyncio
import json
import sys
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator
from pydantic_ai import Agent

from app.config import settings
from app.models.substances import Element, Substance
from app.models.tags import Tag


# Tags that make sense for behavior targeting
TARGETING_TAGS: frozenset[str] = frozenset({
    "HEAT_SOURCE", "LIVING", "HOSTILE", "FLYING", "WET",
    "FROZEN", "TOXIC", "METALLIC", "EXPLOSIVE", "ELECTRIC",
    "COLD", "ACIDIC",
})

TARGETING_TAG_HELP = """Available target_tags (use 0-2 per behavior, only when state matters):
  HEAT_SOURCE — target is on fire or emitting heat
  LIVING — target is a living creature
  HOSTILE — target is aggressive/dangerous
  FLYING — target is airborne
  WET — target is soaked or underwater
  FROZEN — target is frozen
  TOXIC — target is poisonous
  METALLIC — target is made of metal
  EXPLOSIVE — target is volatile
  ELECTRIC — target is electrified
  COLD — target is freezing
  ACIDIC — target is corrosive
Leave target_tags empty [] when targeting by identity only (food, treasure, etc.)"""


class BehaviorVerb(StrEnum):
    DESTROY = "destroy"
    EAT = "eat"
    INVESTIGATE = "investigate"
    FOLLOW = "follow"
    PROTECT = "protect"
    FLEE = "flee"


class BehaviorVerbSpecV2(BaseModel):
    verb: BehaviorVerb
    target: str = Field(min_length=1, max_length=100)
    target_tags: list[str] = Field(default_factory=list, max_length=2)

    @field_validator("target_tags", mode="before")
    @classmethod
    def validate_target_tags(cls, tags: list) -> list:
        from pydantic_ai import ModelRetry
        result = []
        for t in tags:
            val = str(t).strip().upper()
            if val and val not in TARGETING_TAGS:
                raise ModelRetry(
                    f"Target tag '{t}' is not valid.\n{TARGETING_TAG_HELP}"
                )
            if val:
                result.append(val)
        return result


class TestCreatorOutput(BaseModel):
    name: str
    substance: Substance
    element: Element | None = None
    tags: list[str] = Field(default_factory=list, max_length=3)
    behaviors: list[BehaviorVerbSpecV2] = Field(default_factory=list, max_length=4)


SYSTEM_PROMPT = """\
You are a game object designer for a 2D sandbox game. Given a player's description, \
create a game object by choosing a substance, optional element, tags, behaviors, and visual appearance.

## Substance (pick exactly 1)
| Substance | What it's for |
|-----------|--------------|
| metal | Swords, armor, coins, anvils, chains |
| wood | Furniture, sticks, barrels, trees |
| stone | Rocks, boulders, walls, statues |
| glass | Bottles, windows, crystal, mirrors |
| rubber | Balls, tires, erasers, bouncy things |
| bone | Skeletons, fossils, horns, tusks |
| ceramic | Pottery, tiles, bricks, porcelain |
| cloth | Flags, clothing, sails, carpets |
| water | Water bodies, rain, puddles |
| oil | Oil slicks, fuel, grease |
| slime | Slime blobs, ooze, goop |
| ice | Ice blocks, icicles, frost |
| lava | Lava flows, magma pools |
| fire | Flames, campfires, infernos |
| smoke | Smoke clouds, steam, mist |
| flesh | Creatures, monsters, animals, people |

## Tags (pick 0-3)
SHARP, HEAVY, LIGHT, BOUNCY, BREAKABLE, STICKY, REFLECTIVE, EXPLOSIVE, FLYING, LIVING, WET, HOSTILE

## Behaviors (0-4, for LIVING creatures)

Each behavior has:
- verb: destroy, eat, investigate, follow, protect, flee
- target: freeform text describing WHAT KIND of thing (identity/noun)
- target_tags: 0-2 tags the target must currently HAVE (state filter)

Use target_tags when the target's current STATE matters:
  HEAT_SOURCE — on fire        LIVING — alive           HOSTILE — aggressive
  FLYING ��� airborne            WET — soaked             FROZEN — frozen
  TOXIC — poisonous            METALLIC — made of metal EXPLOSIVE — volatile

Leave target_tags: [] when targeting by IDENTITY only (food, treasure, ships, etc.)

Examples:
- Firefighter: destroy, target: "fires and burning things", target_tags: ["HEAT_SOURCE"]
- Brave knight: destroy, target: "monsters and evil creatures", target_tags: ["HOSTILE"]
- Brave knight: protect, target: "villagers and innocents", target_tags: ["LIVING"]
- Hungry wolf: destroy, target: "small prey animals", target_tags: ["LIVING"]
- Hungry wolf: flee, target: "fire and heat", target_tags: ["HEAT_SOURCE"]
- Donut cop: eat, target: "food, especially donuts", target_tags: []
- Dragon: follow, target: "treasure and gold", target_tags: []
- Coward: flee, target: "anything dangerous", target_tags: ["HOSTILE"]

## Name
1-3 words.\
"""

TEST_CREATURES = [
    # Core cases
    "firefighter",
    "hungry wolf",
    "brave knight",
    "donut-obsessed cop",

    # Diet edge cases
    "vegetarian chef",
    "vampire",
    "zombie",
    "picky eater who only eats candy",
    "vegan activist",

    # State-dependent edge cases
    "ice wizard who hates fire",
    "rust monster that eats metal",
    "electric eel",
    "toxic waste cleanup robot",
    "ghost that haunts the living",

    # Identity-only edge cases
    "treasure-hunting dragon",
    "bookworm scholar",
    "pirate looking for ships",
    "dog that loves tennis balls",
    "magpie that collects shiny things",

    # Ambiguous / tricky
    "pacifist monk",
    "cowardly goblin",
    "friendly neighbourhood spider",
    "sentient sword",
    "curious baby",

    # Compound behaviors
    "guard dog",
    "mother hen protecting chicks",
    "predator stalking wounded prey",
    "arsonist",
    "healer who avoids combat",
]


async def main() -> None:
    # Use same model routing as real creator agent
    if settings.local_llm_url:
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        model = OpenAIChatModel(
            settings.llm_model,
            provider=OpenAIProvider(base_url=settings.local_llm_url, api_key="unused"),
        )
    else:
        model = settings.llm_model
    print(f"Model: {settings.llm_model}")  # noqa: T201
    if settings.local_llm_url:
        print(f"URL: {settings.local_llm_url}")  # noqa: T201
    print(f"Testing {len(TEST_CREATURES)} creatures\n")  # noqa: T201

    model_settings: dict = {"temperature": 0.8}
    if settings.local_llm_url:
        model_settings["extra_body"] = {
            "chat_template_kwargs": {"enable_thinking": True},
        }

    agent = Agent(
        model,
        output_type=TestCreatorOutput,
        retries=3,
        system_prompt=SYSTEM_PROMPT,
        model_settings=model_settings,
    )

    for creature in TEST_CREATURES:
        try:
            result = await agent.run(f"Create a game object for: {creature}")
            spec = result.output
            print(f"--- {creature} ---")  # noqa: T201
            print(f"  Name: {spec.name}, Substance: {spec.substance.value}")  # noqa: T201
            if spec.behaviors:
                for b in spec.behaviors:
                    tags_str = f", target_tags: {b.target_tags}" if b.target_tags else ""
                    print(f"  {b.verb.value} -> \"{b.target}\"{tags_str}")  # noqa: T201
            else:
                print("  (no behaviors)")  # noqa: T201
            print()  # noqa: T201
        except Exception as e:
            print(f"--- {creature} --- ERROR: {e}\n")  # noqa: T201


if __name__ == "__main__":
    asyncio.run(main())
