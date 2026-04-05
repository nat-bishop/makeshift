"""Prompt variant registry for A/B evaluation.

Add a new variant by adding a key to PROMPT_VARIANTS.
The key is used as the variant name in CLI args and reports.

Split variants use two prompts (classify + creative) and are
registered in SPLIT_VARIANTS separately.
"""

from __future__ import annotations

from app.creator.agent import SYSTEM_PROMPT

# ---------------------------------------------------------------------------
# Single-call variants
# ---------------------------------------------------------------------------

PROMPT_VARIANTS: dict[str, str] = {
    "baseline": SYSTEM_PROMPT,
    "compact": """\
You are a game object designer for a 2D sandbox game. Given a player's description, \
create a game object by choosing a substance, optional element, tags, behaviors, and visual.

## Substance (1 of 16)
metal, wood, stone, glass, rubber, bone, ceramic, cloth, water, oil, slime, ice, lava, fire, smoke, flesh

## Element (0 or 1)
burning, electric, magnetic, freezing, acidic, toxic, windy

## Tags (0-3 independent modifiers)
SHARP, HEAVY, LIGHT, BOUNCY, BREAKABLE, STICKY, REFLECTIVE, EXPLOSIVE, FLYING, LIVING, WET, HOSTILE

LIVING = biological creature. HOSTILE = aggressive (auto-derived from destroy verb for creatures).

## Behaviors (0-4, for LIVING creatures)
verb + freeform target. List in priority order.
Verbs: destroy, eat, investigate, follow, protect, flee

## Visual
visual_description: 1-2 sentences (shape, material, colors). size_category: tiny/small/medium/large/huge

## Name
1-3 words.

## Examples
"fire sword" → metal, burning, [SHARP], "a gleaming blade wreathed in flame"
"rock" → stone, null, [], "a rough gray boulder with moss patches"
"acid spider" → flesh, acidic, [LIVING], behaviors: [destroy→"insects", flee→"fire"], \
"a glossy black spider dripping green acid"\
""",
}


# ---------------------------------------------------------------------------
# Split variants: (classify_prompt, creative_prompt)
# ---------------------------------------------------------------------------

CLASSIFY_PROMPT = """\
You are a game object classifier for a 2D sandbox game. Given a player's description, \
decide what the object is made of and what properties it has.

Pick:
1. **substance** (exactly 1): metal, wood, stone, glass, rubber, bone, ceramic, cloth, \
water, oil, slime, ice, lava, fire, smoke, flesh
2. **element** (0 or 1): burning, electric, magnetic, freezing, acidic, toxic, windy
3. **tags** (0-3): SHARP, HEAVY, LIGHT, BOUNCY, BREAKABLE, STICKY, REFLECTIVE, EXPLOSIVE, \
FLYING, LIVING, WET, HOSTILE
4. **name**: 1-3 words

Substance determines physics (mass, durability, friction). Element adds energy properties. \
Tags are independent modifiers the substance doesn't cover. LIVING = biological creature. \
HOSTILE = aggressive non-living threat (creatures get HOSTILE from destroy behaviors).

Examples:
"fire sword" → name: Fire Sword, substance: metal, element: burning, tags: [SHARP]
"rock" → name: Rock, substance: stone, element: null, tags: []
"acid spider" → name: Acid Spider, substance: flesh, element: acidic, tags: [LIVING]
"rubber duck" → name: Rubber Duck, substance: rubber, element: null, tags: [LIGHT]\
"""

CREATIVE_PROMPT = """\
You are a game object designer. You've been given an object's classification \
(name, substance, element, tags). Now design its personality and appearance.

Create:
1. **behaviors** (0-4): Each is a verb + freeform target. List in priority order.
   - Verbs: destroy (attack), eat (consume+heal), investigate (approach slowly), \
follow (maintain distance), protect (follow+defend), flee (run away)
   - Only for LIVING creatures. Non-living objects need no behaviors.
   - Examples: destroy→"enemies", eat→"food", flee→"fire", follow→"the player"

2. **visual_descriptor**:
   - visual_description: 1-2 sentences — shape, material, colors, distinctive features
   - size_category: tiny | small | medium | large | huge

Make the visual consistent with the substance and tags. Make behaviors reflect \
the creature's personality — order matters (first = highest priority).\
"""


SPLIT_VARIANTS: dict[str, tuple[str, str]] = {
    "split_v1": (CLASSIFY_PROMPT, CREATIVE_PROMPT),
}
