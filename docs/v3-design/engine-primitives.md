# V3 Engine Primitives

Everything the LLM outputs must map onto something the engine can execute. This document is the reference for what those things are.

---

## Physics properties

Set at creation time. Each is 1 LLM call, 1-2 output tokens. All asked in parallel (~60ms wall time).

**Design principle:** Real-world physical quantities use real-world units (kg, cm) to leverage LLM training data grounding — the LLM knows "a sword weighs 1.5 kg" from training. Abstract game properties use 0-100 integer scales with named anchors.

| Property | Prompt format | Output | Engine mapping |
|---|---|---|---|
| **Mass** (kg) | "How heavy in kg? (ant=0.001, feather=0.01, apple=0.2, sword=1.5, human=70, car=1500, house=50000)" | 1 number (may be 2-4 tokens for decimals) | Direct. Clamped 0.001–100000 |
| **Height** (cm) | "How tall in cm? (ant=1, mouse=5, coin=2, sword=120, human=170, horse=200, house=800)" | 1 integer | Sprite scale + collision shape. cm → m for engine. Clamped 1–5000 |
| **Friction** (0–100) | "How grippy 0-100? (ice=0, metal=30, wood=50, rubber=90)" | 1 integer | PhysicsMaterial friction. 0-100 → 0.0-1.0 |
| **Bounce** (0–100) | "How bouncy 0-100? (clay=0, wood=20, tennis ball=70, super ball=99)" | 1 integer | PhysicsMaterial bounce. 0-100 → 0.0-1.0 |
| **Gravity** (0–100) | "Gravity pull 0-100? (balloon=5, smoke=15, ghost=30, feather=40, normal=50, rock=60, anvil=75)" | 1 integer | gravity_scale. 0-100 → -1.0 to 2.0 |

**Damping** is derived, not LLM-decided: `damping = height_cm / (mass_kg * 100 + 10)`. Light large things (feather) have high damping. Heavy small things (bullet) have low damping.

Mass uses real-world kg (decimal, 2-4 tokens) because LLM grounding in physical weight matters for answer quality. Height uses cm (integer, 1-2 tokens) — real-world grounded AND always an integer. All other properties are 0-100 integer scales with no real-world unit the LLM has strong priors about.

---

## Destructibility

Two questions, parallel with physics batch:

| Property | Prompt | Output |
|---|---|---|
| **Armor** (0–100) | "How resistant to damage? (paper=5, wood=30, steel=80, diamond=99)" | 1 number |
| **HP** (0–100) | "How much punishment before destroyed? (balloon=5, wood=40, steel=80, mountain=skip)" | 1 number |
| **Indestructible** | "Can this be destroyed? 0=no 1=yes" | 1 number |

Armor reduces incoming damage (percentage). HP is the total pool. A slime has low armor (easy to damage per hit) but high HP (lots of punishment). A glass window has low armor AND low HP. Indestructible objects skip HP tracking entirely — damage interactions are ignored.

---

## Interaction outcomes

The engine has 6 primitives for what can happen when two objects meet. Numbered for LLM output:

| # | Outcome | Parameters | Examples |
|---|---|---|---|
| 0 | **Nothing** | — | Rock + rock. Sword + sword. |
| 1 | **Damage** | amount (0-100), mode (0=instant, 1=continuous) | Fire burns wood. Acid corrodes metal. |
| 2 | **Force** | strength (0-100), direction (0=push, 1=pull), mode (0=instant, 1=continuous) | Explosion pushes. Magnet pulls. Wind blows. |
| 3 | **Add state** | state_id (1-7) | Fire sword adds on_fire to wood. |
| 4 | **Remove state** | state_id (1-7) | Water removes on_fire. Grounding rod removes electrified. |
| 5 | **Destroy** | which (0=A, 1=B) | Water poured on fire destroys the water. Key consumed by lock. |

### Mapping to pairwise LLM calls

Each pairwise evaluation asks 9 parallel 1-token questions that map onto these primitives:

| Call | Question | Primitives covered |
|---|---|---|
| 1-2 | Damage to A/B? 0-100 | Damage (#1) |
| 3-4 | State change on A/B? 0-14 | Add state (#3) + Remove state (#4) |
| 5-6 | Force on B? 0-100 / Push or pull? | Force (#2) |
| 7-8 | A/B destroyed? 0/1 | Destroy (#5) |
| 9 | Instant or continuous? 0/1 | Mode for damage + force |

**State encoding 0-14:** `0`=none, `1`=add on_fire, `2`=add frozen, `3`=add wet, `4`=add electrified, `5`=add poisoned, `6`=add corroded, `7`=add molten, `8`=remove on_fire, `9`=remove frozen, `10`=remove wet, `11`=remove electrified, `12`=remove poisoned, `13`=remove corroded, `14`=remove molten. All single tokens. Limitation: one state change per object per interaction.

**Force on A is engine-derived**, not LLM-evaluated. The engine applies Newton's 3rd law heuristic: `force_a = force_b × (mass_b / mass_a)`. This is more consistent than asking the LLM to reason about mass ratios. Bounce reflection is handled by the physics property, not pairwise force.

Carry/mount interactions are handled by the affordance system, not the pairwise cache.

---

## States (closed vocabulary)

Interaction-only state modifiers. Never set at creation — objects are born stateless. Applied by interaction outcomes, removed by other interactions or decay timers. Each state has a clear game mechanic, not just a visual effect.

| # | State | Mechanic | Visual effect | Contradicts |
|---|---|---|---|---|
| 0 | none | — | — | — |
| 1 | on_fire | DOT. Spreads to nearby objects via state interaction table | Fire particles + orange PointLight2D | frozen, wet |
| 2 | frozen | Immobilized. Extra damage from impacts. Removed by on_fire | Blue tint + ice shader | on_fire, molten |
| 3 | wet | Amplifies electrified damage. Resists on_fire | Drip particles | on_fire |
| 4 | electrified | DOT. Chains to nearby wet objects via state interaction table | Spark particles + periodic flash | — |
| 5 | poisoned | DOT. Doesn't spread | Green particles + green tint | — |
| 6 | corroded | Armor reduced (incoming damage increased) | Brown tint + crumble particles | — |
| 7 | molten | Contact damage to anything touching. Eventually destroys self | Orange glow + ripple shader | frozen |

This set is extensible — add new states when they have clear mechanics. States without game effects don't belong here.

### Contradiction table

Engine enforces on state add — adding a state automatically removes its contradictions:

```
on_fire:  removes [frozen, wet]
frozen:   removes [on_fire, molten]
wet:      removes [on_fire]
molten:   removes [frozen]
```

### Visual effects

Each state maps to a known engine-side visual effect. No LLM involved — purely rendering. No sprite regeneration for state changes — particles and shaders handle all state visuals.

### State decay

States applied by interactions have a default decay timer (e.g., 10s). The state is removed automatically after the timer expires unless re-applied. Continuous interactions (mode=1) re-apply the state each tick, keeping it active.

### State stacking

Objects can have multiple states simultaneously (on_fire AND poisoned AND corroded). Visual effects layer — particles from all active states render together. Contradictions prevent impossible combinations (can't be on_fire AND frozen).

---

## Affordances

What happens when the player presses interact near an object. Three mechanics, each a chunk of engine code:

| # | Affordance | Input | Engine mechanic |
|---|---|---|---|
| 0 | **carry** | Player presses interact | Object reparents as child of player. Player controls movement. Object loses independent physics while held. |
| 1 | **mount** | Player presses interact | Player reparents as child of object. Object physics govern movement. Player input steers the object. |
| 2 | **climb** | Player overlaps object | Player vertical velocity modified. Player moves upward while overlapping. No reparenting. |

One LLM call at creation, 1 token:
```
"When a player interacts with [horse]:
 0=carry it  1=ride it  2=climb it  3=nothing"
→ 1
```

### Carry mechanics

- **Pickup:** Object freeze = true, reparent under player's hand Marker2D
- **Use/swing:** Rotate hand through arc (tween), check overlaps during swing, apply held object's pairwise interactions against targets
- **Throw:** Reparent to scene, unfreeze, apply impulse in aim direction
- **Drop:** Same as throw, zero impulse

The held object IS the weapon. Player has no intrinsic attack damage — the held object's cached interactions determine attack effects. No held object → player can only kick (existing mechanic).

### Mount mechanics

- **Mount:** Player reparents under rideable object, player input redirects to object movement
- **Movement:** Object's mass/speed/gravity govern physics
- **Dismount:** Player reparents back to scene, input returns to normal

### Climb mechanics

- **While overlapping:** Player gains upward velocity (overrides gravity)
- **On exit:** Normal gravity resumes

### Some interactions are just carry + pairwise outcome

No separate affordance needed for:
- **Drinkable/edible:** carry + pairwise interaction with player → heal (negative damage)
- **Throwable:** carry + throw (release with impulse)
- **Pushable:** mass too high for carry → engine applies force instead of reparenting

---

## Creature behavior (per-pair)

Autonomous creatures don't have fixed behavior verbs. Instead, each creature×object relationship is evaluated independently at spawn time. A firefighter extinguishes fire, rescues people, and chases arsonists — different behavior for different targets.

### Movement patterns

| # | Movement | Engine behavior |
|---|---|---|
| 0 | **approach** | Move toward target, stop at contact |
| 1 | **flee** | Move away from target |
| 2 | **orbit** | Circle target at range |
| 3 | **ignore** | No movement reaction |

Each creature×object pair gets a movement (0-3) and a strength (0-100) at spawn time.

### On-arrival actions

For pairs where the creature approaches or orbits, the LLM decides what happens on arrival:

| # | Action | Parameters | Examples |
|---|---|---|---|
| 0 | **nothing** | — | Cat orbits ball of yarn, just watches |
| 1 | **damage** | amount (0-100) | Cop attacks criminal |
| 2 | **heal** | amount (0-100) | Doctor heals injured person |
| 3 | **add state** | state_id (1-7) | Wizard curses enemy (if cursed state existed) |
| 4 | **remove state** | state_id (1-7) | Firefighter removes on_fire from tree |
| 5 | **destroy** | — | Zombie destroys brain (instant kill) |
| 6 | **take** | — | Thief takes gold (pickup holdable) |

These are the same engine primitives as interaction outcomes. The creature behavior system and the pairwise collision cache both produce the same effect types — the engine doesn't care which system generated the effect.

### Staged evaluation

See [architecture.md](architecture.md) for the full staged evaluation flow. Three sequential stages, each parallel internally, each seeding context to the next. 1 token per call. ~104 calls for 3 creatures × 14 objects, ~180ms total.

### Priority resolution — utility scoring

When a creature has reactions to multiple objects, it picks ONE target per frame using utility scoring. Same pattern as The Sims and most single-agent game AI. The creature should look like it's making a decision — "going for the donut" or "running from the garlic" — not drifting at a blended angle.

```
For each (creature, object) pair with movement ≠ ignore:
  utility = strength / (1 + distance / perception_range)
  if movement == flee:
    utility *= 1.5   # survival bias

Pick highest utility pair.
  flee → move away from that object
  approach → move toward that object
  orbit → circle that object at range
```

Distance is normalized by perception range so falloff is relative to how far the creature can see, not absolute meters. A creature with 20m perception treats 10m as "half range" (utility halved), not "10 units away." The 1.5× flee multiplier ensures survival slightly overrides desire at equal strength and distance.

**Examples** (assuming perception_range = 20m):
- Vampire, garlic 2m (flee 90), human 5m (approach 85): garlic utility = 90×1.5/1.1 = 123, human utility = 85/1.25 = 68 → flees garlic
- Vampire, garlic 15m (flee 90), human 2m (approach 85): garlic utility = 90×1.5/1.75 = 77, human utility = 85/1.1 = 77 → tie, slight edge to flee → flees but barely
- Vampire, garlic 20m (flee 90), human 2m (approach 85): garlic utility = 90×1.5/2 = 67.5, human utility = 85/1.1 = 77 → approaches human

When the creature reaches contact range of an approach/orbit target, execute the on-arrival action from the pairwise cache.

If creatures need obstacle avoidance (curve around garlic to reach human), that's a pathfinding layer on top — not priority resolution. Defer until playtesting shows it's needed.

---

## Fields

Objects that affect nearby things without contact. Two creation-time questions:

```
"Does this affect nearby things without touching? 0=no 1=yes" → 1
"If yes, range in cm? (candle=50, campfire=250, bonfire=500, volcano=1000)" → 250
```

The engine creates an Area2D with that radius. Field interactions use the **same pairwise cache** as contact interactions — no separate system. A campfire's field interaction with a wooden wall: the cached result is "damage 20, add on_fire, continuous."

Fields tick every 2s (rate limit, part of cascade control). First tick is immediate via `call_deferred`.

---

## Destruction

When an object reaches 0 HP, it plays a death animation (shrink, fade, particle burst) and is removed from the scene. No runtime LLM calls or image generation.

See [future-features.md](future-features.md) for destruction remains (generating "pile of charred splinters" sprites).
