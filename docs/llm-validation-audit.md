# LLM Validation Audit: Where Scribblenauts' Three Inherited Problems Live in Our Code

Scribblenauts hand-authored every object, so determinism was free and cultural accuracy was a QA problem, not an architectural one. We replaced the six-month Wikipedia pipeline with an LLM call, which bought us infinite dictionary breadth but inherited three failure modes 5th Cell never had to worry about: **contradictory tags**, **culturally wrong tags**, and **non-deterministic outputs across sessions**. This audit traces each failure mode through our codebase, identifies where it can happen today, and proposes a concrete validation layer.

---

## 1. Contradictory Tags ("fireproof flammable")

### What Scribblenauts Taught Us

Scribblenauts' adjective system (Section 3 of the Compass doc) applied property deltas from ~10,000 adjectives onto a 10-tab schema. A "fireproof flammable" conflict was impossible because adjectives were hand-authored property bundles — a human sorted 80,000 candidates and deleted the ones that didn't make sense. Material adjectives like "Metal" simply overrode fire reaction to "No Damage." Contradictions were caught at authoring time, not runtime.

We don't have that luxury. Our LLM generates tag sets on every object creation call. The contradiction must be caught programmatically or not at all.

### Where It Lives Today

**Enforcement point:** `backend/app/models/blueprint.py:50-60`

```python
@field_validator("tags")
@classmethod
def check_contradictions(cls, tags: list[Tag]) -> list[Tag]:
    tag_set = set(tags)
    for pair in TAG_CONTRADICTIONS:
        if pair <= tag_set:
            a, b = sorted(pair, key=lambda t: t.value)
            raise ModelRetry(f"{a.value} and {b.value} cannot coexist. Remove one.")
    return tags
```

**Contradiction definitions:** `backend/app/models/tags.py:89-102` — 12 `frozenset` pairs.

This validator catches the LLM outputting `[FROZEN, HOT]` or `[SOLID, LIQUID]`. The `ModelRetry` mechanism gives the LLM structured feedback ("FROZEN and HOT cannot coexist. Remove one.") and up to 3 retries to fix it.

### Gaps

The 12 pairs cover physical-state and temperature contradictions well. But several semantically contradictory combinations slip through:

| Tag Pair | Why It's Contradictory | Currently Caught? |
|----------|----------------------|-------------------|
| FROZEN + MOLTEN | Ice can't be lava | Yes |
| SOLID + LIQUID | Mutually exclusive states | Yes |
| HEAVY + LIGHT | Contradictory mass | Yes |
| INSULATING + CONDUCTING | Opposite electrical properties | **No** |
| FLAMMABLE + FROZEN | Frozen things don't catch fire easily | **No** (debatable — frozen paper is still flammable, but the gameplay implication is contradictory since FROZEN objects become LIQUID when heated, while FLAMMABLE objects gain HEAT_SOURCE) |
| EXPLOSIVE + INSULATING | An explosive that blocks energy transfer is mechanically incoherent | **No** |
| LIVING + GAS | A gaseous creature breaks physics expectations | **No** (debatable — a "ghost" could justify this, but the rule engine has no living-gas interactions) |
| REFLECTIVE + STICKY | A mirror that adheres to everything is mechanically weird | **No** |

The most critical gap is **INSULATING + CONDUCTING**. These are defined as conceptual opposites in the system prompt ("metal-like" vs "rubber-like"), both are transferable tags, and the rule engine has them behave as functional inverses (INSULATING blocks what CONDUCTING propagates). Yet neither the contradiction list nor any validator catches `[CONDUCTING, INSULATING]`.

### What Happens When a Contradiction Slips Through

Contradictions that bypass validation create **rule ambiguity** at interaction time. If an object has both CONDUCTING and INSULATING:

1. Rule `electric_conducting_electrify` (priority 12) says: electricity propagates through it → add ELECTRIC tag, 30 damage.
2. Rule `electric_insulating_block` (priority 20) says: insulation blocks electricity → no propagation.

The higher-priority insulation rule wins (priority 20 > 12), so the object effectively acts insulating. The CONDUCTING tag becomes dead weight — it exists on the object but does nothing meaningful. This isn't a crash, but it's a waste of 2 budget points and a player-confusing property sheet.

---

## 2. Culturally Wrong Tags ("vegetarian eats hamburger")

### What Scribblenauts Taught Us

Scribblenauts' deepest problem (Section 5 of the Compass doc) was that player expectations are cultural knowledge, not computable rules. The cop should go for the donut. The vegetarian shouldn't eat the hamburger. Liz England spent six months on Wikipedia because "it didn't actually matter if an object was accurate. What mattered is that it did what people expected." The design goal was **representational over accurate** — "what do people visualize when they read this word?"

