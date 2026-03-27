# Gut Check: Three Things We're Getting Wrong

After reading the Scribblenauts deep-dive and walking through the codebase,
these are the gaps that jumped out immediately.

---

## 1. Objects are props, not actors

The compass doc's single biggest lesson: Scribblenauts' world felt alive because
objects *did things on their own*. Nine behavior verbs (destroy, eat, investigate,
follow, protect, use, ride, steal, run away) meant a lion would hunt, a puppy
would follow, a cop would chase. Every object had agency.

Our objects are physics props. They sit on the ground obeying gravity until the
player manually shoves them into each other. The rule engine only fires on
collision — there's no tick-based evaluation, no "a BURNING object seeks out
FLAMMABLE neighbors," no "a HOSTILE creature chases LIVING things." Drop a wolf
and a sheep into the same level and they'll just... sit there.

The pitch is "Scribblenauts meets Terraria" but right now the world between
collisions is dead. The rule engine is solid for what it does, but it only
answers "what happens when A touches B?" It never asks "what does A *want* to
do?"

**What Scribblenauts got right:** Behavior verbs targeted *categories*, not
individual objects. A single rule — "all predators destroy category 'Prey'" —
scaled across thousands of objects. We could do the same with tags: HOSTILE seeks
LIVING, BURNING seeks FLAMMABLE, ELECTRIC seeks CONDUCTIVE.

---

## 2. Tags are boolean, properties are flat

Scribblenauts had 10 property tabs with ~40-50 numeric and enum fields: health
(1–1,500), weapon damage (1–100), weight (numeric), movement speed (numeric),
jump height (5 levels), temperature (continuous accumulation per tick), buoyancy
(float/sink/neutral), container size, explosion type (5 tiers).

Our objects have tags — on/off switches. SHARP or not. HEAVY or not. HOSTILE or
not. A "rusty dagger" and "enchanted greatsword" both get SHARP and deal the
same damage through the same rule. A "weak goblin" and "ancient dragon" both get
LIVING + HOSTILE and have no mechanical difference beyond maybe size_category.

The LLM is already generating structured output via Pydantic — it's right there
in `CreatorOutput`. But we're asking it to pick from 33 boolean tags instead of
filling out a property vector with numeric fields. The tag system is a good
*categorical* layer (what kind of thing is this?) but there's no *degree* layer
underneath it (how much of that thing is it?).

The compass doc's "Objects React To It As If It's A" field is the pattern we're
missing. It decoupled an object's name from its behavioral archetype. We collapse
everything into the tag bag, so there's no room for a "zombie firefighter" that
behaves like a zombie but looks like a firefighter.

**What this costs us:** Every SHARP object is mechanically identical. Every
BURNING object burns at the same rate. Every interaction is the same intensity.
The LLM generates rich descriptions — "a corroded iron blade that sparks when
swung" — and then the game flattens it to `[SHARP, METALLIC, ELECTRIC]`.

---

## 3. No modifier system — objects are immutable after creation

Scribblenauts shipped ~10,000 adjectives. Each was a property delta: "wooden"
added flammability and changed the texture, "giant" scaled size and weight,
"flying" added a movement mode, "frozen" lowered temperature and added ice
visuals. Players composed them freely — "giant frozen wooden sword" was four
discrete transforms stacking at runtime. The creative core of the game was
combinatorial experimentation with modifiers.

Our system: player types a full description, LLM generates a finished object,
done. No composition. No runtime mutation beyond tag add/remove from rule
effects (which the player doesn't control). You can't take a sword you already
made and make it "on fire" or "giant" or "invisible." Every creative act is a
single atomic LLM call that costs budget.

This matters because the Scribblenauts research is explicit that the deepest
player engagement came from *modifying and combining*, not just *summoning*.
Super Scribblenauts pivoted the entire game toward adjective puzzles. Our
current loop is: type description → get object → place it → watch physics.
There's no "what if I made it bigger?" moment.

The engine already supports tag mutation (`add_tag`/`remove_tag` effects in the
rule system, `effect_executor.gd` handles it). But there's no player-facing
way to say "apply BURNING to this object" or "make this GIANT." The
infrastructure is half there — the creative verb is missing.

**What this costs us:** Players get one shot per object. The budget ($1.00,
~24 objects) runs out fast. Without modifiers, each creation must be exactly
right on the first try, which is the opposite of the experimental sandbox
fantasy.

---

## Bottom line

The backend is well-built and the rule engine is solid. But the game is
currently a physics toy where you spawn inert objects and bump them together.
The three gaps above are all facets of the same underlying issue: **objects
don't have enough internal state or autonomous behavior to create emergent
gameplay without the player manually orchestrating every interaction.**

Scribblenauts' insight was that the fun comes from objects surprising you —
the lion eating the steak glued to its back, the cop ignoring Cthulhu for
the donut. That requires objects that *want things* (behavior), *differ in
degree* (numeric properties), and *can be transformed* (modifiers). We have
none of the three yet.
