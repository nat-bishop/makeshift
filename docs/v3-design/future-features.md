# V3 Future Features

Ideas explored during design that aren't part of the core system. Each could be added independently once the base architecture is working.

---

## Compound object sprites

When a creature picks up a holdable object, generate a combined sprite ("zombie holding fire sword") instead of using child sprite positioning.

**How:** FLUX supports reference image input. Pass both the creature sprite and the held object sprite as references → generate a combined image that maintains visual consistency.

**Pre-caching:** At spawn, generate compound sprites for all (creature × holdable) pairs in background. With 3 creatures and 5 holdables: 15 requests, async, non-blocking. Cached before any creature reaches any holdable.

**Dropping:** Compound splits back to originals (both cached from creation — instant).

**Why deferred:** The core carry/mount mechanics work with child sprite positioning (object sprite attached to holder's hand point). Compound sprites add visual polish but require reliable reference image generation and add image gen load during gameplay. Worth testing once the base system works.

---

## Creature death remains

When an autonomous creature dies, generate a "dead creature" sprite instead of just playing a death animation and removing it.

**How:** Same as destruction results — "A [zombie cop] is killed. What does the body look like? 3-5 words." → "fallen cop in tattered uniform" → background image gen.

**Why deferred:** The destruction results system handles this for non-creature objects. Creature death sprites are a visual polish feature, not a mechanic.

---

## Object evolution

Objects that accumulate states could fundamentally change identity. A wooden shield that's been on_fire → corroded → repeatedly damaged might become a "battered charred ruin" with different physics and interactions.

**How:** After N state changes or at specific HP thresholds, ask: "A [wooden shield] has been burned and corroded. What is it now? 3-5 words." → new object identity → full creation graph + new sprite.

**Why deferred:** Requires defining triggers for identity change (how many state changes? which combinations?). The state interaction table handles state effects mechanically — evolution adds narrative emergence but needs design work to feel intentional rather than random.

---

## Additional states

The core system ships with 7 states. Potential additions once mechanics are designed:

| State | Potential mechanic | Needs design work |
|---|---|---|
| blessed | Damage bonus vs cursed objects? Heal over time? | What's the game-meaningful effect? |
| cursed | Damage reduction? Attract hostile creatures? | How does it interact with other states? |
| weakened | Reduced mass/force output? | How much reduction? Duration? |
| strengthened | Increased mass/force output? | How much increase? Duration? |
| petrified | Convert to stone physics (high mass, high armor, immobile)? | Does it change all physics properties? |

Each state should only be added when it has a clear mechanic, not just a visual effect.

---

## Additional affordances

The core system ships with 3 affordances (carry, mount, climb). Potential additions:

| Affordance | Engine mechanic needed | Complexity |
|---|---|---|
| shootable | Projectile spawn, aim UI, fire rate | Medium |
| attachable | Physics joints, rope/chain, tension, breaking | Hard |
| containable | Child object storage, open/close UI, capacity | Medium |
| openable | State toggle, collision shape swap | Simple |
| wearable | Equipment slots, stat modification overlay | Medium |

Each requires engine code before it can be added to the LLM classification list.