England's pipeline was: Wikipedia research → category assignment → prototype inheritance → hand-authored exceptions for the 80% of dev time spent on cultural edge cases. We replaced all of that with a single LLM call.

### Where It Lives Today

**The only cultural guidance is the system prompt:** `backend/app/creator/agent.py:15-115`

The prompt tells the LLM to "Think about gameplay affordances: what can the player DO with this object? Favor tags that enable interesting interactions." Two worked examples ("fire sword" and "ice wall") demonstrate expected reasoning. The prompt lists all 33 tags with plain-English descriptions.

**There is no post-LLM semantic validation.** The three validators in `blueprint.py` check:
1. Name is 1-3 words (line 37-48)
2. No contradiction pairs (line 50-60)
3. Budget ≤ 10 (line 62-73)

None of these validate whether the tags *make sense* for the described object.

### Concrete Failure Scenarios

**Scenario 1: "balloon" → [SOLID, RIGID, HEAVY]**
The LLM assigns physical-state tags appropriate for a rock, not a balloon. No validator catches this. The player sees a "Balloon" that doesn't float, can't be popped, and falls like a brick. The system prompt's examples don't cover lightweight/inflatable objects.

**Scenario 2: "glass vase" → [SOLID, RIGID, CONDUCTING, BREAKABLE]**
Glass is an insulator, not a conductor. The LLM may confuse "glass can shatter" (correct → BREAKABLE) with "glass conducts" (wrong). No validator catches semantic misalignment between material and electrical properties.

**Scenario 3: "campfire" → [SOLID, RIGID, HEAT_SOURCE, HOT, TOOL]**
A campfire tagged TOOL means the player can equip it. The LLM might reason "you use a campfire as a tool for cooking." But the game effect is that Maxwell wields a campfire in his hand slot. This is a `base_form` → `EQUIP_SLOT_MAP` interaction: since "campfire" isn't in the map, it defaults to "hand" (`tags.py:98`).

**Scenario 4: "feather" → [SOLID, RIGID, SHARP, LIGHT]**
A quill feather could plausibly be "sharp" to the LLM (quill pen tip), but the player expects a soft, floating feather. The LLM picks up on the wrong cultural connotation. RIGID is wrong (feathers are FLEXIBLE), and SHARP deals 25 damage to living things via rule `sharp_living_cut`.

### Why the LLM Is Both the Problem and the (Partial) Solution

The Compass doc's Section 5 notes that an LLM "trained on encyclopedic text might generate *accurate* object properties rather than *expected* ones." Our LLM might tag a "feather" as SHARP because quill tips are sharp — encyclopedically accurate, culturally wrong. But the same LLM also knows that when most people say "feather," they mean a soft, floating thing. The system prompt could steer this better with explicit guidance on cultural consensus over technical accuracy.

---

## 3. Non-Deterministic Outputs Across Sessions

### What Scribblenauts Taught Us

Scribblenauts' hand-authored database returned the same properties for "lion" every time. A lion had 100 HP, the "Destroy" behavior toward prey, and the "Run Away" behavior toward... nothing (lions don't flee). This determinism was free — it came from being a static database. The Compass doc (Section 7) identifies this as the #1 new problem for LLM-based reimplementation: "a hand-authored database returns the same result every time; an LLM might assign different properties to 'lion' on different runs."

### Where It Lives Today

**The LLM agent has no determinism controls:** `backend/app/creator/agent.py:123-129`

```python
_agent = Agent(
    settings.llm_model,                # google-gla:gemini-3.1-flash-lite-preview
    output_type=CreatorOutput,
    retries=3,
    system_prompt=SYSTEM_PROMPT,
    model_settings={"timeout": settings.llm_timeout_seconds},
)
```

No `temperature` parameter. No `seed` parameter. No result caching by description.

**The call site passes raw user input:** `agent.py:143`

```python
result = await agent.run(f"Create a game object for: {description}")
```

No input normalization. "Fire Sword", "fire sword", "FIRE SWORD", and "a fire sword" are four different prompts that may produce four different tag sets.

### Concrete Non-Determinism Vectors

**Vector 1: LLM sampling variance.** With default temperature (~1.0 for Gemini), identical input "fire sword" might yield:
- Session A: `[SOLID, RIGID, SHARP, HEAT_SOURCE, TOOL]` (cost 9)
- Session B: `[SOLID, RIGID, HEAT_SOURCE, TOOL, GLOWING]` (cost 10)
- Both valid. Different gameplay: Session A's sword cuts (SHARP → 25 damage via `sharp_living_cut`), Session B's doesn't but glows.

**Vector 2: Input normalization.** "a big rock" vs "big rock" vs "Big Rock" yield different LLM prompts. Even minor phrasing differences can shift tag selection.

