"""Curated test cases for creator agent evaluation.

Designed to mimic real player input — a mix of terse keywords,
full sentences, mundane objects, wild ideas, and adversarial edge cases.
50 cases covering all 31 tags, 9 behavior triggers, and 11 actions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator


@dataclass(frozen=True)
class CaseMeta:
    category: str
    expected_tags: list[str] = field(default_factory=list)
    notes: str = ""


# Type alias for readability
CreatorCase = Case[str, str, CaseMeta]

EVAL_CASES: list[CreatorCase] = [
    # =========================================================================
    # Mundane objects — everyday items players WILL try
    # =========================================================================
    Case(
        name="rock",
        inputs="rock",
        metadata=CaseMeta(
            category="mundane",
            expected_tags=["SOLID", "RIGID", "HEAVY"],
            notes="The simplest possible input. Should still produce a valid, playable object.",
        ),
    ),
    Case(
        name="wooden chair",
        inputs="wooden chair",
        metadata=CaseMeta(
            category="mundane",
            expected_tags=["SOLID", "RIGID", "FLAMMABLE"],
            notes="Everyday furniture. Tests if FLAMMABLE gets picked up from 'wooden'.",
        ),
    ),
    Case(
        name="bucket of water",
        inputs="bucket of water",
        metadata=CaseMeta(
            category="mundane",
            expected_tags=["LIQUID", "COLD"],
            notes="Container + liquid. Interesting tagging challenge — is it SOLID or LIQUID?",
        ),
    ),
    Case(
        name="banana",
        inputs="banana",
        metadata=CaseMeta(
            category="mundane",
            expected_tags=["SOLID", "LIGHT", "SLIPPERY"],
            notes="Meme object. Tests if SLIPPERY gets picked up from banana association.",
        ),
    ),
    Case(
        name="glass bottle",
        inputs="a glass bottle, like an empty potion bottle that breaks easily",
        metadata=CaseMeta(
            category="mundane",
            expected_tags=["SOLID", "RIGID", "BREAKABLE"],
            notes="Tests BREAKABLE from 'breaks easily'. Player framing as game item.",
        ),
    ),
    Case(
        name="hot coal",
        inputs="a glowing piece of coal fresh out of a fire, still super hot to the touch",
        metadata=CaseMeta(
            category="mundane",
            expected_tags=["SOLID", "HOT", "GLOWING"],
            notes="Tests HOT(2) distinct from HEAT_SOURCE(3). Sensory description.",
        ),
    ),
    Case(
        name="giant boulder",
        inputs="a massive boulder the size of a house that just crushes anything in its path",
        metadata=CaseMeta(
            category="mundane",
            expected_tags=["SOLID", "HEAVY", "RIGID"],
            notes="Tests 'huge' size category. Player implying damage-on-contact from mass.",
        ),
    ),
    Case(
        name="tiny pebble",
        inputs="the worlds smallest pebble",
        metadata=CaseMeta(
            category="mundane",
            expected_tags=["SOLID", "LIGHT"],
            notes="Tests 'tiny' size. Minimal budget (cost 2). Superlative phrasing.",
        ),
    ),
    # =========================================================================
    # Weapons — combat objects, classic game items
    # =========================================================================
    Case(
        name="fire sword",
        inputs="fire sword",
        metadata=CaseMeta(
            category="weapon",
            expected_tags=["SOLID", "SHARP", "HEAT_SOURCE"],
            notes="Baseline in-prompt example.",
        ),
    ),
    Case(
        name="sword",
        inputs="sword",
        metadata=CaseMeta(
            category="weapon",
            expected_tags=["SOLID", "SHARP"],
            notes="Bare minimum single word. Tests defaults when given nothing to work with.",
        ),
    ),
    Case(
        name="time bomb",
        inputs="time bomb that blows up after a few seconds",
        metadata=CaseMeta(
            category="weapon",
            expected_tags=["SOLID", "EXPLOSIVE"],
            notes="Player expects ON_TIMER -> EXPLODE. Tests behavior trigger selection.",
        ),
    ),
    Case(
        name="homing missile",
        inputs="a missile that locks onto the nearest enemy and chases them down, like those heat seeking ones from movies",
        metadata=CaseMeta(
            category="weapon",
            expected_tags=["SOLID", "EXPLOSIVE"],
            notes="Tests MOVE_TOWARD -> NEAREST_LIVING. Pop culture framing.",
        ),
    ),
    Case(
        name="rubber ball from hell",
        inputs="a bouncy ball but its like possessed or something, it just keeps bouncing around faster and faster and if it hits you it really hurts",
        metadata=CaseMeta(
            category="weapon",
            expected_tags=["SOLID", "BOUNCY", "LIGHT"],
            notes="Tests BOUNCY tag with HOSTILE for contact damage. Comedic escalation.",
        ),
    ),
    Case(
        name="firework",
        inputs="a firework that goes off the second you place it",
        metadata=CaseMeta(
            category="weapon",
            expected_tags=["SOLID", "EXPLOSIVE", "LIGHT"],
            notes="Tests ON_CREATE trigger. Player describing instant activation.",
        ),
    ),
    # =========================================================================
    # Traps — contact/proximity triggers, chain reactions
    # =========================================================================
    Case(
        name="explosive barrel",
        inputs="explosive barrel",
        metadata=CaseMeta(
            category="trap",
            expected_tags=["SOLID", "FLAMMABLE", "EXPLOSIVE"],
            notes="Classic chain-reaction setup. EXPLOSIVE=5 budget pressure.",
        ),
    ),
    Case(
        name="glass cannon",
        inputs="a crystal ball that just floats there and looks pretty but if anything bumps into it it shatters into a million sharp pieces and everything nearby gets cut up",
        metadata=CaseMeta(
            category="trap",
            expected_tags=["SOLID", "BREAKABLE", "SHARP", "GLOWING", "FLOATING"],
            notes="Long description with ON_DAMAGED -> EXPLODE. Tests BREAKABLE + SHARP.",
        ),
    ),
    Case(
        name="sticky honey trap",
        inputs="imagine like a big glob of honey that just sits there and anything that walks into it gets completely stuck and cant move",
        metadata=CaseMeta(
            category="trap",
            expected_tags=["STICKY", "LIQUID"],
            notes="Conversational 'imagine like'. Tests STICKY tag and contact-based trapping.",
        ),
    ),
    Case(
        name="death flower",
        inputs="a pretty flower but when you destroy it a cloud of toxic gas comes out and poisons everything in the area, like a trap you know",
        metadata=CaseMeta(
            category="trap",
            expected_tags=["LIVING", "TOXIC"],
            notes="Tests ON_DESTROY -> ADD_TAGS(TOXIC) or EXPLODE. Player explaining the gimmick.",
        ),
    ),
    # =========================================================================
    # Creatures — LIVING tag, movement, autonomous behaviors
    # =========================================================================
    Case(
        name="acid spider",
        inputs="a little spider that spits acid at you if you get too close",
        metadata=CaseMeta(
            category="creature",
            expected_tags=["LIVING", "CORROSIVE"],
            notes="Explicit behavior hint. Should map to ON_PROXIMITY -> SPAWN_PROJECTILE or CORROSIVE tag.",
        ),
    ),
    Case(
        name="friendly dog",
        inputs="friendly dog",
        metadata=CaseMeta(
            category="creature",
            expected_tags=["LIVING", "LIGHT"],
            notes="Non-hostile creature. Tests if LLM avoids combat behaviors for something friendly.",
        ),
    ),
    Case(
        name="lava monster",
        inputs="a lava monster that chases you around and sets everything on fire",
        metadata=CaseMeta(
            category="creature",
            expected_tags=["LIVING", "MOLTEN", "HEAT_SOURCE"],
            notes="MOLTEN(4)+LIVING(3)+HEAT_SOURCE(3)=10, exactly at budget. MOVE_TOWARD behavior.",
        ),
    ),
    Case(
        name="angry bunny",
        inputs="a bunny that gets more and more angry as it sees the player and eventually just charges at them trying to bite",
        metadata=CaseMeta(
            category="creature",
            expected_tags=["LIVING", "LIGHT"],
            notes="Long narrative with escalating behavior. Tests ON_PROXIMITY -> MOVE_TOWARD + HOSTILE tag.",
        ),
    ),
    Case(
        name="electric jellyfish",
        inputs="one of those deep sea jellyfish that glows in the dark and shocks anything that gets close to its tentacles",
        metadata=CaseMeta(
            category="creature",
            expected_tags=["LIVING", "ELECTRIC", "GLOWING"],
            notes="Nature reference. Tests ELECTRIC(4)+LIVING(3)+GLOWING(2)=9. ELECTRIC tag handles shock damage.",
        ),
    ),
    Case(
        name="wind spirit",
        inputs="a little tornado spirit, its alive and it blows everything around it away, like leaves and small objects just go flying",
        metadata=CaseMeta(
            category="creature",
            expected_tags=["LIVING", "WIND_SOURCE", "FLOATING"],
            notes="Tests WIND_SOURCE(3)+LIVING(3)+FLOATING(2)=8. APPLY_FORCE behavior.",
        ),
    ),
    Case(
        name="toxic frog",
        inputs="a cute little frog but its actually super poisonous, if you touch it or get too close the poison seeps out and hurts you",
        metadata=CaseMeta(
            category="creature",
            expected_tags=["LIVING", "TOXIC"],
            notes="Tests TOXIC(4)+LIVING(3)=7. TOXIC tag handles poison damage automatically.",
        ),
    ),
    Case(
        name="mirror golem",
        inputs="a golem made entirely out of mirrors, it reflects everything back at you - fire, lightning, whatever you throw at it bounces right back",
        metadata=CaseMeta(
            category="creature",
            expected_tags=["SOLID", "LIVING", "REFLECTIVE", "RIGID"],
            notes="Tests REFLECTIVE(2)+LIVING(3)+SOLID(1)+RIGID(1)=7. Defensive creature.",
        ),
    ),
    Case(
        name="lasso vine",
        inputs="a living vine that reaches out and wraps around things nearby, pulling them in closer like a lasso",
        metadata=CaseMeta(
            category="creature",
            expected_tags=["LIVING", "FLEXIBLE", "STICKY"],
            notes="Tests FLEXIBLE + STICKY. ON_PROXIMITY -> ATTRACT or APPLY_FORCE.",
        ),
    ),
    Case(
        name="cowardly slime",
        inputs="a little slime creature thats really scared of everything, the moment anything comes near it just books it in the other direction as fast as it can",
        metadata=CaseMeta(
            category="creature",
            expected_tags=["LIVING", "SLIPPERY"],
            notes="Tests MOVE_AWAY behavior. Long narrative emphasizing flee mechanic.",
        ),
    ),
    Case(
        name="phoenix egg",
        inputs="an egg that looks totally normal but when its about to break it suddenly bursts into flames and a firebird comes out, or at least thats the idea",
        metadata=CaseMeta(
            category="creature",
            expected_tags=["SOLID", "LIVING"],
            notes="Tests ON_HEALTH_LOW -> ADD_TAGS(HEAT_SOURCE). Player hedging ('thats the idea').",
        ),
    ),
    Case(
        name="patrol bot",
        inputs="a little robot that just walks back and forth guarding an area, and if it spots you it starts shooting",
        metadata=CaseMeta(
            category="creature",
            expected_tags=["SOLID", "LIVING"],
            notes="Tests PATROL + ON_PROXIMITY -> SPAWN_PROJECTILE. Multi-behavior creature.",
        ),
    ),
    Case(
        name="electric lava golem",
        inputs="a golem thats made of lava and shoots lightning, like the final boss of a video game",
        metadata=CaseMeta(
            category="creature",
            expected_tags=["LIVING", "MOLTEN", "ELECTRIC"],
            notes="LIVING(3)+MOLTEN(4)+ELECTRIC(4)=11 exceeds budget. Tests constraint handling.",
        ),
    ),
    # =========================================================================
    # Abstract / wild — creative mapping, emotions, pop culture
    # =========================================================================
    Case(
        name="the sun",
        inputs="the sun",
        metadata=CaseMeta(
            category="abstract",
            expected_tags=["HEAT_SOURCE", "GLOWING"],
            notes="Absurdly large concept. Tests how it gets scoped into a game object.",
        ),
    ),
    Case(
        name="tiny black hole",
        inputs="a tiny black hole that sucks everything in",
        metadata=CaseMeta(
            category="abstract",
            expected_tags=["MAGNETIC", "HEAVY"],
            notes="Sci-fi concept. Should use ATTRACT behavior.",
        ),
    ),
    Case(
        name="sadness",
        inputs="sadness",
        metadata=CaseMeta(
            category="abstract",
            expected_tags=["GLOWING"],
            notes="Pure abstract emotion. No obvious physical form. Tests creative mapping.",
        ),
    ),
    Case(
        name="indiana jones boulder",
        inputs="that one boulder from indiana jones",
        metadata=CaseMeta(
            category="abstract",
            expected_tags=["SOLID", "HEAVY", "RIGID"],
            notes="Pop culture reference. Should produce a large rolling boulder.",
        ),
    ),
    Case(
        name="frozen fire",
        inputs="frozen fire",
        metadata=CaseMeta(
            category="abstract",
            expected_tags=[],
            notes="FROZEN + HEAT_SOURCE is a tag contradiction. Tests how LLM resolves impossible combos.",
        ),
    ),
    # =========================================================================
    # Adversarial — bad input, typos, rambling, conversational
    # =========================================================================
    Case(
        name="a thing",
        inputs="a thing",
        metadata=CaseMeta(
            category="adversarial",
            expected_tags=["SOLID"],
            notes="Maximally vague input. Should still produce something valid and interesting.",
        ),
    ),
    Case(
        name="indestructible wall",
        inputs="a wall that literally nothing can break, like at all",
        metadata=CaseMeta(
            category="adversarial",
            expected_tags=["SOLID", "RIGID", "HEAVY"],
            notes="Player asking for OP object with emphasis style. Tests budget constraints.",
        ),
    ),
    Case(
        name="fiar swrod",
        inputs="fiar swrod",
        metadata=CaseMeta(
            category="adversarial",
            expected_tags=["SOLID", "SHARP", "HEAT_SOURCE"],
            notes="Deliberate typo of 'fire sword'. Tests LLM's typo tolerance.",
        ),
    ),
    Case(
        name="shield request",
        inputs="hey can you make me like a shield or something? nothing fancy just something to block stuff",
        metadata=CaseMeta(
            category="adversarial",
            expected_tags=["SOLID", "RIGID"],
            notes="Question format, conversational. Tests extraction from casual speech.",
        ),
    ),
    Case(
        name="rambling glowing sword",
        inputs="ok so I want like a really cool sword right, it should be super sharp and glow like a lightsaber and maybe be on fire or something idk, oh and make it big, like really big, biggest sword youve ever seen",
        metadata=CaseMeta(
            category="adversarial",
            expected_tags=["SOLID", "SHARP", "GLOWING"],
            notes="Long rambling with contradictory size demands. Tests feature extraction from noise.",
        ),
    ),
    Case(
        name="not heavy floaty thing",
        inputs="something light that floats and definitely isnt heavy at all, like a feather but cooler",
        metadata=CaseMeta(
            category="adversarial",
            expected_tags=["LIGHT", "FLOATING"],
            notes="Negation. Tests if LLM avoids HEAVY and picks up LIGHT + FLOATING.",
        ),
    ),
    # =========================================================================
    # Environment — weather, area hazards
    # =========================================================================
    Case(
        name="acid rain cloud",
        inputs="a cloud that rains acid on everything below it",
        metadata=CaseMeta(
            category="environment",
            expected_tags=["GAS", "FLOATING", "CORROSIVE"],
            notes="Environmental hazard. GAS+FLOATING+CORROSIVE. Tag handles acid damage automatically.",
        ),
    ),
    Case(
        name="ice shield",
        inputs="an ice shield that freezes stuff when they touch it",
        metadata=CaseMeta(
            category="defensive",
            expected_tags=["SOLID", "RIGID", "FROZEN"],
            notes="Full sentence with mechanic hint. Tests if LLM follows the instruction.",
        ),
    ),
    # =========================================================================
    # Utility — tools, helpers, mechanical objects
    # =========================================================================
    Case(
        name="magnet",
        inputs="magnet",
        metadata=CaseMeta(
            category="utility",
            expected_tags=["SOLID", "MAGNETIC"],
            notes="Single word, obvious ATTRACT behavior expected.",
        ),
    ),
    Case(
        name="healing mushroom",
        inputs="I want a healing mushroom that heals you when you kick it",
        metadata=CaseMeta(
            category="utility",
            expected_tags=["LIVING", "SOLID"],
            notes="Player speaking naturally with 'I want'. ON_DAMAGED -> HEAL -> CONTACT_BODY.",
        ),
    ),
    Case(
        name="conductor rod",
        inputs="a metal rod that conducts electricity between things, like if you put it between a tesla coil and a robot it would zap the robot",
        metadata=CaseMeta(
            category="utility",
            expected_tags=["SOLID", "CONDUCTING", "RIGID"],
            notes="Tests CONDUCTING tag. Player explaining the mechanic they want.",
        ),
    ),
    Case(
        name="spring trap",
        inputs="one of those cartoon spring platforms that launches you way up in the air when you step on it, BOING",
        metadata=CaseMeta(
            category="utility",
            expected_tags=["SOLID", "BOUNCY"],
            notes="Tests ON_CONTACT -> APPLY_FORCE. Cartoon reference with sound effect.",
        ),
    ),
    Case(
        name="campfire",
        inputs="just a regular campfire, you know, logs burning, keeps you warm, maybe heals you a little if you stand near it",
        metadata=CaseMeta(
            category="utility",
            expected_tags=["SOLID", "HEAT_SOURCE", "GLOWING"],
            notes="Tests field-based healing behavior. ON_PROXIMITY -> HEAL.",
        ),
    ),
    # =========================================================================
    # Defensive — protective, reflective, insulating
    # =========================================================================
    Case(
        name="rubber armor",
        inputs="armor made of rubber so electricity cant hurt you when youre wearing it, like an insulator",
        metadata=CaseMeta(
            category="defensive",
            expected_tags=["SOLID", "FLEXIBLE", "INSULATING"],
            notes="Tests INSULATING. Player explicitly naming the mechanic.",
        ),
    ),
]


def build_dataset(evaluators: list[Evaluator] = ()) -> Dataset[str, str, CaseMeta]:
    """Build a Dataset from the eval cases with the given evaluators."""
    return Dataset(
        cases=EVAL_CASES,
        evaluators=list(evaluators),
    )
