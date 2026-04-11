# LLM Design Patterns

Patterns for decomposing problems into LLM calls. Derived from benchmarks on a Blackwell GPU running Qwen3.5-35B-A3B via SGLang, but the patterns apply to any local or cloud LLM.

When designing any LLM-powered feature, start here. Every system in the game should be expressible as a composition of these patterns.

---

## Core constraints

Every LLM call has two costs:

1. **Base cost (~55ms)** — fixed overhead per call. Input length barely matters: 10 tokens and 1500 tokens cost the same ~55ms.

2. **Per-token cost (~7ms/token)** — each output token adds ~7ms. A 1-token output takes ~60ms. A 100-token output takes ~750ms.

**Output tokens dominate cost. Input tokens are nearly free.**

### The base cost wall

Every call pays ~55ms regardless of how little work it does. This is the wall — no call can be faster than this. The formula:

```
call_time = 55ms (base) + output_tokens × 7ms
```

This means short outputs are dominated by the base cost, and you get surprisingly many tokens before the call gets meaningfully slower:

| Output tokens | Time | vs 1-token call |
|---|---|---|
| 1 | ~62ms | 1.0x |
| 5 | ~90ms | 1.4x |
| 9 | ~118ms | 1.9x |
| 10 | ~125ms | **2.0x** — this is where splitting into 2 calls breaks even |
| 20 | ~195ms | 3.1x |
| 130 | ~965ms | 15.5x |

**Up to ~9 output tokens, a single call is less than 2x the cost of a 1-token call.** A comma-separated list like `0,2,5,3` (5 tokens) barely costs more than a single number. This means you don't always need to split to individual 1-token calls — a short multi-value output can be efficient.

**Above ~10 tokens, splitting into parallel 1-token calls wins.** A 20-token output (~195ms) takes 3x longer than a single token, but 20 parallel 1-token calls take ~145ms total due to parallelism.

### Parallelism absorbs the base cost

The base cost wall means parallel calls are dramatically more efficient than sequential ones. The GPU processes multiple calls concurrently, sharing the base cost overhead:

| Concurrent calls | Wall time (2-token output each) | Per-call equivalent |
|---|---|---|
| 1 | ~65ms | 65ms |
| 8 | ~145ms | 18ms |
| 32 | ~200ms | 6ms |
| 64+ | degrades | — |

**8 parallel calls cost ~2.2x one call, not 8x.** This is why fan-out patterns are so powerful — you get 8 answers for barely more than the price of 1.

The math: with sequential calls, you pay the base cost N times (N × 55ms). With parallel calls, the base cost is paid roughly once and the GPU batches the work. This is why **splitting a 10-token output into 10 parallel 1-token calls is faster** — you trade 1×(55+70)ms = 125ms for ~145ms... wait, that's actually slower. The breakpoint is around 15-20 output tokens, where the serial cost exceeds the parallel overhead.

**Rule of thumb: if a single call would output >10 tokens, consider splitting into parallel calls. If <10 tokens, a single call is fine.** Exception: when the LLM needs to see all items together to make relative judgments (e.g., screening which pairs are interesting), a single multi-token call is better than N independent calls even if output exceeds 10 tokens.

### Input is cheap (for latency)

Benchmarked: 10 input tokens and 1500 input tokens both produce the first output token in ~58ms. Adding context to a prompt doesn't slow it down. However, longer prompts can affect answer quality — prompt design still matters and needs testing.

---

## The decomposition principle

**Break complex questions into many simple ones.** This is the central design idea that everything else follows from.

Instead of one prompt that outputs a structured response:
```
"Design a game object" → 130 tokens out → ~950ms
```

Decompose into parallel 1-token questions:
```
In parallel (~60ms wall):
  "How heavy in kg? (feather=0.01, sword=1.5, car=1500)" → 1 token
  "How bouncy 0-100? (clay=0, rubber=90)"                → 1 token
  "Gravity pull 0-100? (balloon=5, normal=50, anvil=75)"  → 1 token
```

This is faster (60ms vs 950ms) AND more reliable. But the deeper benefit is:

**Simpler questions enable smaller models.** A 3B model can answer "how heavy is a sword?" but can't produce a correct 130-token JSON object. Decomposition isn't just an optimization — it's what makes the game shippable on consumer hardware.

| Task complexity | Model size needed |
|---|---|
| "Is a zombie a creature? 0=no 1=yes" | 1-3B |
| "How heavy is a fire sword in kg?" | 3-7B |
| "Describe a fire sword for a sprite artist" | 7-35B |
| "Design a complete game object as JSON" | 35B+ |

Estimated base cost by model size:

| Model | Base cost | Per token | Fits on |
|---|---|---|---|
| 35B MoE (current) | ~55ms | ~7ms | 24GB+ GPU |
| 7B quantized | ~40-50ms | ~7-10ms | 8GB GPU |
| 3B quantized | ~15-25ms | ~3-5ms | 8GB GPU (room to spare) |

### How to decompose a new feature

1. **What decisions need to be made?** List them.
2. **Which are independent?** → parallel fan-out
3. **Which depend on prior answers?** → sequential seeding
4. **Can a cheap first question eliminate follow-up work?** → fan-out, filter, fan-in
5. **Can each decision be a numbered choice?** If yes: 1 token. If it needs freeform text: 10-50x more expensive — make sure it's worth it.

---

## Patterns

### 1. Parallel fan-out

Independent questions asked simultaneously. The simplest and most common pattern.

```
All parallel (~60ms wall):
  "Mass in kg?"     → 2
  "Height in m?"    → 1.2
  "Friction 0-100?" → 30
  "Bounce 0-100?"   → 10
  "Gravity 0-100?"  → 50
```

**When to use:** Questions have no dependencies. Each answer doesn't affect any other question's prompt or meaning.

**Used in:** Object creation — all physics properties, destructibility, field, autonomous flag.

### 2. Sequential seeding

Later questions use answers from earlier questions as input context. Each stage is trivially simple because prior answers are given.

```
Stage 1: "Firefighter sees burning tree. approach/flee/ignore"
  → approach

Stage 2: "Firefighter is APPROACHING burning tree because it wants to help.
          On contact: nothing/attack/heal/consume/push"
  → attack

Stage 3 (parallel): "Firefighter will ATTACK burning tree.
                     Apply/remove a state? none/add/remove"  → remove
                    "Firefighter will ATTACK burning tree. Which state?
                     burning/frozen/wet/electrified"          → burning
```

Stage 2 includes "is APPROACHING because it wants to help" — seeded from stage 1's answer. Stage 3 includes "will ATTACK" — seeded from stage 2. The model doesn't re-derive intent; it's given. This makes each question trivially simple even for very small models.

**When to use:** Decisions naturally cascade — the answer to question 1 determines the framing of question 2. The key benefit isn't speed (sequential adds base cost per stage) — it's answer quality. Seeded context makes each question easier, enabling smaller models and more consistent answers.

**Used in:** Object behavior staged evaluation (movement → action → parameters).

### 3. Fan-out, filter, fan-in

Fan out to many parallel calls. Filter results. Fan in to a smaller set of follow-up calls.

```
Stage 1 — Fan out (42 parallel calls, 2 tokens each):
  "Object A sees object 1 → approach/flee/ignore?" + "How strongly?"  → approach, driven
  "Object A sees object 2 → approach/flee/ignore?" + "How strongly?"  → ignore, ignore
  "Object A sees object 3 → approach/flee/ignore?" + "How strongly?"  → ignore, mild
  ...

Filter: keep pairs where movement=approach OR priority>0 (~12 out of 42 survive)

Stage 2 — Fan in (12 parallel calls, 1+ tokens each):
  "Object A contacts object 1. nothing/attack/heal/consume/push?"  → attack
  ...
```

The filter eliminates ~70% of follow-up work. Stage 2 only runs for pairs that matter.

**When to use:** A cheap first question (binary or categorical) can determine whether expensive follow-up is needed. Always ask the cheap question first.

**Used in:** Object behavior — movement+priority (all pairs) filters to composite action pipeline (approach-or-priority pairs only) filters to parameters (actions that need them).

### 4. Combined: parallel fan-out + conditional sequential