**Vector 3: Retry path divergence.** If the LLM's first attempt violates budget (e.g., cost 12), `ModelRetry` sends feedback: "Budget 12/10. Tags: EXPLOSIVE(5), ELECTRIC(4), SHARP(2), SOLID(1). Remove expensive tags." The LLM's retry might drop EXPLOSIVE or ELECTRIC — different sessions may drop different tags.

**Vector 4: Fallback non-equivalence.** If the LLM fails all 3 retries (timeout, malformed output), the fallback produces `Mysterious {Name}` with `[SOLID, RIGID]` (cost 2). A user who creates "fire sword" and gets the fallback has a radically different object than one who gets the LLM result. The fallback is deterministic, but whether it triggers is not.

### Why This Matters for Gameplay

Non-determinism is invisible when each player has their own session. It becomes visible when:
- Players share strategies: "use a fire sword to ignite the TNT" fails if one player's fire sword has HEAT_SOURCE and another's doesn't.
- Speedrun/challenge reproducibility: same input, different objects, different solutions.
- Balance testing: we can't reason about whether "X is overpowered" if X has different tags every time.

---

## 4. Proposed Validation Layer

### 4A. Extend Contradiction Pairs (Immediate, Low Risk)

Add the mechanically meaningful missing contradictions to `TAG_CONTRADICTIONS` in `tags.py`:

```python
# New contradiction pairs
frozenset({Tag.CONDUCTING, Tag.INSULATING}),  # electrical opposites
frozenset({Tag.REFLECTIVE, Tag.STICKY}),      # surface incompatibility
```

These are unambiguous mechanical opposites. The CONDUCTING + INSULATING pair is the most urgent — it creates dead-weight tags and confusing rule resolution.

**Debatable pairs** (add to the system prompt as guidance, not as hard contradictions):
- FLAMMABLE + FROZEN: soft-warn in the prompt ("frozen objects typically aren't flammable — use only if the concept specifically requires both")
- LIVING + GAS: soft-warn ("gaseous creatures are unusual — only use for ghosts, spirits, or vapor beings")
- EXPLOSIVE + INSULATING: soft-warn ("explosives that block energy are mechanically odd")

### 4B. Semantic Coherence Validator (New Validator on CreatorOutput)

Add a fourth `@field_validator` on `CreatorOutput` that catches the most common cultural/semantic mismatches. This is not about blocking creativity — it's about catching the LLM's most likely mistakes.

**Tag-implication rules** — if a tag is present, certain other tags are expected or forbidden based on common sense:

```python
# In blueprint.py, new validator on CreatorOutput

TAG_SOFT_REQUIREMENTS: dict[Tag, dict[str, set[Tag]]] = {
    # If LIVING, should not be RIGID (living things are flexible)
    Tag.LIVING: {"discouraged": {Tag.RIGID}},
    # If TOOL, should be SOLID (can't wield a liquid)
    Tag.TOOL: {"requires_one_of": {Tag.SOLID, Tag.RIGID}},
    # If WEARABLE, should be SOLID or FLEXIBLE (can't wear gas)
    Tag.WEARABLE: {"requires_one_of": {Tag.SOLID, Tag.FLEXIBLE}},
    # If FLOATING + HEAVY coexist → warn (contradicts physics expectations)
    # Already handled by rule 42 (floating_heavy_cancel) at runtime,
    # but better to catch at creation time
}
```

Implementation: a new `check_semantic_coherence` validator that raises `ModelRetry` with specific guidance ("TOOL objects should be SOLID or at minimum RIGID — a liquid tool doesn't make sense. Add SOLID or remove TOOL."). This is cheap — it's a dict lookup, not an LLM call.

### 4C. Input Normalization (Immediate, Zero Risk)

Normalize the user's description before passing it to the LLM. In `creator/agent.py`, before the `agent.run()` call:

```python
def _normalize_description(description: str) -> str:
    """Normalize input for more consistent LLM outputs."""
    # Lowercase, strip whitespace, collapse multiple spaces
    normalized = " ".join(description.strip().lower().split())
    # Strip leading articles
    for prefix in ("a ", "an ", "the "):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
    return normalized
```

This collapses "A Fire Sword", "a fire sword", "  fire  sword  " into the same prompt, reducing one source of non-determinism.

### 4D. LLM Temperature Pinning (Immediate, Low Risk)

Set temperature to 0 (or as low as the model allows) in the agent configuration:

```python
model_settings={"temperature": 0.0, "timeout": settings.llm_timeout_seconds}
```

Temperature 0 selects the highest-probability token at every step, making outputs nearly deterministic for identical inputs. "Nearly" because some models still have minor variance at temperature 0, but this eliminates the largest source of non-determinism.

**Trade-off:** Lower temperature means less creative/surprising tag combinations. A "weird" input like "singing cactus" might get more interesting tags at temperature 0.7 than at 0. This is an acceptable trade-off: consistency matters more than novelty when the tag set determines gameplay mechanics.

