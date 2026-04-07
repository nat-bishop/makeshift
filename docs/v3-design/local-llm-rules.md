# Local LLM Design Rules

Rules for designing game systems around local LLM inference, derived from benchmarks on a Blackwell GPU running Qwen3.5-35B-A3B via SGLang.

## The Core Tradeoff

Every LLM call has two costs:

1. **Base cost (~55ms)** — fixed overhead per call. The model processes your input and produces its first output token. Input length barely matters: 10 input tokens and 1500 input tokens cost the same ~55ms. This is the irreducible cost of one forward pass through the model.

2. **Per-token cost (~7ms/token)** — each output token adds ~7ms. This is where the real cost is. A call that outputs 1 token takes ~60ms. A call that outputs 100 tokens takes ~750ms.

**Output tokens are everything. Input tokens are nearly free.**

## Output Tokens — What Counts

An output token is roughly one word or number. Some examples:

| Output | Tokens | Time |
|---|---|---|
| `5` | 1 | ~60ms |
| `CREATURE` | 1 | ~60ms |
| `0,2,5` | 5 | ~90ms |
| A sentence | ~15-20 | ~160-190ms |
| A paragraph | ~50-75 | ~400-580ms |
| Full JSON blob (current creator) | ~130 | ~950ms |

**Ask for numbers instead of words.** "Pick 0-15" → 1 token. "Pick a substance" → the model might say "I think metal would be best" → 10 tokens. Constrain the output format.

## Parallelism — It's Almost Free

Multiple calls running at the same time share the GPU efficiently:

| Concurrent calls | Wall time (2-token output each) |
|---|---|
| 1 | ~65ms |
| 4 | ~140ms |
| 8 | ~145ms |
| 16 | ~175ms |
| 32 | ~200ms (peak throughput) |
| 64+ | latency starts degrading |

**Up to ~8 parallel calls cost barely more than 1 call.** This means asking 6 simple questions in parallel is faster than asking 1 complex question that combines all 6 answers.

## The Design Pattern

Instead of one big prompt that outputs a full structured response:

```
❌ "Design a game object" → 130 tokens out → ~950ms
```

Break it into parallel tiny questions:

```
✅ In parallel (~150ms wall):
   "Pick substance 0-15"    → 1 token
   "Pick element 0-7"       → 1 token  
   "Pick categories 0-6"    → 1-3 tokens
   "Pick tags 0-9"          → 1-3 tokens
   "Pick size 0-4"          → 1 token
```

This tested at **0.61s vs 0.97s** — 37% faster — and the gap widens with more complex outputs.

## Simpler Questions = Smaller Models

The complexity of the question determines how smart the model needs to be:

| Task | Model size needed |
|---|---|
| "Is a zombie a creature? 0=no 1=yes" | Tiny (1-3B) |
| "Pick substance for fire sword: 0-15" | Small (3-7B) |
| "Write a visual description of a fire sword" | Medium (7-35B) |
| "Design a complete game object as JSON" | Large (35B+) |

A 3B model on a cheap GPU (RTX 4060, 8GB) can answer numbered-choice questions reliably. It would struggle to produce a correct 130-token JSON blob. **The graph approach makes small models viable by only asking easy questions.**

Estimated base cost by model size:

| Model | Base cost | Per token | Fits on |
|---|---|---|---|
| 35B MoE (current) | ~55ms | ~7ms | 24GB+ GPU |
| 7B quantized | ~40-50ms | ~7-10ms | 8GB GPU |
| 3B quantized | ~15-25ms | ~3-5ms | 8GB GPU (room to spare) |

## What Input Tokens Cost

Almost nothing. Benchmarked:

| Input size | Time for 1 output token |
|---|---|
| 10 tokens | 59ms |
| 500 tokens | 57ms |
| 1500 tokens | 60ms |

**You can put as much context as you want in the prompt for free.** Long numbered lists, examples, rules — none of it matters for latency. Only output tokens cost time.

## Batching Limits

The GPU saturates around 32-64 concurrent requests. Beyond that, latency spikes. Practical limits:

- **Single player creating:** 5-7 parallel calls, no problem
- **4 players creating simultaneously:** ~30 total calls, fine
- **8 players + interaction-time calls:** approaching the limit, may need to prioritize

## Interaction-Time Feasibility

Can you call the LLM during gameplay (not just at creation time)?

| Use case | Latency | Viable? |
|---|---|---|
| Per-frame (60fps) | needs <16ms | No — 55ms floor |
| Per-collision event | ~60-90ms | Yes, if not too frequent |
| Per player action (kick, use) | ~60-90ms | Yes |
| Object creation (graph) | ~150-300ms | Yes |
| Object creation (single call) | ~950ms | Yes but slow |

The 55ms base cost means LLM calls work for **event-driven** decisions (something collides, player does something) but not for **continuous** evaluation (every frame).

## Rules of Thumb

1. **Minimize output tokens** — this is the single most important optimization
2. **Use numbered choices** — "pick 0-7" not "pick a substance"
3. **Run independent questions in parallel** — 6 parallel calls ≈ cost of 1
4. **Input is free** — stuff the prompt with context, examples, numbered lists
5. **~55ms floor per call** — you always pay this, plan around it
6. **Simpler questions → smaller models → cheaper hardware**
7. **Free text is expensive** — descriptions and names cost 10-50x more tokens than classifications
8. **32 concurrent calls before degradation** — plenty for a multiplayer game
