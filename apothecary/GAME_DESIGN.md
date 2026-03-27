# Apothecary — Game Design Document

> A 3D potion shop game where you craft items from ingredients, sell them to AI customers through real conversation, and manage a shop where your creations physically interact.
>
> "Shoppe Keep meets LLM-driven conversation, grounded by an invisible tag chemistry engine."

---

## Table of Contents

1. [Core Concept](#core-concept)
2. [The Three Loops](#the-three-loops)
3. [Crafting System](#crafting-system)
4. [Customer Conversation System](#customer-conversation-system)
5. [Shop Physics](#shop-physics--cascade-management)
6. [Progression](#progression)
7. [The Tag Engine (Invisible)](#the-tag-engine-invisible)
8. [Art Direction & 3D](#art-direction--3d)
9. [Technical Architecture](#technical-architecture)
10. [Prototype Scope](#prototype-scope)
11. [Open Questions](#open-questions)

---

## Core Concept

### The Elevator Pitch

You run a potion shop. Customers walk in and describe their problems — in their own words, through real conversation. You craft potions from ingredients, each with hidden properties. The potions you create are real objects that exist on your shelves and interact with each other through an invisible physics system. A hot potion next to flammable ingredients? Fire. A magnetic elixir near conducting items? Chaos.

The game is three things at once:
- **A crafting discovery game** — ingredients combine emergently, not through fixed recipes
- **A conversation game** — you talk to customers to figure out what they actually need
- **A shop management sim** — your inventory is a live cascade of interacting properties

### Why This Works as an AI Game

Most AI games feel random and generated — the LLM's output has no grounding, so nothing feels consistent or learnable. This game solves that with an **invisible tag system**:

- Every ingredient has hidden tags (HEAT_SOURCE, COLD, CONDUCTING, etc.)
- Every crafted potion gets tags determined by ingredient combination rules
- 43 interaction rules govern what happens when tagged objects meet
- The player never sees tags. They see: "fire burns flammable things" and "cold freezes liquids"

The LLM handles flavor (names, descriptions, conversation, art). The tag engine handles truth (does this potion actually work? does this shelf interaction cause a cascade?). The player experiences a world that makes sense and behaves consistently — the defining quality that separates this from "AI game" slop.

### Design Pillars

1. **Learnable, not random.** Same ingredients always produce the same result. The player builds a mental model of how the world works through experimentation.
2. **Conversation is gameplay.** Talking to customers isn't flavor — it's how you figure out what they need. Good questions lead to better sales.
3. **The shop is alive.** Items on shelves aren't inventory icons. They're physical objects with properties that interact. Managing the shop IS the action game.
4. **Start simple.** 4 ingredients, simple customers. Complexity grows with the player, not dumped upfront.

---

## The Three Loops

```
         CRAFT                    SELL                    MANAGE
    ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
    │ Combine 2-3  │         │ Customer     │         │ Items on     │
    │ ingredients   │────────▶│ walks in,    │────────▶│ shelves      │
    │ at cauldron   │         │ describes    │         │ interact via │
    │               │         │ problem      │         │ rule engine  │
    │ Tag engine    │         │              │         │              │
    │ determines    │         │ You chat,    │         │ Cascades     │
    │ properties    │         │ ask questions│         │ create chaos │
    │               │         │              │         │ or opportunity│
    │ LLM names &   │         │ Hand over    │         │              │
    │ describes it  │         │ a potion     │         │ Organize to  │
    │               │         │              │         │ prevent      │
    │ Sprite/model  │         │ LLM evaluates│         │ disasters    │
    │ generated     │         │ tag match    │         │              │
    └─────────────┘         └─────────────┘         └─────────────┘
          │                       │                       │
          └───────────────────────┴───────────────────────┘
                          FEEDBACK LOOP
              Successful sales → more customers → need more
              potions → need to manage more inventory → more
              cascade risk → need better organization
```

### Loop 1: CRAFT (Creative Expression)

- Walk to the cauldron. Select 2 (later 3) ingredients from your stock.
- The tag engine combines their properties: merges tag sets, fires interaction rules between them, resolves contradictions.
- The LLM generates a name, description, and visual for the result.
- The result is a new potion/item with real properties. Place it on a shelf, or hand it directly to a customer.
- **The player's skill:** learning what ingredient combinations produce useful results. Predicting outcomes based on past experience.

### Loop 2: SELL (Social Puzzle)

- Customers walk in and describe their problems in natural language via LLM.
- The player chats freely — asking questions, offering suggestions, learning what's really needed.
- When ready, the player picks an item from the shelf and hands it over.
- The LLM evaluates: do the item's hidden tags address the customer's hidden need-tags?
- Customer reacts: delighted, satisfied, confused, or angry.
- **The player's skill:** extracting useful information from conversation. Reading between the lines. Matching the right potion to the right problem.

### Loop 3: MANAGE (Emergent Challenge)

- Every item in the shop is a real tagged object. The rule engine checks nearby items periodically.
- Dangerous combinations cascade: fire spreads, cold transfers, electricity chains, corrosion eats.
- The player must organize intelligently: separate heat from flammables, insulate volatile items.
- As inventory grows, management becomes harder — more items = more potential cascades.
- **The player's skill:** spatial reasoning. Risk assessment. Learning which tag combinations are dangerous neighbors.

### How the Loops Interlock

- **Craft feeds Sell:** You need the right potions for your customers.
- **Sell feeds Manage:** Successful sales mean more customers, which means more inventory to manage.
- **Manage constrains Craft:** You might WANT to craft a powerful molten potion, but can you safely store it?
- **Cascades affect Sell:** A shelf fire destroys your stock right before a customer needs it.

---

## Crafting System

### Ingredients

Each ingredient has a name, a visual appearance (generated sprite/model), and **hidden tags** the player never sees.

#### Starter Ingredients (4)

| Ingredient | Visual Hint | Hidden Tags | Why These Tags |
|------------|------------|-------------|----------------|
| Firebloom | Red-orange flower, warm glow | HEAT_SOURCE, FLAMMABLE | Fire-themed. Note: it's flammable itself — a hint to the player that fire ingredients are volatile. |
| Frostmint | Blue crystalline herb, frost on leaves | COLD, FROZEN | Cold-themed. Solid (frozen), so it behaves differently from liquid cold. |
| Iron Dust | Grey metallic powder in a jar | CONDUCTING, HEAVY, SOLID | Metal-themed. Conducting is the key property — it chains reactions. |
| Honey Moss | Green-gold living moss | STICKY, FLEXIBLE, LIVING | Organic-themed. LIVING and STICKY are unusual tags that create unique combinations. |

#### Unlockable Ingredients (examples, not exhaustive)

| Ingredient | Hidden Tags | Unlock Condition |
|------------|------------|------------------|
| Thundersap | ELECTRIC, LIQUID | Week 2 — supplier delivers |
| Ashite Powder | EXPLOSIVE, BREAKABLE | Week 3 — found in ruins |
| Mirrorleaf | REFLECTIVE, LIGHT, FLEXIBLE | Week 2 — customer gift |
| Acidbark | CORROSIVE, RIGID, SOLID | Week 3 — foraging expedition |
| Driftweed | FLOATING, LIGHT, GAS | Week 2 — market purchase |
| Glowcap Mushroom | GLOWING, LIVING, TOXIC | Week 4 — deep forest |
| Magnetite Shard | MAGNETIC, HEAVY, SOLID | Week 3 — mine expedition |
| Slickstone | SLIPPERY, SOLID, BOUNCY | Week 2 — river collection |

### How Crafting Works (Tag Combination Logic)

When two ingredients are combined:

1. **Start with the union** of both tag sets.
2. **Fire interaction rules** between the two tag sets (using the existing 43-rule engine).
   - HEAT_SOURCE + FROZEN → FROZEN removed, LIQUID added (melt rule)
   - COLD + MOLTEN → SOLID + RIGID added, MOLTEN + LIQUID removed (solidify rule)
   - ELECTRIC + CONDUCTING → ELECTRIC propagates (both keep it)
3. **Resolve contradictions** — if the result has contradictory tags (HEAVY + LIGHT, HOT + COLD), the tag from the higher-priority rule survives.
4. **Cap at 6 tags** (budget system). If more than 6 remain, drop lowest-cost tags first.
5. **Send to LLM** — given the resulting tag set, generate a name and visual description.
6. **Generate sprite/model** — the image/model pipeline creates the potion's appearance.

### Example Crafts

```
Firebloom (HEAT_SOURCE, FLAMMABLE) + Frostmint (COLD, FROZEN)
  → Union: HEAT_SOURCE, FLAMMABLE, COLD, FROZEN
  → Rules fire: HEAT_SOURCE melts FROZEN → remove FROZEN, add LIQUID
  → Rules fire: COLD + HOT contradiction... HEAT_SOURCE wins (higher priority rule)
  → Result: HEAT_SOURCE, FLAMMABLE, LIQUID
  → LLM names it: "Warmspring Draught"
  → A warm, flammable liquid — useful for warming, dangerous near fire

Firebloom (HEAT_SOURCE, FLAMMABLE) + Iron Dust (CONDUCTING, HEAVY, SOLID)
  → Union: HEAT_SOURCE, FLAMMABLE, CONDUCTING, HEAVY, SOLID
  → Rules fire: HEAT_SOURCE + CONDUCTING → HOT added (heat conduction rule)
  → Result: HEAT_SOURCE, HOT, CONDUCTING, HEAVY, SOLID
  → Note: FLAMMABLE removed because HEAT_SOURCE + FLAMMABLE contradiction
  → LLM names it: "Molten Iron Tonic"
  → A hot, heavy, conducting solid — useful for metalwork, dangerous near... everything

Frostmint (COLD, FROZEN) + Honey Moss (STICKY, FLEXIBLE, LIVING)
  → Union: COLD, FROZEN, STICKY, FLEXIBLE, LIVING
  → Rules fire: FROZEN + LIVING → frostbite effect (damages LIVING, but in crafting context we interpret as "preserved")
  → Result: COLD, FROZEN, STICKY, LIVING
  → FLEXIBLE removed by FROZEN+RIGID interaction
  → LLM names it: "Everfrost Salve"
  → Cold, sticky, living compound — useful for preservation, cooling, wound-sealing

Iron Dust (CONDUCTING, HEAVY, SOLID) + Honey Moss (STICKY, FLEXIBLE, LIVING)
  → Union: CONDUCTING, HEAVY, SOLID, STICKY, FLEXIBLE, LIVING
  → No rules fire between these tags (no interaction rules for these combos)
  → Result: all 6 tags preserved
  → LLM names it: "Lodestone Paste"
  → Heavy, sticky, conducting, living paste — unique utility (conducts, sticks, alive)
```

### Crafting UX

1. Player walks to cauldron, interacts.
2. Ingredient selection UI opens — shows available ingredients by name and appearance.
3. Player selects 2 (or 3 at higher levels). Confirms.
4. Cauldron starts brewing — takes real time (see below).
5. Result appears: name, description, appearance. Player picks it up.
6. Player places it on a shelf, or holds it for a customer.

### Cauldron Brew Time & 3D Model Quality

The cauldron doesn't produce a potion instantly. Brewing takes real time — **15–45 seconds** depending on ingredient complexity. This isn't just flavor.

**The insight:** Generation time is an asset. In Makeshift, sprite generation happens as fast as possible because the player is standing there waiting. In Apothecary, the cauldron's brew time is a natural window — the player walks away, serves a customer, organizes a shelf. We can use that window to run a much better generation pipeline than a fire-and-forget approach allows.

**What happens during brew time:**

```
Player confirms ingredients → cauldron animation begins
  ↓
BACKGROUND (invisible to player):
  → Tag engine resolves combination → final tag set
  → LLM generates name + visual description from tag set
  → 3D generation pipeline starts (Meshy / Tripo / Rodin)
  → Tag validation pass: does the model look like what the tags say it is?
      - Does a COLD potion look cold?
      - Does STICKY read as viscous or gooey?
      - Does HEAT_SOURCE have visual warmth (glow, color temperature)?
  → If validation fails: refine prompt, regenerate (one retry)
  ↓
Brew timer expires → cauldron done animation
  ↓
Player picks up the result — name and appearance revealed at this moment
```

**Why validation during brew time produces better results:**

| Approach | Quality | Player Experience |
|----------|---------|------------------|
| Instant (Makeshift pattern) | Average — first attempt, no validation | Player waits; any delay feels wrong |
| Brew-time pipeline | High — validated, retry-eligible | Player is busy; wait is invisible |

The brew timer is tuned to match the pipeline, not the other way around. A faster generation backend shortens the brew time. A slower one stretches it. The mechanic is honest — the cauldron is actually working.

**Brew time by complexity:**

| Potion Type | Brew Time | Pipeline |
|-------------|-----------|----------|
| 2 starter ingredients | ~15s | Single generation pass, light validation |
| 2 exotic/unlocked ingredients | ~25s | Single pass, stricter validation |
| 3-ingredient combination | ~40s | Two generation passes, full validation, one retry budget |

**Brew time as a design lever:**

- The wait is never punishment — the player should always have something to do while waiting (serve a customer, restock a shelf, chat). If there's nothing to do, the shop isn't busy enough yet, which is an early-game problem that naturally resolves.
- A future "Quick Brew" upgrade trades quality for speed — reverts to the Makeshift pattern (first attempt, no retry). The tradeoff is explicit: faster stock, uglier bottles.
- The reveal at pickup is intentional. The player doesn't watch a progress bar — they get a surprise when they come back. Discovery feels better than monitoring.

---

## Customer Conversation System

### How Customers Work

Each customer is generated with:
- **Need-tags** (hidden): the tag properties that would solve their problem (e.g., HEAT_SOURCE for warmth, STICKY + LIVING for wound-sealing)
- **Personality**: tone, chattiness, honesty level (generated by LLM)
- **Opening line**: natural language description of their problem
- **Budget**: how much they can pay (scales with difficulty of need)

### Conversation Flow

```
Customer enters shop → walks to counter
  ↓
Opening line displayed: "I've been having terrible headaches
  ever since the cold snap hit. Nothing I've tried helps."
  ↓
Player types freely. Examples:
  - "When do the headaches happen?"
  - "Have you tried staying warm?"
  - "Is it more of a sharp pain or a dull ache?"
  ↓
LLM responds in character, guided by need-tags:
  "They're worst in the morning when the cabin is coldest.
   A dull, throbbing ache. My neighbor suggested warm
   compresses but I can't keep them hot long enough."
  ↓
Player now has clues: COLD-related, needs sustained HEAT_SOURCE
  ↓
Player picks up "Warmspring Draught" (HEAT_SOURCE, FLAMMABLE, LIQUID)
  from shelf and hands it to customer
  ↓
LLM evaluates: HEAT_SOURCE matches need? YES.
  Sustained warmth? LIQUID form can be applied. Good match.
  ↓
Customer: "Oh! I can feel the warmth already just holding the
  bottle. This is exactly what I needed. Thank you!"
  → Reputation +2, Gold +50
```

### Customer Archetypes (Prototype Set)

| Archetype | Example Opening | Hidden Need-Tags | Difficulty |
|-----------|----------------|-----------------|------------|
| **Cold Traveler** | "The mountain pass is freezing this time of year..." | HEAT_SOURCE or INSULATING | Easy |
| **Injured Worker** | "Cut myself at the mill, won't stop bleeding..." | STICKY + LIVING (clotting) | Easy |
| **Worried Farmer** | "Something's been destroying my crops at night..." | TOXIC or HEAT_SOURCE (repellent) | Medium |
| **Nervous Bride** | "Outdoor wedding tomorrow. The forecast says rain and cold." | HEAT_SOURCE + WIND_SOURCE | Medium |
| **Sick Child's Parent** | "My daughter has a fever but she's also shivering..." | COLD (reduce fever) but NOT FROZEN | Hard (nuanced) |
| **Suspicious Stranger** | "I need something... potent. Don't ask questions." | EXPLOSIVE or CORROSIVE | Moral choice |
| **Rival Alchemist** | "I hear you've been making quite a name for yourself..." | Tests your knowledge, not a real need | Story event |
| **Returning Customer** | "That salve you sold me last week worked wonders!" | Varies — references past sale | Continuity |

### Conversation Design Principles

1. **The conversation IS the puzzle.** A player who asks no questions and just hands over a random potion will get mediocre results. A player who asks targeted questions narrows down the need and can match precisely.

2. **Multiple valid solutions.** "I'm cold" can be solved by HEAT_SOURCE (warming potion), INSULATING (protective coating), or removing the COLD source. Different potions = different customer reactions.

3. **Partial matches are okay.** A potion with 1 of 2 needed tags gets a lukewarm reaction: "This helps a bit, but I was hoping for something more." Reputation +1 instead of +2.

4. **Bad matches have consequences.** Give a CORROSIVE potion to someone with a skin condition. The customer is NOT happy. Reputation -2.

5. **Some customers are tricky.**
   - The vague customer: "I just need something... you know, for energy." (Could be HEAT_SOURCE, could be ELECTRIC, could be LIVING)
   - The lying customer: says they need medicine, actually wants EXPLOSIVE (for dubious purposes)
   - The picky customer: needs a very specific combo and won't settle for partial matches

6. **Returning customers build story.** A customer you helped well comes back with a new problem — and references the past: "That warming draught saved my trip. Now I need something for my brother..."

### LLM Architecture for Conversations

```
System Prompt:
  You are [customer_name], a [personality] who has come to
  a potion shop. Your problem: [problem_description].

  You need a potion with these properties (DO NOT reveal
  these directly): [need_tags].

  Respond naturally to the shopkeeper's questions. Give
  hints about your problem that could help them figure out
  what you need, but don't say "I need a HEAT_SOURCE potion."

  When the shopkeeper offers you an item:
  - If item tags match your needs well: express delight
  - If partial match: express mild satisfaction, hint at what's missing
  - If bad match: express disappointment or concern
  - If dangerous match: express alarm

Context provided per turn:
  - Conversation history
  - Player's offered item (if any) with hidden tags
  - Customer's need-tags (for evaluation)
  - Player's shop inventory (names only, for natural reference)
```

---

## Shop Physics / Cascade Management

### The Core Idea

Your shop is a physical space. Items on shelves are real tagged objects. The rule engine checks proximity between items periodically. When nearby items have interacting tags, rules fire and effects happen.

**This is NOT a simulation running every frame.** It's event-driven:
- When an item is placed on a shelf → check what's nearby → fire rules if applicable
- On a slow tick (every ~5 seconds) → check all shelf neighbors → fire any new rules
- When a cascade happens → immediate neighbor re-check → can chain

### Shelf Interactions the Player Discovers

| Scenario | What Happens | Rule Triggered |
|----------|-------------|----------------|
| Hot potion next to Firebloom | Firebloom ignites (it's FLAMMABLE) | HEAT_SOURCE + FLAMMABLE → ignition |
| Fire spreads to other shelf items | Nearby FLAMMABLE items also catch fire | Cascade: fire propagates |
| Molten Iron Tonic next to Frostmint | Frostmint melts (FROZEN removed, becomes LIQUID) | HEAT_SOURCE + FROZEN → melt |
| Thundersap next to Iron Dust | Iron Dust becomes electrified | ELECTRIC + CONDUCTING → electrify (cascade) |
| Acidbark touching a wooden shelf | Shelf takes damage over time | CORROSIVE + BREAKABLE → corrode |
| Magnetic potion near conducting items | Items pulled toward it, knocked off shelf | MAGNETIC + CONDUCTING → attraction force |
| Toxic potion in an open container | Nearby LIVING ingredients wilt | TOXIC + LIVING → poison |

### What the Player Learns (Organically)

- "Keep fire stuff away from plant ingredients"
- "I need a special cabinet for the electric and conducting items"
- "Acidic things eat through regular shelves — I need a stone shelf"
- "Magnetic items need their own corner, away from anything metallic"

### Shop Upgrades That Help

| Upgrade | What It Does | Unlocked |
|---------|-------------|----------|
| **Stone Shelf** | RIGID, not BREAKABLE — resists corrosion and fire | Week 2 |
| **Insulated Cabinet** | Items inside don't interact with items outside | Week 3 |
| **Fireproof Vault** | INSULATING — blocks heat cascade | Week 3 |
| **Magnetic Shield** | Blocks MAGNETIC force from spreading | Week 4 |
| **Ventilated Rack** | GAS and TOXIC items dissipate safely | Week 4 |
| **Larger Shop** | More shelf space, more room to separate items | Week 5+ |

### Cascade Events as "Action Moments"

Instead of Shoppe Keep's bolt-on combat (fighting thieves with a sword), our action moments ARE the shop mechanics:

- **Fire breaks out:** A customer bumps a shelf. Your hot potion falls against your Firebloom stock. Fire spreads. You grab items off the burning shelf, stamp out the fire (interact with LIQUID items to extinguish), and assess the damage.
- **Electric chain:** Your Thundersap leaks near the metal shelf. Everything conducting on that shelf electrifies. You need to isolate the source.
- **Corrosion:** You forgot to move the Acidbark off the wooden shelf overnight. Morning: the shelf has a hole and three potions fell through.

These are the "oh no" moments that break up the routine and teach the player about the tag system without ever showing them a tag.

---

## Progression

### Day/Night Cycle

Stolen directly from Shoppe Keep:

| Phase | Duration | What Happens |
|-------|----------|-------------|
| **Morning** | ~2 min | Open shop. 1-2 early customers. Light traffic. |
| **Midday** | ~3 min | Peak traffic. 3-4 customers. Busiest crafting period. |
| **Afternoon** | ~2 min | Traffic dies down. 1-2 late customers. |
| **Evening/Night** | ~3 min | Shop closed. Restock, reorganize, craft for tomorrow, upgrade. |

### Weekly Progression

| Week | Ingredients | Customers | Complexity | Milestone |
|------|------------|-----------|------------|-----------|
| 1 | 4 starter | Simple, direct needs | Single-tag matches | Learn crafting basics |
| 2 | 6-8 | Multi-tag needs, first returner | First shelf cascade | Unlock stone shelves, new supplier |
| 3 | 10-12 | Tricky customers, lying customers | Multi-step cascades | Unlock insulated storage, foraging |
| 4 | 14-16 | Complex multi-need problems | Dangerous ingredients | Unlock fireproof vault, town events |
| 5+ | 16-20 | Story climax customers, rare needs | Full cascade management | Endgame upgrades, story resolution |

### Economy

- **Income:** Selling potions to customers. Price based on tag complexity and match quality.
- **Expenses:** Buying ingredients (from suppliers, market, foraging expeditions). Shop upgrades. Replacing damaged stock.
- **Tension:** More complex potions sell for more, but are harder to store safely. Risk vs reward.

### Reputation

- Successful sales increase reputation. Failed sales decrease it.
- Higher reputation → more customers → more complex needs → more money → but also more inventory to manage.
- Reputation unlocks: new customer types, story events, ingredient suppliers.

### Story Beats (Light Narrative)

The story comes to you through customers. You don't leave the shop (mostly).

- **Week 1:** Establish yourself. Simple customers. A friendly neighbor introduces you.
- **Week 2:** Word spreads. A regular customer becomes a friend. A suspicious stranger appears.
- **Week 3:** The town has a problem (cold snap / plague / monster sightings). Demand surges. What you sell matters.
- **Week 4:** Consequences of your past sales manifest. The stranger's true purpose revealed.
- **Week 5+:** Crisis resolution. Your shop's reputation determines the outcome.

---

## The Tag Engine (Invisible)

### Why Invisible?

The player never sees "HEAT_SOURCE" or "CONDUCTING." They see:
- A red potion that feels warm to the touch
- A grey dust that seems to react to nearby metals
- A customer who says "I need warmth"

The tag system is the **contract between the LLM and the game engine.** The LLM can be creative with names, descriptions, and conversation — but it cannot violate the tag grounding. A potion with HEAT_SOURCE tags will always warm things. Always. This consistency is what makes the game feel like a real world instead of random AI generation.

### Tags We Use (From Existing Engine)

The full 30-tag system from Makeshift is available. For the prototype, these are most relevant:

**Commonly used in crafting:**
- HEAT_SOURCE, COLD, FROZEN, HOT, MOLTEN (temperature)
- SOLID, LIQUID, GAS (state)
- CONDUCTING, INSULATING (electrical)
- FLAMMABLE, EXPLOSIVE (energy)
- STICKY, SLIPPERY (surface)
- LIVING, TOXIC, CORROSIVE (organic/chemical)
- MAGNETIC, ELECTRIC (force)

**Useful for shop management:**
- BREAKABLE (containers, shelves)
- HEAVY, LIGHT (physics/placement)
- FLOATING, WIND_SOURCE (atmospheric effects)
- GLOWING (visual — attracts customers?)

### Rules We Use (From Existing Engine)

All 43 rules from Makeshift carry over. The most gameplay-relevant for the shop:

- **Fire cascade:** HEAT_SOURCE + FLAMMABLE → ignition (cascade-eligible)
- **Melt:** HEAT_SOURCE + FROZEN → remove FROZEN, add LIQUID
- **Freeze:** COLD + LIQUID → add FROZEN, RIGID, SOLID
- **Electrify:** ELECTRIC + CONDUCTING → spread ELECTRIC (cascade-eligible)
- **Corrode:** CORROSIVE + BREAKABLE → damage over time
- **Toxic spread:** TOXIC + GAS → spread TOXIC (cascade-eligible)
- **Magnetic pull:** MAGNETIC + CONDUCTING → attraction force
- **Extinguish:** LIQUID + HEAT_SOURCE → remove HEAT_SOURCE

### What Might Need to Change

- **New rules for crafting-specific interactions** — some combinations don't have rules in the combat-oriented set. May need ~10-15 new rules for ingredient interactions.
- **Softer effects** — existing rules deal damage (25-99999 HP). In a shop context, "damage" means "item degradation" not "health loss." Might need to reinterpret or scale effects.
- **Shelf-as-object** — shelves themselves could have tags (wooden shelf = BREAKABLE + FLAMMABLE, stone shelf = RIGID + SOLID). Rules fire between shelf and item.

---

## Art Direction & 3D

### Visual Style

Carry over the **mixed media collage / paper craft diorama** aesthetic from Makeshift, but in 3D:

- Shop interior feels like a handcrafted diorama / dollhouse
- Items look like paper craft / clay craft objects
- Low-poly, stylized, warm lighting
- Think: Tearaway, Paper Mario TTYD, or a cozy craft-store aesthetic
- NPCs are simple, expressive, slightly exaggerated — not realistic

### 3D Asset Generation

For potion/ingredient models, options:

| Approach | Quality | Speed | Cost | Style Consistency |
|----------|---------|-------|------|-------------------|
| **Text-to-3D API** (Meshy, Tripo, Rodin) | Medium | 15-60s | $0.05-0.20/model | Low — needs post-processing |
| **Generated 2D sprites on billboards** | Good (for stylized) | 5s | $0.01-0.05/sprite | High — same pipeline as Makeshift |
| **Pre-made base meshes + color/texture variation** | Good | Instant | Free (upfront art cost) | Very high |
| **Hybrid: hand-made bottle/jar meshes + generated labels** | Very good | 5s for label | Low | Very high |

**Recommended for prototype: Hybrid approach.** Hand-model 4-5 base container shapes (round bottle, tall vial, jar, pouch, bowl). Generate 2D label/texture art via existing sprite pipeline. Apply as texture. This gives: fast generation, consistent style, real 3D feel.

For ingredients: similar approach. A few base mesh types (flower, crystal, powder-in-jar, moss-clump) with generated texture variation.

### Shop Environment

Hand-built. The shop interior is a fixed (upgradeable) 3D scene:
- Wooden walls, floor, ceiling
- Shelves, tables, counter, cauldron
- Door for customers to enter
- Windows for lighting
- Upgradeable furniture (stone shelves, insulated cabinets, etc.)

### Camera

Options:
- **First-person** (like Shoppe Keep) — most immersive, pick up items with your hands
- **Third-person isometric** — better overview of shop, easier shelf management
- **Fixed overhead** — simplest, but less engaging

Recommend: **First-person for the full game, third-person isometric for the prototype** (faster to implement, easier to see shelf interactions).

---

## Technical Architecture

### What We Reuse from Makeshift

| System | Source Files | Reuse Level |
|--------|------------|-------------|
| Tag model + costs + contradictions | `backend/app/models/tags.py` | 100% |
| Rule engine + resolver | `backend/app/engine/resolver.py` | 100% |
| 43 interaction rules | `backend/app/engine/rules_data.py` | 100% |
| Effect system | `backend/app/models/effects.py` | 100% |
| Behavior triggers | `backend/app/models/behaviors.py` | 70% (subset) |
| LLM agent pattern | `backend/app/creator/agent.py` | Pattern only — new prompts |
| Sprite generation pipeline | `backend/app/images/pipeline.py` | 100% |
| Gemini image client | `backend/app/images/gemini_client.py` | 100% |
| FastAPI structure | `backend/app/main.py` | Pattern reuse |
| WebSocket delivery | `backend/app/ws/handler.py` | 90% |
| Session persistence | `backend/app/sessions/manager.py` | 70% (new tables) |

### New Backend Systems

| System | Purpose | Estimated Size |
|--------|---------|---------------|
| **Crafting resolver** | Merge tag sets, fire rules, resolve contradictions, cap budget | ~200 lines |
| **Crafting agent** | LLM prompt for naming/describing crafted results | ~100 lines + prompt |
| **Customer generator** | LLM prompt for generating customer with need-tags and personality | ~150 lines + prompt |
| **Conversation agent** | LLM prompt for customer dialogue, maintaining context | ~200 lines + prompt |
| **Evaluation agent** | LLM prompt for evaluating item-to-need match | ~100 lines + prompt |
| **Craft API routes** | `/craft`, `/customer/*`, `/shop/*` endpoints | ~300 lines |
| **Shop state model** | Shelf contents, positions, proximity graph | ~200 lines |
| **Cascade simulator** | Run rule engine on shelf contents, return events | ~150 lines |

### Godot Architecture (3D, New Project)

```
Autoloads/
├── EventBus         — Signal bus (reuse pattern)
├── Backend          — HTTP + WebSocket client (reuse)
├── GameManager      — State machine: MENU, SHOPPING, CRAFTING, DIALOGUE
├── RuleEngine       — Client-side rule matching (reuse logic)
└── ShopManager      — Customer spawning, time progression, economy

Scenes/
├── shop/
│   ├── Shop.tscn           — 3D shop interior (hand-built)
│   ├── Shelf.tscn          — Shelf with item slots
│   ├── Cauldron.tscn       — Crafting station
│   └── Counter.tscn        — Customer interaction point
├── items/
│   ├── ShopItem.tscn       — 3D item (base mesh + generated texture)
│   └── Ingredient.tscn     — Raw ingredient variant
├── npcs/
│   ├── Customer.tscn       — Customer NPC (walk in, talk, leave)
│   └── CustomerSpawner.gd  — Manages customer queue
└── ui/
    ├── DialoguePanel.tscn  — Free text chat interface
    ├── CraftingPanel.tscn  — Ingredient selection UI
    ├── ShopHUD.tscn        — Gold, reputation, time of day
    └── ItemTooltip.tscn    — Item name/description on hover

Scripts/
├── logic/                  — PURE LOGIC (no spatial nodes, 100% portable)
│   ├── inventory.gd        — What items exist, where they are
│   ├── recipe_cache.gd     — Known crafting results
│   ├── customer_state.gd   — Active customer data
│   └── shop_economy.gd     — Gold, reputation, pricing
├── systems/
│   ├── cascade_checker.gd  — Periodic shelf proximity check → rule engine
│   ├── effect_executor.gd  — Apply rule effects to shop items (adapted)
│   └── item_placer.gd      — Pick up, carry, place items on shelves
└── data/
    ├── ingredient_data.gd  — Starter + unlockable ingredient definitions
    └── customer_data.gd    — Customer archetype definitions
```

**Key architectural decision: logic/ is pure GDScript with no Node dependencies.** This makes it 100% portable between 2D and 3D. If we ever change camera, renderer, or perspective, only the scenes and spatial scripts change.

### API Endpoints (New)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/sessions` | Create session (same as Makeshift) |
| POST | `/api/sessions/{id}/craft` | Combine ingredients → return result blueprint |
| POST | `/api/sessions/{id}/customer/generate` | Generate next customer (need-tags, personality, opening line) |
| POST | `/api/sessions/{id}/customer/chat` | Send player message → get customer response |
| POST | `/api/sessions/{id}/customer/evaluate` | Hand item to customer → get reaction + reputation change |
| GET | `/api/sessions/{id}/shop` | Get current shop state (shelves, items, positions) |
| PUT | `/api/sessions/{id}/shop/place` | Place item on shelf at position |
| GET | `/api/sessions/{id}/shop/cascade` | Check for pending cascade events |
| GET | `/api/rules` | Download rules (same as Makeshift, with any new rules) |

---

## Prototype Scope

### What's In

| Feature | Description |
|---------|-------------|
| 3D shop scene | Single room, 4-6 shelves, cauldron, counter, door |
| 4 ingredients | Firebloom, Frostmint, Iron Dust, Honey Moss |
| Crafting | Combine 2 ingredients at cauldron |
| 5 customer types | Cold traveler, injured worker, farmer, bride, stranger |
| Free text chat | Type to customers, LLM responds |
| Item evaluation | Hand item to customer, LLM evaluates match |
| Shelf physics | Items interact on shelves via rule engine |
| Basic cascade | Fire spread, melt, freeze, electrify |
| Simple economy | Gold from sales, ingredients cost gold |
| Isometric camera | Third-person view of shop (simpler than first-person) |

### What's NOT In

| Feature | Why Deferred |
|---------|-------------|
| Day/night cycle | Just spawn customers in sequence for prototype |
| Town consequences | Too complex — just test shop-level gameplay |
| Progression/unlocks | Handwave — all 4 ingredients available |
| Skill tree | No upgrades beyond basic shelves |
| Foraging/gathering | Ingredients are "in stock" |
| Advanced shop upgrades | Only basic wooden + stone shelves |
| Save/load | Single session |
| Returning customers | No persistence between sessions |
| Generated 3D models | Use hybrid approach (base mesh + texture) |
| Music/SFX | Placeholder or silent |
| First-person camera | Isometric is faster to prototype |

### Success Criteria

The prototype is successful if:

1. **Crafting feels like discovery.** A playtester can craft 3+ potions and correctly predict what a new combination will do based on past experience.
2. **Conversations feel like gameplay.** A playtester enjoys figuring out what a customer needs through dialogue, and gets a better result by asking good questions.
3. **Shop management creates tension.** A playtester has at least one "oh no" moment from a shelf cascade and then intentionally reorganizes their shop.

If any of these three fail, we know exactly which hypothesis is wrong and can pivot before investing further.

---

## Open Questions

1. **Crafting depth:** Is 2-ingredient combination enough, or do we need 3-ingredient combinations from the start for interesting results?
2. **Customer patience:** How long does a customer wait? Do they leave if you take too long? Or is it untimed (more relaxed)?
3. **Cascade severity:** How punishing should shelf disasters be? Lose the item? Lose the shelf? Just a visual warning?
4. **Ingredient replenishment:** In the prototype, do ingredients auto-restock? Or does the player buy them (requiring money management from day 1)?
5. **Conversation length:** Should there be a natural limit to how long you can chat with a customer? Or do they wait forever while you figure it out?
6. **Name of the game:** "Apothecary" is a working title. Final name TBD.
7. **Multiplayer potential:** Could two players run competing shops? Co-op the same shop? Deferred but worth considering architecturally.