### 4E. Description-Keyed Result Cache (Medium Effort, High Impact)

Cache LLM results by normalized description. If a player in Session B types "fire sword" and a player in Session A already created one, return the cached `CreatorOutput`.

```python
# In creator/agent.py or a new creator/cache.py

_creation_cache: dict[str, CreatorOutput] = {}

async def create_object(description: str) -> GameObjectBlueprint:
    normalized = _normalize_description(description)

    if normalized in _creation_cache:
        creator_output = _creation_cache[normalized]
    else:
        result = await agent.run(f"Create a game object for: {normalized}")
        creator_output = result.output
        _creation_cache[normalized] = creator_output

    # Blueprint still gets a unique UUID
    blueprint = GameObjectBlueprint(
        id=str(uuid.uuid4()),
        name=creator_output.name,
        description=description,  # preserve original
        tags=creator_output.tags,
        visual_descriptor=creator_output.visual_descriptor,
    )
    return blueprint
```

This turns our LLM into a **progressive dictionary** — the first player to create "fire sword" defines it for everyone, just like Scribblenauts' static database. Same tags, same visuals, same gameplay. Over time, the cache grows into exactly the kind of deterministic lookup table the Compass doc recommends.

**Cache scope:** In-memory dict for v1 (lost on restart). Upgrade path: persist to the `sessions` SQLite database in a `object_templates` table keyed by normalized description.

**Cache invalidation:** Start with no invalidation (the first generation wins). If we later add manual curation or prompt improvements, add a version field and invalidate when the prompt version changes.

### 4F. System Prompt Improvements (Immediate, Zero Risk)

Add cultural-consensus guidance to the system prompt, inspired by England's "representational over accurate" principle:

```
## Cultural Consensus Rule

Choose tags based on what MOST PEOPLE expect, not technical accuracy.
- "feather" → LIGHT, FLEXIBLE, FLOATING (soft, floaty) — NOT SHARP (even though quill tips are sharp)
- "glass" → SOLID, RIGID, BREAKABLE, REFLECTIVE — NOT CONDUCTING (glass is an insulator)
- "balloon" → LIGHT, FLOATING, FLEXIBLE, BREAKABLE — NOT SOLID (it's a thin membrane of air)
- "campfire" → HEAT_SOURCE, HOT, GLOWING — NOT TOOL (you don't wield a campfire)

When in doubt: what would a 10-year-old expect this object to do?
```

This directly addresses the "encyclopedic accuracy vs cultural expectation" gap that the Compass doc identifies as the core design challenge.

---

## 5. Implementation Priority

| Change | Risk | Effort | Failure Mode Addressed | Files Modified |
|--------|------|--------|----------------------|----------------|
| 4A. Extend contradictions | Low | 15 min | Contradictory tags | `tags.py` |
| 4C. Input normalization | Zero | 15 min | Non-determinism | `agent.py` |
| 4D. Temperature = 0 | Low | 5 min | Non-determinism | `agent.py` |
| 4F. Prompt improvements | Zero | 30 min | Culturally wrong tags | `agent.py` |
| 4B. Semantic validator | Low | 1 hr | Culturally wrong tags | `blueprint.py` |
| 4E. Result cache | Medium | 2 hr | Non-determinism | `agent.py` (new: `cache.py`) |

Items 4A, 4C, 4D, and 4F can ship together as a single commit. Items 4B and 4E are independent follow-ups.

---

## 6. What Remains Unsolvable

Three problems that no validation layer fully fixes:

1. **Novel objects have no ground truth.** If a player types "quantum spaghetti," there's no cultural consensus to validate against. The LLM's best guess is the only guess. This is fine — Scribblenauts also had to handle objects where "the most important thing is how they are different from each other" (England). The cache (4E) ensures that at least the guess is consistent.

2. **Balance regression from LLM-generated objects.** Every new object is a potential exploit vector. Scribblenauts had the jetpack-and-rope problem with 22,000 hand-tuned objects; we have it with infinite objects and zero QA history. The tag budget (max 10) and cost tiers are our primary defense, but a TOOL + HEAT_SOURCE + SHARP object at cost 8 is still a strong combo. The Compass doc's conclusion applies: "the balance problem is not a bug to fix but a design constraint to accept."

3. **Hallucinated properties that are mechanically valid but semantically absurd.** A "lightweight anvil" tagged [SOLID, RIGID, LIGHT] passes every validator — no contradictions, under budget, tags are self-consistent. But it breaks the player's mental model. The system prompt (4F) mitigates the most common cases; the semantic validator (4B) catches mechanical absurdities; but the long tail of "technically valid, culturally wrong" objects is infinite. This is the same problem England described: "the expectations of players coming into the game meant that every AI, and many other objects, needed tons of custom 'exceptions.'" Our LLM replaces most exceptions automatically, but not all.
