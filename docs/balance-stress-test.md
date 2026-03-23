# Balance Stress Test: Adversarial Object Analysis

An adversarial analysis of 10 maximally broken objects a player could craft within
our 10-point tag budget, traced through the rule engine, cascade system, and
equipment mechanics. Inspired by Scribblenauts' post-mortem lessons — particularly
the jetpack+rope traversal exploit, cosmic-black-hole stat bypass, and
lion-eating-itself recursion bug.

---

## System constraints under test

| Parameter | Value |
|-----------|-------|
| Tag budget per object | 10 points |
| Tags per object | 2-6 |
| Contradiction pairs | 12 |
| Cascade max depth | 3 (depths 0-3, so 4 levels total) |
| Cascade radius | 96 px |
| Collision cooldown | 0.5 s per pair |
| Equipment slots | 3 (hand, back, head) |
| Transferable tags | 14 of 33 |
| Cascade-eligible rules | 11 of 55 |
| DOT timer cap | **None** |
| Simultaneous rule cap | **None** (all matching rules fire) |
| Rule preemption | **None** (high-priority rules don't cancel lower ones) |

---

## Object 1: "Toxic Torch" — Walking Death Aura

**Concept:** Equippable item that turns the player into a passive area-denial weapon.

| Tag | Cost |
|-----|------|
| HEAT_SOURCE | 3 |
| TOXIC | 4 |
| TOOL | 2 |
| FLAMMABLE | 1 |
| **Total** | **10** |

**Equipment transfer:** TOOL = hand slot. Transfers HEAT_SOURCE + TOXIC to player.
Player effective tags: `[LIVING, HEAT_SOURCE, TOXIC]`.

**Rule trace — player walks near a LIVING enemy:**
1. `toxic_living_damage` (p10, bidir): 10 instant damage to enemy.
2. No further LIVING rules fire from HEAT_SOURCE (HOT+LIVING triggers, not HEAT_SOURCE+LIVING).

**Rule trace — player walks near a FLAMMABLE object:**
1. `heat_flammable_ignite` (p10, bidir, **cascade**): Target gains HEAT_SOURCE + HOT, 10 DOT for 5s.
2. Cascade fires. Every FLAMMABLE neighbor within 96px ignites.
3. Depth 0→1→2→3: fire chain propagates up to 384px of total spread.

**Rule trace — player walks near CONDUCTING object:**
1. No rule. HEAT_SOURCE + CONDUCTING → `heat_conducting_transfer` (p8, **cascade**): Target gains HOT.
2. HOT cascades through CONDUCTING network.

**Verdict: MODERATELY BROKEN.**
The player becomes a walking firestorm — every FLAMMABLE object within reach auto-ignites
and cascades. This is our mild version of the jetpack problem: one item passively solves
any obstacle involving flammable materials. The TOXIC tag adds 10 damage per collision
to any LIVING thing, making the player a passive combatant just by standing nearby.

**Severity: 6/10.** Cascade fire is dramatic but bounded by depth 3. The real concern is
that this single item replaces both offense and environmental interaction.

---

## Object 2: "Acid Blade" — Unlimited DOT Stacking

**Concept:** Equippable weapon that stacks unlimited damage-over-time timers.

| Tag | Cost |
|-----|------|
| CORROSIVE | 4 |
| SHARP | 2 |
| TOOL | 2 |
| SOLID | 1 |
| RIGID | 1 |
| **Total** | **10** |

**Equipment transfer:** TOOL = hand slot. Transfers CORROSIVE + SHARP to player.
Player effective tags: `[LIVING, CORROSIVE, SHARP]`.

**Rule trace — player stands next to a LIVING enemy:**

Every 0.5s (cooldown), the collision re-fires:
1. `sharp_living_cut` (p9): 25 instant damage.
2. `corrosive_living_damage` (p10): 20 instant damage.
3. **Total per collision: 45 instant damage.**

**Rule trace — player stands next to a BREAKABLE object:**

Every 0.5s:
1. `sharp_breakable_damage` (p8): 25 instant damage.
2. `corrosive_breakable_corrode` (p8): **15 DOT/s for 3s** (spawns a new Timer child node).

After sustained contact:
- 0.0s: 25 instant + DOT timer #1 starts (15 dps)
- 0.5s: 25 instant + DOT timer #2 starts. Two timers running: 30 dps.
- 1.0s: 25 instant + DOT timer #3. Three timers: 45 dps.
- 1.5s: 25 instant + DOT timer #4. Four timers: 60 dps.
- 3.0s: Timer #1 expires, but timer #7 starts. Six concurrent: 90 dps.

**Steady-state DPS: 50 instant/s + 90 DOT/s = 140 DPS.**

BREAKABLE objects have 50 HP. They die from the first collision (25 dmg) plus one DOT
tick (15 dmg) = dead in 1 second. RIGID objects (200 HP) die in ~1.5 seconds.

**Rule trace — player touches CONDUCTING object:**
- `corrosive_conducting_dissolve` (p9): 20 DOT/s for 3s. Same stacking problem.

**Rule trace — player touches RIGID object:**
- `corrosive_rigid_weaken` (p7): 10 DOT/s for 3s. Stacks identically.

**Verdict: BROKEN.**
The DOT stacking is the core vulnerability. `_apply_dot()` in `effect_executor.gd`
spawns a new Timer child every invocation with no deduplication or cap.
There is no check for existing DOT timers on the target. A player holding this sword
deals escalating damage the longer they maintain contact — with no upper bound on
simultaneous DOT timers.

The code path:
```
effect_executor.gd:145 _apply_dot() → Timer.new() → target.add_child(timer)
```
No max-children check. No "already has CORRODE DOT" check.

**Severity: 8/10.** Every CORROSIVE or IGNITE interaction in the game has this vulnerability.

---

## Object 3: "Chain Lightning" — Electric Cascade Propagation

**Concept:** Cheap electric node that cascades ELECTRIC through CONDUCTING networks.

| Tag | Cost |
|-----|------|
| ELECTRIC | 4 |
| CONDUCTING | 2 |
| LIGHT | 1 |
| BREAKABLE | 1 |
| **Total** | **8** |

**Rule trace — placed near a CONDUCTING object:**
1. `electric_conducting_electrify` (p12, bidir, **cascade**): Target takes 30 dmg, gains ELECTRIC tag.
2. Target's tags changed → cascade fires.
3. Target (now ELECTRIC + its existing tags) checks 96px neighbors.
4. Any CONDUCTING neighbor: same rule fires at depth+1. 30 dmg + ELECTRIC tag.
5. Chain continues to depth 3.

**Cascade damage in a cluster of 5 CONDUCTING objects within 96px:**
- Depth 0: Object A electrifies Object B. 30 dmg.
- Depth 1: Object B electrifies Objects C, D. 30 dmg each.
- Depth 2: Objects C, D electrify Object E. 30 dmg.
- Depth 3: Terminal. No further cascade.
- **Total: 150 damage distributed, all 5 objects now permanently ELECTRIC.**

**The permanent tag problem:** ELECTRIC is added via `ADD_TAG` but never removed.
These objects are now permanently electrified. Any LIVING thing that touches them later
takes 30 damage (`electric_living_shock`). Any BREAKABLE thing takes 30 damage
(`electric_breakable_damage`). The area is permanently hazardous.

**Amplification:** Player creates 2 Chain Lightning objects (16 total points across 2
object budgets). Place them in a level with CONDUCTING scenery objects (metal platforms,
pipes, etc.). The entire CONDUCTING network becomes permanently electrified.

**Verdict: CONCERNING.**
Bounded by cascade depth 3, but the permanent ELECTRIC tag addition means the damage
persists indefinitely. There is no ELECTRIC decay or removal mechanism for non-living
objects. The tag is write-once, read-forever.

**Severity: 5/10.** Powerful but requires CONDUCTING targets. The real risk is if level
designers place many CONDUCTING objects near each other.

---

## Object 4: "Napalm Cluster" — Cheap Cascade Fire Spam

**Concept:** Minimum-cost fire cascade amplifier. Create 3-4 for area denial.

| Tag | Cost |
|-----|------|
| HEAT_SOURCE | 3 |
| FLAMMABLE | 1 |
| GAS | 1 |
| LIGHT | 1 |
| **Total** | **6** |

**Why this is dangerous at 6 points:**
The object budget is per-object, not per-session. A player can create many objects
(limited only by the session's $1.00 budget at $0.041/object = ~24 objects).
At 6 points, this is well under the 10-point cap. A player could create 4 of these
for total session cost of $0.164.

**Rule trace — two Napalm Clusters collide:**

Object A (HEAT_SOURCE, FLAMMABLE, GAS, LIGHT) touches Object B (same tags):

1. `heat_flammable_ignite` (p10, bidir, **cascade**): B gains +HEAT_SOURCE +HOT, 10 DOT/s for 5s.
2. Bidirectional: A also gains +HOT. (Already has HEAT_SOURCE.)
3. `heat_heat_intensify` (p5, **cascade**): Both are HEAT_SOURCE → cascade trigger.
4. Tags changed on both A and B → cascade fires from both.

**Cascade from A (depth 1):** Finds Object C within 96px.
- `heat_flammable_ignite`: C ignites. Cascade from C (depth 2).
- C finds Object D. D ignites. Cascade from D (depth 3). Terminal.

**Result:** 4 objects, all now HEAT_SOURCE + HOT + FLAMMABLE + GAS + LIGHT.
Each has IGNITE DOT: 10 dmg/s for 5s = 50 total damage. Default durability = 150 HP.
They survive the first chain reaction but are now permanent HEAT_SOURCE objects.

**Environmental impact:** Any FLAMMABLE object within 96px of any cluster member
ignites on contact. Any LIVING thing within 96px takes `hot_living_burn` (5 dmg/collision).
The GAS tag means WIND_SOURCE objects disperse them (150 force push), potentially
spreading the cluster wider.

**Scribblenauts parallel:** This is the "campfire surrounding" exploit from the
Compass doc — ambient temperature accumulation over time. Place enough cheap heat
sources and the area becomes uninhabitable.

**Verdict: MODERATELY BROKEN.**
The danger isn't any single object — it's the economics. At 6 points and $0.041 per
object, a player can carpet the level with fire nodes. The cascade system faithfully
propagates fire through all of them. The depth-3 limit only affects single-chain
propagation; a grid of fire nodes within 96px of each other creates overlapping cascade
zones that collectively cover far more than 384px.

**Severity: 6/10.** Bounded by object creation cost, but 4 objects is cheap.

---

## Object 5: "Shield of Lies" — The Insulation Non-Functionality Bug

**Concept:** Equippable shield that SHOULD provide defense but doesn't.

| Tag | Cost |
|-----|------|
| INSULATING | 2 |
| REFLECTIVE | 2 |
| WEARABLE | 2 |
| RIGID | 2 |
| SOLID | 1 |
| **Total** | **9** |

**Equipment transfer:** WEARABLE = equip slot by base_form. Transfers INSULATING +
REFLECTIVE to player. Player effective tags: `[LIVING, INSULATING, REFLECTIVE]`.

**Expected behavior:** Player is protected from heat, cold, and electricity.

**Actual rule trace — ELECTRIC object touches player:**

The resolver finds ALL matching rules and executes ALL of them:

1. `electric_insulating_block` (p20, bidir): `CHANGE_PROPERTY` with no tags_to_add,
   no tags_to_remove. **Prints "The insulation blocks the electricity." Does nothing.**
2. `electric_living_shock` (p12, bidir): **30 damage to player.**
3. `reflective_electric_reflect` (p14): **30 damage reflected to attacker.**

The player takes full damage AND reflects it. The "block" is cosmetic.

**Actual rule trace — HEAT_SOURCE object touches player:**
1. `insulating_heat_block` (p14): `CHANGE_PROPERTY`, empty. **Prints message. Does nothing.**
2. `reflective_heat_reflect` (p12): 10 damage to attacker.
3. If player touches a HOT+LIVING enemy: `hot_living_burn` (p8): 5 damage to player.

Again: full damage taken, plus reflected damage. Insulation is theater.

**The root cause:**
```python
# rules_data.py line 180-186 (electric_insulating_block)
Effect(
    effect_type=EffectType.CHANGE_PROPERTY,
    target=EffectTarget.B,
    message="The insulation blocks the electricity.",
    # No tags_to_add, no tags_to_remove, no damage modification
)
```
The block rules have the highest priority but no actual effect. And the collision
resolver has no rule-preemption system — all matching rules fire regardless of priority.

**This is not an exploit — it's a design bug.** Any player who creates INSULATING or
REFLECTIVE equipment expecting defense will discover it's cosmetic. The game's feedback
message says "blocked" while the damage number says otherwise.

**Verdict: DESIGN BUG, not a player exploit.**

**Severity: 7/10 (as a trust/UX bug).** Players will lose faith in the tag system
when they discover "blocked" messages accompanied by full damage. This is the
Scribblenauts "vegetarian eats hamburger" problem — the system promises behavior it
doesn't deliver.

**Fix required:** See Systemic Fix #3 below.

---

## Object 6: "Cascade Nuke" — Explosion Chain Reaction

**Concept:** Cheap explosive that detonates from any heat source and cascades destruction.

| Tag | Cost |
|-----|------|
| EXPLOSIVE | 5 |
| FLAMMABLE | 1 |
| BREAKABLE | 1 |
| LIGHT | 1 |
| **Total** | **8** |

**Rule trace — HEAT_SOURCE object touches this:**
1. `explosive_heat_detonate` (p20, bidir, **cascade**):
   - Target A (this object): DESTROY = 99999 damage. Dies instantly.
   - Target B (heat source): 80 damage + 500 force impulse.
2. `heat_flammable_ignite` (p10, bidir, **cascade**):
   - This object gains HEAT_SOURCE + HOT + IGNITE DOT.
   - But it's already dead from DESTROY (99999 dmg fires first due to higher priority).

**Key question: does a destroyed object still cascade?**

In Godot, `queue_free()` defers removal to end of frame. The cascade check happens
immediately after rule execution in the same frame:
```gdscript
# collision_resolver.gd:73-82
if any_cascade_eligible and cascade_depth < MAX_CASCADE_DEPTH:
    var tags_a_after = _get_body_tags(body_a)  # body_a may be queue_freed
```

If the DESTROY effect calls `queue_free()`, the object is still technically valid during
the current frame. `_get_body_tags()` will return its tags. `_cascade_to_neighbors()`
will fire. The dead object cascades to neighbors before being removed.

**Cascade chain with 3 Nukes + 2 Napalm Clusters:**

Layout: `[Napalm A] — 80px — [Nuke B] — 80px — [Nuke C] — 80px — [Napalm D] — 80px — [Nuke E]`

1. Light Napalm A (any fire source). Depth 0.
2. A cascades to Nuke B (96px radius). `explosive_heat_detonate` at depth 1:
   Nuke B DESTROYED. 80 dmg + 500 force to A.
3. Nuke B cascades (dead but still in-frame) to Nuke C at depth 2:
   Nuke C DESTROYED. 80 dmg + 500 force.
4. Nuke C cascades to Napalm D at depth 3:
   `heat_flammable_ignite`: D ignites. Terminal depth.

**Total damage output:**
- Nuke B explosion: 80 damage + 500 force in radius
- Nuke C explosion: 80 damage + 500 force in radius
- Napalm D ignited: 10 DOT + HEAT_SOURCE propagation
- Cascade radius overlap: anything within 96px of any nuke takes 80+ damage

**Force concern:** 500 force magnitude per explosion. Three overlapping blasts =
1500+ cumulative force. LIGHT objects (mass 0.2) receive acceleration of
`force / mass = 500 / 0.2 = 2500 px/s`. This launches objects off-screen.

**Verdict: BROKEN (force magnitude).**
The explosions themselves are bounded by depth 3. But the 500 force impulse on
LIGHT objects (mass 0.2) creates absurd velocities. Objects fly off-screen and may
never return. This is a physics exploit more than a rule exploit.

**Severity: 7/10.** The cascade is bounded but force magnitudes are unbounded relative
to object mass.

---

## Object 7: "Toxic Fog" — Gas Cascade Area Denial

**Concept:** Toxic gas that spreads TOXIC to all nearby GAS objects via cascade.

| Tag | Cost |
|-----|------|
| TOXIC | 4 |
| GAS | 1 |
| LIGHT | 1 |
| FLAMMABLE | 1 |
| **Total** | **7** |

**Rule trace — Toxic Fog touches another GAS object:**
1. `toxic_gas_cloud` (p8, bidir, **cascade**): Target gains TOXIC tag. Tags changed → cascade.
2. Cascade: newly TOXIC neighbor checks ITS GAS neighbors. Same rule fires.
3. Depth 0→1→2→3: TOXIC propagates through entire GAS network.

**After propagation:** Every GAS object within cascade range is now TOXIC. Any LIVING
thing touching any of them triggers `toxic_living_damage` (10 dmg per collision, 0.5s cooldown).

**Combo with fire:** All Toxic Fog objects are FLAMMABLE. A single HEAT_SOURCE contact:
1. `heat_flammable_ignite` (cascade): Object ignites.
2. HEAT_SOURCE added → cascades to nearby FLAMMABLE GAS objects.
3. Entire gas network ignites AND is toxic.
4. LIVING things near the cloud take: 10 dmg (toxic) + 5 dmg (hot_living_burn) + 10 DOT (ignite) per collision.

**Physics:** GAS objects have mass 0.01 and friction 0.0. WIND_SOURCE pushes them
(150 force, `wind_gas_disperse`). A player with equipped WIND_SOURCE can blow the
toxic cloud toward enemies. Mass 0.01 means `force/mass = 150/0.01 = 15,000 px/s`
acceleration — the gas gets launched instantly.

**Verdict: MODERATELY BROKEN.**
The cascade propagation through GAS networks is powerful area denial. The GAS mass
(0.01) combined with any force creates absurd velocities, same as the explosion force
problem. The TOXIC+GAS cascade has no depth limit concern (depth 3 bounds it), but
the gas physics are broken independent of rules.

**Severity: 5/10.** Requires multiple GAS objects nearby. But gas physics are exploitable.

---

## Object 8: "Electric Sword" — Maximum Single-Item DPS

**Concept:** Highest damage-per-second achievable from a single equipped item.

| Tag | Cost |
|-----|------|
| ELECTRIC | 4 |
| SHARP | 2 |
| TOOL | 2 |
| SOLID | 1 |
| RIGID | 1 |
| **Total** | **10** |

**Equipment transfer:** TOOL = hand slot. Transfers ELECTRIC + SHARP.
Player effective tags: `[LIVING, ELECTRIC, SHARP]`.

**Rule trace — player touches LIVING enemy (every 0.5s):**
1. `electric_living_shock` (p12, bidir): 30 damage.
2. `sharp_living_cut` (p9): 25 damage.
3. **55 damage per collision. Cooldown 0.5s = 110 DPS.**

**Rule trace — player touches BREAKABLE object:**
1. `electric_breakable_damage` (p10): 30 damage.
2. `sharp_breakable_damage` (p8): 25 damage.
3. **55 damage. BREAKABLE has 50 HP. Instant kill.**

**Rule trace — player touches CONDUCTING object:**
1. `electric_conducting_electrify` (p12, bidir, **cascade**): 30 dmg + ELECTRIC tag.
2. Player walks through CONDUCTING network, electrifying everything.

**Comparison to base damage:** Without equipment, the player has only LIVING tag.
`living_living_neutral` (p1): "Two living things regard each other." Zero damage.
With the Electric Sword: 110 DPS against LIVING. That's infinite percent increase.

**Verdict: STRONG BUT POSSIBLY INTENDED.**
A single max-budget item dealing 110 DPS is powerful. The question is whether this
becomes broken in combination with other equipment (see Object 9).

**Severity: 4/10 alone, 9/10 in combination.**

---

## Object 9: "Triple Threat Loadout" — The Jetpack+Rope of Our Game

**Concept:** Three specifically crafted equipment items that together make the player
an invincible flying murder machine. This is our Scribblenauts jetpack+rope moment.

### Hand: Electric Sword (from Object 8)
Tags: ELECTRIC(4) + SHARP(2) + TOOL(2) + SOLID(1) + RIGID(1) = 10
Transfers: ELECTRIC, SHARP

### Back: Toxic Jetpack
Tags: TOXIC(4) + FLOATING(2) + WEARABLE(2) + FLEXIBLE(1) + LIGHT(1) = 10
Base form: "jetpack" → back slot.
Transfers: TOXIC, FLOATING

### Head: Corrosive Crown
Tags: CORROSIVE(4) + GLOWING(2) + WEARABLE(2) + CONDUCTING(2) = 10
Base form: "crown" → head slot.
Transfers: CORROSIVE, GLOWING, CONDUCTING

### Combined player effective tags:
`[LIVING, ELECTRIC, SHARP, TOXIC, FLOATING, CORROSIVE, GLOWING, CONDUCTING]`

**Eight tags. Zero budget violation — each item is independently valid at 10 points.**

### Offense — player touches LIVING enemy:

| Rule | Priority | Damage |
|------|----------|--------|
| `electric_living_shock` | 12 | 30 |
| `corrosive_living_damage` | 10 | 20 |
| `toxic_living_damage` | 10 | 10 |
| `sharp_living_cut` | 9 | 25 |
| **Total per collision** | | **85** |

Cooldown 0.5s → **170 DPS against any LIVING target.**

### Offense — player touches BREAKABLE object:

| Rule | Priority | Damage |
|------|----------|--------|
| `electric_breakable_damage` | 10 | 30 |
| `corrosive_breakable_corrode` | 8 | 15 DOT/s |
| `sharp_breakable_damage` | 8 | 25 |
| **Total per collision** | | **55 + 15 DOT/s** |

BREAKABLE objects (50 HP) die in a single collision.

### Offense — cascade damage:

| Rule | Target type | Effect |
|------|-------------|--------|
| `electric_conducting_electrify` | CONDUCTING | 30 dmg + ELECTRIC tag, **cascade** |
| `corrosive_conducting_dissolve` | CONDUCTING | 20 DOT/s |
| `corrosive_rigid_weaken` | RIGID | 10 DOT/s |

Player electrifies and corrodes entire CONDUCTING networks on contact.

### Mobility:
- FLOATING: gravity reduced by 70% (effective gravity = 0.3x).
- Player floats over pits, lava, and ground-based hazards.
- This IS the jetpack.

### Auto-targeting:
- GLOWING + LIVING → `glowing_living_attract` (p2): -30 force pulls LIVING enemies
  toward the player. Enemies walk into the kill zone automatically.
- This IS the rope.

### Defensive analysis:
Player has CONDUCTING — vulnerable to `electric_conducting_electrify` (30 dmg + cascade).
Player has LIVING — vulnerable to all LIVING-target rules.
But at 170 DPS, enemies die before they can meaningfully fight back.

### The Scribblenauts parallel:
| Scribblenauts | Our game |
|---------------|----------|
| Jetpack (mobility bypass) | FLOATING tag (70% gravity reduction) |
| Rope (range bypass) | GLOWING tag (auto-pull enemies to player) |
| "Solves every level" | 170 DPS + floating + auto-pull = solves every combat encounter |

**Verdict: SEVERELY BROKEN.**
Three objects, each independently legal within the 10-point budget, combine to give
the player 8 effective tags, 170 DPS against LIVING, floating mobility, and auto-targeting.
There is no per-player tag cap and no diminishing returns on simultaneous damage rules.

This is the single most dangerous exploit in the system. A player who figures out
equipment tag stacking will trivialize all content.

**Severity: 10/10.** This is the game's jetpack+rope.

---

## Object 10: "Burning Wire" — Mutual Cascade Feedback Loop

**Concept:** Two objects that recursively trigger cascade-eligible rules on each other,
testing whether the cooldown system prevents infinite loops.

| Tag | Cost |
|-----|------|
| HEAT_SOURCE | 3 |
| CONDUCTING | 2 |
| FLAMMABLE | 1 |
| BREAKABLE | 1 |
| LIGHT | 1 |
| **Total** | **8** |

**Rule trace — two Burning Wires touch each other:**

Object A and B have identical tags: `[HEAT_SOURCE, CONDUCTING, FLAMMABLE, BREAKABLE, LIGHT]`

Rules that match (A→B, all bidirectional or A-directed):
1. `heat_flammable_ignite` (p10, bidir, **cascade**): B gains +HEAT_SOURCE +HOT, 10 DOT.
2. `heat_conducting_transfer` (p8, bidir, **cascade**): B gains +HOT.
3. `heat_heat_intensify` (p5, **cascade**): Both HEAT_SOURCE → cascade trigger.

All three are cascade-eligible. Tags change on B (gains HOT). Cascade fires from B.

**Cascade depth 1 — B cascades back to A:**
- Cooldown check: pair key "A:B" was set at depth 0. Time elapsed ≈ 0ms.
  **Cooldown blocks the re-collision.** The A↔B pair cannot re-fire for 0.5s.

**Cascade depth 1 — B cascades to neighbor C (another Burning Wire):**
- New pair "B:C". No cooldown. All three rules fire again.
- C gains HOT, cascade to depth 2.

**Cascade depth 2 — C cascades to D:**
- New pair "C:D". Same rules fire.
- Depth 3: terminal.

**The cooldown saves us from infinite A↔B loops.** But the cascade still propagates
outward through new objects at each depth level. The cooldown only blocks the same pair,
not the same object from participating in new pairs.

**Multi-object cascade map (5 Burning Wires in a cluster):**
```
Depth 0: A→B (rules fire, cooldown set for A:B)
Depth 1: B→C, B→D, B→E (3 new pairs, rules fire on each)
Depth 2: C→D, C→E (2 new pairs), D→C, D→E (cooldown may block D→C if C→D already ran)
Depth 3: ...terminal
```

Each object takes 10 DOT (IGNITE, 5s duration) from each collision. An object can be
the target in multiple pairs. Object D might receive IGNITE from B→D (depth 1) AND
from C→D (depth 2) = 2 DOT timers = 20 DOT/s.

**Combined with Object 2's DOT stacking bug:** Each cascade level adds another DOT
timer. Objects accumulate DOT timers from multiple cascade sources. A central object
in a cluster of 5 could receive 4 DOT timers (one from each neighbor's cascade).
4 × 10 dmg/s × 5s = 200 total DOT damage on a 50 HP BREAKABLE object.

**Verdict: BOUNDED BUT AMPLIFIES DOT STACKING.**
The cooldown system correctly prevents A↔B infinite loops. But fan-out cascade
through multiple neighbors means objects in dense clusters receive multiple DOT timers.
This amplifies the DOT stacking vulnerability from Object 2.

**Severity: 5/10.** The cooldown works as designed; the remaining risk is DOT stacking.

---

## Systemic Findings

### Finding 1: Unlimited DOT Timer Stacking

**Affects:** Objects 2, 4, 6, 7, 10 — any CORRODE or IGNITE effect.

`effect_executor.gd:145-166` creates a new `Timer` child on every `_apply_dot()` call.
There is no check for existing DOT timers of the same type on the target. A single
object can accumulate unlimited simultaneous DOT timers.

**Worst case:** An object touching a CORROSIVE source re-fires every 0.5s. After 3s,
it has 6 concurrent CORRODE timers doing 15 dmg/s each = 90 DOT DPS from a single
source. If it's also in a cascade cluster, multiply by the number of cascade sources.

### Finding 2: Equipment Tag Stacking Has No Cap

**Affects:** Object 9 (the jetpack+rope exploit).

`player_equipment.gd:48-62` aggregates ALL transferable tags from ALL 3 equipment slots
with no cap. The player can accumulate up to 14 unique transferable tags (all 14 are
transferable). Each tag triggers its own rules independently. Damage stacks additively
with no diminishing returns.

The per-object budget of 10 is meaningless as a balance constraint when the player
can equip 3 max-budget items and receive their combined 30 points of tag power.
The effective "player tag budget" is 30, not 10.

### Finding 3: Block/Insulation Rules Are Cosmetic

**Affects:** Object 5 and any defensive strategy.

Three "block" rules exist with high priority but zero mechanical effect:
- `electric_insulating_block` (p20): No-op.
- `insulating_heat_block` (p14): No-op.
- `insulating_cold_block` (p14): No-op.

The collision resolver executes ALL matching rules. There is no preemption system where
a high-priority rule cancels lower-priority ones. The "block" rules print reassuring
messages while damage rules fire normally.

This means there are **zero defensive options** in the tag system. Every tag is
either offensive, utility, or cosmetic. Players cannot build toward defense.

### Finding 4: Force Magnitudes vs. Mass Creates Absurd Velocities

**Affects:** Objects 6, 7, and any force-based rule.

Force impulses (100-500 magnitude) applied to low-mass objects:
- GAS (mass 0.01): 500 force → 50,000 px/s acceleration
- LIGHT (mass 0.2): 500 force → 2,500 px/s acceleration

Objects reach escape velocity and leave the playable area. There is no velocity cap
in the physics system and no boundary teleportation.

### Finding 5: Permanently Added Tags Never Decay

**Affects:** Objects 3, 4, 7, 10.

When cascade rules add tags (ELECTRIC, HEAT_SOURCE, HOT, TOXIC, COLD), those tags
persist forever. There is no decay timer, no tag expiration, and no maximum tag count
per object. A level that has experienced a cascade chain becomes permanently
hazardous — objects never lose their acquired tags.

---

## Proposed Fixes

### Fix 1: DOT Timer Deduplication (Critical)

**File:** `godot/scripts/systems/effect_executor.gd`

Cap concurrent DOT timers per type per target. Before spawning a new timer, check if
the target already has an active DOT of the same type. If so, refresh duration instead
of stacking.

```gdscript
func _apply_dot(target: Node, damage_per_tick: float, tick_interval: float,
                duration: float, dot_type: String = "generic") -> void:
    if not target.has_method("take_damage"):
        return

    # Check for existing DOT of same type - refresh instead of stack
    var dot_key := "dot_%s" % dot_type
    if target.has_meta(dot_key):
        var existing_timer: Timer = target.get_meta(dot_key)
        if is_instance_valid(existing_timer):
            # Refresh: reset ticks remaining (stored in meta)
            target.set_meta(dot_key + "_ticks", int(duration / tick_interval))
            return

    var timer := Timer.new()
    timer.wait_time = tick_interval
    timer.one_shot = false
    target.add_child(timer)
    target.set_meta(dot_key, timer)

    var ticks_remaining: int = int(duration / tick_interval)
    target.set_meta(dot_key + "_ticks", ticks_remaining)
    timer.timeout.connect(func():
        if not is_instance_valid(timer) or not is_instance_valid(target):
            if is_instance_valid(timer):
                timer.queue_free()
            return
        var remaining: int = target.get_meta(dot_key + "_ticks", 0)
        if remaining <= 0:
            target.remove_meta(dot_key)
            target.remove_meta(dot_key + "_ticks")
            timer.queue_free()
            return
        target.set_meta(dot_key + "_ticks", remaining - 1)
        target.take_damage(damage_per_tick)
    )
    timer.start()
```

Call sites need updating: `_apply_dot(target, 10.0, 1.0, 5.0, "ignite")` and
`_apply_dot(target, 15.0, 1.0, 3.0, "corrode")`.

**Impact:** Caps DOT DPS at the design-intended values (10/s for ignite, 15/s for corrode).

---

### Fix 2: Equipment Tag Transfer Cap (Critical)

**File:** `godot/scenes/player/player_equipment.gd`

Cap the total number of transferred tags across all equipment to prevent the
Triple Threat loadout exploit.

```gdscript
const MAX_TRANSFERRED_TAGS: int = 4

func get_effective_tags() -> Array:
    if not _tags_dirty:
        return _cached_tags
    var tags: Array = ["LIVING"]
    var transferred: Array = []

    # Collect all transferable tags with their source item's power cost for priority
    for slot_name in equipped:
        var blueprint: Dictionary = equipped[slot_name]
        if blueprint.is_empty():
            continue
        var item_tags: Array = blueprint.get("tags", [])
        for tag in item_tags:
            if tag in TRANSFERABLE_TAGS and tag not in transferred:
                transferred.append(tag)

    # If over cap, keep only the first N (equipped in slot order: hand, back, head)
    if transferred.size() > MAX_TRANSFERRED_TAGS:
        transferred = transferred.slice(0, MAX_TRANSFERRED_TAGS)

    tags.append_array(transferred)
    _cached_tags = tags
    _tags_dirty = false
    return _cached_tags
```

**Impact:** Player can have at most LIVING + 4 transferred tags = 5 total. Max 3
damage rules fire per collision instead of 5+. DPS drops from 170 to ~55-85 depending
on which 4 tags the player prioritizes.

**Design consideration:** The cap of 4 is a starting point. Playtesting should determine
the right number. Even 3 might be appropriate for aggressive balance.

---

### Fix 3: Rule Preemption for Block Rules (Important)

**File:** `godot/scripts/systems/collision_resolver.gd`

When a "block" rule fires, it should prevent lower-priority rules that target the same
damage channel from executing.

```gdscript
func resolve_collision(body_a: Node, body_b: Node, cascade_depth: int = 0) -> void:
    # ... existing cooldown/tag checks ...

    var rules: Array = RuleEngine.find_matching_rules(tags_a, tags_b)
    if rules.is_empty():
        return

    var tags_a_before: Array = tags_a.duplicate()
    var tags_b_before: Array = tags_b.duplicate()

    # Collect blocked tag categories from high-priority block rules
    var blocked_channels: Array = []
    var any_cascade_eligible: bool = false

    # Sort by priority descending (should already be sorted)
    for rule in rules:
        if _is_block_rule(rule):
            blocked_channels.append(rule.get("block_channel", ""))
            _effect_executor.execute(rule, body_a, body_b)
            continue
        # Skip damage rules whose channel is blocked
        var channel: String = rule.get("damage_channel", "")
        if channel != "" and channel in blocked_channels:
            continue
        _effect_executor.execute(rule, body_a, body_b)
        if rule.get("cascade_eligible", false):
            any_cascade_eligible = true

    # ... existing cascade logic ...
```

**Also requires:** Adding `block_channel` and `damage_channel` fields to rule definitions.
For example, `electric_insulating_block` gets `block_channel: "electric"` and
`electric_living_shock` gets `damage_channel: "electric"`.

**Backend changes:** Add `block_channel` and `damage_channel` optional fields to
`InteractionRule` model in `backend/app/models/rules.py`. Tag the three block rules
and their corresponding damage rules.

**Impact:** INSULATING actually blocks electric and thermal damage. REFLECTIVE becomes
a counter-attack mechanic (reflects damage instead of taking it). Players can build
meaningful defensive loadouts.

---

### Fix 4: Force-to-Mass Velocity Cap (Important)

**File:** `godot/scripts/systems/effect_executor.gd`

Cap the resulting velocity from force application to prevent objects from leaving the
playable area.

```gdscript
const MAX_IMPULSE_VELOCITY: float = 800.0  # px/s

func _apply_impulse(target: Node, body_a: Node, body_b: Node, magnitude: float) -> void:
    if target is not RigidBody2D:
        return
    var source: Node = body_b if target == body_a else body_a
    if source is Node2D and target is Node2D:
        var direction: Vector2 = (target.global_position - source.global_position).normalized()
        var impulse: Vector2 = direction * magnitude

        # Cap resulting velocity
        var predicted_velocity: Vector2 = target.linear_velocity + impulse / target.mass
        if predicted_velocity.length() > MAX_IMPULSE_VELOCITY:
            impulse = direction * MAX_IMPULSE_VELOCITY * target.mass - target.linear_velocity
            if impulse.dot(direction) < 0:
                impulse = Vector2.ZERO

        target.apply_central_impulse(impulse)
```

**Impact:** GAS (mass 0.01) with 500 force → capped at 800 px/s instead of 50,000 px/s.
Objects move dramatically but stay in the playable area.

---

### Fix 5: Tag Decay for Cascade-Added Tags (Nice-to-Have)

**File:** `godot/scenes/game_object/game_object.gd` (or wherever `add_tag` lives)

Tags added by cascade effects should decay after a duration rather than persisting
forever.

```gdscript
func add_tag(tag: String, duration: float = 0.0) -> void:
    if tag not in _tags:
        _tags.append(tag)
        _on_tags_changed()

    if duration > 0.0:
        # Schedule tag removal
        var decay_timer := Timer.new()
        decay_timer.wait_time = duration
        decay_timer.one_shot = true
        add_child(decay_timer)
        decay_timer.timeout.connect(func():
            remove_tag(tag)
            decay_timer.queue_free()
        )
        decay_timer.start()
```

Effect executor changes: cascade `ADD_TAG` effects should pass a duration (e.g., 10s
for ELECTRIC, 15s for HOT, 8s for TOXIC).

**Impact:** Cascade chains create temporary hazard zones that clear themselves. Areas
recover after the chain reaction fades. Prevents permanently electrified/toxic levels.

---

## Summary: Risk Matrix

| # | Object | Severity | Root Cause | Fix |
|---|--------|----------|------------|-----|
| 1 | Toxic Torch | 6/10 | Equipment tag transfer | Fix 2 |
| 2 | Acid Blade | 8/10 | DOT stacking | Fix 1 |
| 3 | Chain Lightning | 5/10 | Permanent tag addition | Fix 5 |
| 4 | Napalm Cluster | 6/10 | Cheap cascade objects | Fix 5, level design |
| 5 | Shield of Lies | 7/10 | Block rules are no-ops | Fix 3 |
| 6 | Cascade Nuke | 7/10 | Force vs mass | Fix 4 |
| 7 | Toxic Fog | 5/10 | Gas mass + force | Fix 4 |
| 8 | Electric Sword | 4/10 | Intended (single item) | Monitor |
| 9 | Triple Threat | **10/10** | Equipment tag stacking | **Fix 2** |
| 10 | Burning Wire | 5/10 | DOT stacking via cascade | Fix 1 |

### Priority order:
1. **Fix 1 (DOT dedup)** + **Fix 2 (tag transfer cap)**: Address the two critical exploits.
2. **Fix 3 (rule preemption)**: Make defensive tags functional.
3. **Fix 4 (velocity cap)**: Prevent physics escape.
4. **Fix 5 (tag decay)**: Improve long-term level health.

### What we got right:
- **Cascade depth 3** prevents infinite chain reactions. Without this, Objects 4 and 10
  would be game-ending.
- **Pair-based cooldowns** prevent A↔B ping-pong loops in cascade. The Burning Wire
  test (Object 10) confirmed this works correctly.
- **Contradiction pairs** prevent the most obviously broken tag combos (FROZEN+MOLTEN,
  HEAVY+LIGHT). The 12 pairs are well-chosen.
- **Tag budget of 10** effectively constrains single objects. No single legal object
  is game-breaking — the exploits all emerge from multi-object combinations or system
  interactions the budget doesn't account for.

### The Scribblenauts lesson confirmed:
Scribblenauts' worst balance failures came from *mobility items breaking traversal* and
*stat stacking bypassing intended limits*. Our system reproduces exactly these failure
modes: FLOATING breaks traversal (Object 9), and equipment tag stacking bypasses the
per-object budget (Objects 1, 2, 8, 9). The budget constrains individual objects but
not the player's accumulated power through equipment — just as Scribblenauts' per-object
balance couldn't prevent the jetpack+rope combo from trivializing level design.

The fix is the same insight England and Slaczka reached: **you cannot prevent dominant
strategies through object-level balance alone**. You need system-level caps
(tag transfer limit), mechanical safeguards (DOT dedup, velocity caps), and functional
defensive options (rule preemption) to create a design space where creativity is
rewarded but dominance strategies are bounded.