The full object creation pipeline combines multiple patterns:

```
Batch 1 — Parallel fan-out (~60ms):
  Physics: mass, height, friction, bounce, gravity     → 5 calls
  Destructibility: armor, HP, indestructible            → 3 calls  
  Classification: field, autonomous, affordance         → 3 calls

Batch 1b — Parallel with batch 1 (~200ms):
  Visual description                                    → 1 call, ~25 tokens

Conditional — depends on batch 1 results:
  If autonomous → behavior evaluation for this object vs all existing objects

Spawn integration — depends on creation results:
  Behavior screening (pattern 5: batch screening)
  Behavior stage 1 (pattern 1: parallel fan-out, all screened pairs)
  Behavior stage 2 (pattern 2+3: sequential seeding + filter, interesting pairs only)
```

Independent work runs in parallel. Dependent work waits for prior results. Conditional paths skip unnecessary work.

### 5. Batch screening

One call that triages many items at once, returning a short list. Unlike per-item binary screening (N calls, 1 token each), the LLM sees all candidates together and can make relative judgments.

```
"New object: fire sword (2kg, hot, sharp, metal).
 Scene objects:
 1. wooden shield (3kg, flammable, wood)
 2. rock (5kg, stone)
 3. glass bottle (0.3kg, fragile, glass)
 4. rope (0.5kg, fiber)
 5. campfire (hot, fire)
 Which would interact interestingly with fire sword? List numbers."
 → "1,3"
```

Output is ~5-15 tokens depending on how many items pass the screen. This intentionally exceeds the "split above 10 tokens" guideline because the LLM needs full context to make good judgments — it can see that fire sword + campfire is redundant (both hot) while fire sword + wooden shield is meaningful.

**When to use:** You need to select a subset from a larger set, and the selection benefits from seeing all candidates together. The output is a short list of IDs, not detailed answers — keep expensive follow-up for the items that pass.

**Used in:** Behavior screening — identifies which object pairs are worth fully evaluating. Most pairs (~75%) have no interesting interaction and get filtered.

---

## Patterns we considered but chose not to use

### Redundant fan-out (ask N times, aggregate)

Ask the same question 3 times with different calibration examples, take the median. Improves consistency at 3x cost.

**Why not for this game:** Slight variance in physics values is acceptable for a creative sandbox. Two fire swords with slightly different mass feels natural. The creation cache (same name → same values) handles exact-match consistency without redundant calls.

### Chain of refinement (rough then precise)

Ask a rough question first, refine only if interesting: "Is this object dangerous? 0=no 1=yes" → if yes → "How dangerous 0-100?"

**Why not for this game:** The refinement saves 1 call for non-interesting objects but adds a sequential dependency (~55ms base cost) for ALL objects. Net slower unless >50% of objects skip the refinement. Note: this is about per-item binary screening — batch screening (one call that triages many items, see pattern 5) is a different and often better approach when most items can be skipped.

---

## Interaction-time feasibility

Can LLM calls happen during gameplay, not just at creation/spawn?

| Use case | Latency | Viable? |
|---|---|---|
| Per-frame (60fps) | needs <16ms | No — 55ms floor |
| Per-collision event | ~60-90ms | Yes, if infrequent |
| Per player action | ~60-90ms | Yes |
| Object creation | ~150-300ms | Yes |

The 55ms floor means LLM calls work for **event-driven** decisions but not **continuous** evaluation.

---

## Rules of thumb

1. **Minimize output tokens** — the single most important constraint
2. **Use numbered choices** — "pick 0-7" not "pick a substance". 1 token, not 10
3. **Run independent questions in parallel** — 8 parallel ≈ cost of 1
4. **Seed sequential stages** — prior answers as input context make each question trivial
5. **Filter early** — a cheap yes/no that eliminates follow-up work is always worth it
6. **Input is cheap for latency** — adding context doesn't slow calls down, but prompt quality still matters
7. **Simpler questions → smaller models → consumer hardware** — decomposition enables deployment
8. **~55ms floor per call** — plan around it, don't fight it
9. **32 concurrent calls before degradation** — plenty for multiplayer
