"""Benchmark: single LLM call vs two-tier sequential calls.

Measures latency and token counts for the creator agent pattern,
comparing one big prompt vs a classify-then-specialize split.
Accounts for model warmup, KV cache effects, and variance.

Usage:
    cd backend && uv run python bench_two_tier.py
    cd backend && uv run python bench_two_tier.py --runs 5      # fewer runs
    cd backend && uv run python bench_two_tier.py --prompts 3    # fewer prompts per run
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time

import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_URL = "http://127.0.0.1:5200/v1"
MODEL = "Qwen/Qwen3.5-35B-A3B-FP8"

# Match the project's model_profiles.toml settings
SAMPLING = {
    "temperature": 0.7,
    "top_p": 0.95,
    "top_k": 20,
    "min_p": 0.0,
    "presence_penalty": 1.5,
    "repetition_penalty": 1.0,
}

# Disable thinking (matches project config)
EXTRA_BODY = {
    "chat_template_kwargs": {"enable_thinking": False},
}

# Diverse test prompts — mix of weapons, creatures, simple objects
TEST_PROMPTS = [
    "fire sword",
    "acid spider",
    "rubber duck",
    "electric dragon",
    "wooden shield",
    "campfire",
    "ice golem",
    "gold coin",
    "toxic mushroom",
    "bouncy ball",
    "brave knight",
    "rope",
]

# ---------------------------------------------------------------------------
# The actual system prompt from creator/agent.py (abbreviated for the bench)
# We use the FULL prompt to get realistic prefill times.
# ---------------------------------------------------------------------------
FULL_SYSTEM_PROMPT = """\
You are a game object designer for a 2D sandbox game. Given a player's description, \
create a game object by choosing a substance, optional element, categories, tags, behaviors, and visual appearance.

## Substance (pick exactly 1)

The substance defines what the object is made of — its physics, durability, and base properties.

| Substance | What it's for | Auto-derived traits |
|-----------|--------------|-------------------|
| metal | Swords, armor, coins, anvils, chains | METALLIC, RIGID |
| wood | Furniture, sticks, barrels, trees | FLAMMABLE |
| stone | Rocks, boulders, walls, statues | RIGID, HEAVY |
| glass | Bottles, windows, crystal, mirrors | BREAKABLE, REFLECTIVE |
| rubber | Balls, tires, erasers, bouncy things | BOUNCY, INSULATING |
| bone | Skeletons, fossils, horns, tusks | RIGID |
| ceramic | Pottery, tiles, bricks, porcelain | BREAKABLE, INSULATING |
| cloth | Flags, clothing, sails, carpets | FLAMMABLE, LIGHT |
| water | Water bodies, rain, puddles | LIQUID, WET |
| oil | Oil slicks, fuel, grease | LIQUID, FLAMMABLE |
| slime | Slime blobs, ooze, goop | LIQUID, STICKY, TOXIC |
| ice | Ice blocks, icicles, frost | FROZEN, RIGID, COLD, BRITTLE |
| lava | Lava flows, magma pools | MOLTEN, LIQUID, HEAT_SOURCE |
| fire | Flames, campfires, infernos | GAS, HEAT_SOURCE, HOT |
| smoke | Smoke clouds, steam, mist | GAS, LIGHT |
| flesh | Creatures, monsters, animals, people | *(none)* |

## Element (pick 0 or 1)

An optional energy infusion that adds elemental properties.

| Element | Adds traits | Example |
|---------|------------|---------|
| burning | HEAT_SOURCE, HOT | fire sword, lava golem |
| electric | ELECTRIC | lightning rod, electric eel |
| magnetic | MAGNETIC | lodestone, magnetic crane |
| freezing | COLD | ice breath, frost wand |
| acidic | ACIDIC | acid spider, corrosive slime |
| toxic | TOXIC | poison dart, toxic mushroom |
| windy | WIND_SOURCE | fan, tornado, jet engine |

## Categories (pick 0-3 — what gameplay interactions this object supports)

CREATURE — a living being. Animals, monsters, people, insects. Auto-adds LIVING tag.
FOOD — something edible. Fruit, meat, potions, snacks.
WEAPON — made to deal damage. Swords, bombs, bows, traps.
PLANT — a plant or fungus. Trees, flowers, vines, mushrooms.
VALUABLE — precious or collectible. Treasure, coins, gems, rare items.
VEHICLE — something rideable or that carries things. Carts, boats, horses.
TOOL — a utility object. Buckets, ropes, levers, keys, shields.

Most objects have 0-1 categories. A wolf is [CREATURE]. A donut is [FOOD]. \
A fire sword is [WEAPON]. A campfire has none.

## Tags (pick 0-3 — physical modifiers the substance doesn't cover)

SHARP — cutting edge or point. Swords, thorns, claws.
HEAVY — dense and massive. Anvils, boulders. Immovable by wind.
LIGHT — very low mass. Feathers, paper, balloons. Blown by wind.
BOUNCY — elastic, high restitution. Springs, trampolines.
BREAKABLE — fragile, easily destroyed. Glass, pottery, eggshells.
STICKY — adhesive surface. Honey, tar, spider webs.
REFLECTIVE — mirror-like surface. Shields, polished metal.
EXPLOSIVE — volatile, detonates when damaged. Dynamite, grenades.
FLYING — defies gravity. Birds, drones, ghosts, balloons.
WET — damp or soaked. Amplifies electricity, freezes from cold.

## Behaviors (0-4, for CREATURE objects)

Each behavior has a verb, a target_tag (what to target), and a target_description (freeform reasoning). \
List behaviors in order of importance — first behavior takes precedence when multiple are active.

- **target_tag**: one of CREATURE, FOOD, WEAPON, PLANT, VALUABLE, VEHICLE, TOOL, HOSTILE, HEAT_SOURCE — or empty for "anything nearby"
- **target_description**: freeform text describing intent (for display, not used for matching)
- destroy/eat/flee MUST have a target_tag. investigate/follow/protect may leave it empty.

| Verb | What it does |
|------|-------------|
| destroy | Move toward target + melee attack |
| eat | Move toward target + consume (damage, heal self) |
| investigate | Move toward target slowly, stop at medium range |
| follow | Move toward target, maintain close distance |
| protect | Follow target + attack threats near it |
| flee | Move away from target at high speed |

Examples:
- A wolf: destroy target_tag=CREATURE "small prey animals", flee target_tag=HEAT_SOURCE "fire"
- A dragon: destroy target_tag=CREATURE "anything alive", follow target_tag=VALUABLE "treasure and gold"
- A curious cat: investigate "interesting objects nearby" (empty target_tag)

Non-CREATURE objects have no behaviors. A sword doesn't need behaviors — its tags handle everything.

## Visual Descriptor

- visual_description: 1-2 sentences — shape, material, colors, distinctive features.
- size_category: tiny | small | medium | large | huge

## Name

1-3 words. Concise and evocative.

## Examples

"fire sword" → substance: metal, element: burning, categories: [WEAPON], tags: [SHARP], behaviors: [], \
visual: "a gleaming steel blade wreathed in dancing orange flames"

"rock" → substance: stone, element: null, categories: [], tags: [], behaviors: [], \
visual: "a rough gray boulder with moss patches"

"acid spider" → substance: flesh, element: acidic, categories: [CREATURE], tags: [], \
behaviors: [destroy target_tag=CREATURE "small insects and prey", flee target_tag=HEAT_SOURCE "fire"], \
visual: "a glossy black spider dripping green acid from its fangs"

"campfire" → substance: fire, element: null, categories: [], tags: [], behaviors: [], \
visual: "a crackling campfire with orange flames dancing over charred logs"
"""

# ---------------------------------------------------------------------------
# Two-tier prompts
# ---------------------------------------------------------------------------
TIER1_SYSTEM = """\
You are a game object classifier. Given a player's description, determine what type of object this is.

Respond with a JSON object:
{
  "name": "1-3 word name",
  "substance": one of: metal, wood, stone, glass, rubber, bone, ceramic, cloth, water, oil, slime, ice, lava, fire, smoke, flesh,
  "element": one of: burning, electric, magnetic, freezing, acidic, toxic, windy, or null,
  "categories": list of 0-3 from: CREATURE, FOOD, WEAPON, PLANT, VALUABLE, VEHICLE, TOOL,
  "is_creature": true if this is a living being with behaviors, false otherwise
}

Examples:
"fire sword" → {"name": "Fire Sword", "substance": "metal", "element": "burning", "categories": ["WEAPON"], "is_creature": false}
"acid spider" → {"name": "Acid Spider", "substance": "flesh", "element": "acidic", "categories": ["CREATURE"], "is_creature": true}
"campfire" → {"name": "Campfire", "substance": "fire", "element": null, "categories": [], "is_creature": false}
"brave knight" → {"name": "Brave Knight", "substance": "flesh", "element": null, "categories": ["CREATURE"], "is_creature": true}
"""

TIER2_CREATURE_SYSTEM = """\
You are a game creature designer. Given a creature classification, add behaviors, tags, and visual appearance.

## Tags (pick 0-3)
SHARP, HEAVY, LIGHT, BOUNCY, BREAKABLE, STICKY, REFLECTIVE, EXPLOSIVE, FLYING, WET

## Behaviors (1-4, in priority order)
Verbs: destroy, eat, investigate, follow, protect, flee
- target_tag: one of CREATURE, FOOD, WEAPON, PLANT, VALUABLE, VEHICLE, TOOL, HOSTILE, HEAT_SOURCE, or empty
- target_description: freeform text
- destroy/eat/flee MUST have a target_tag

## Visual Descriptor
- visual_description: 1-2 sentences
- size_category: tiny | small | medium | large | huge

Respond with JSON:
{
  "tags": [...],
  "behaviors": [{"verb": "...", "target_tag": "...", "target_description": "..."}],
  "visual_descriptor": {"visual_description": "...", "size_category": "..."}
}
"""

TIER2_OBJECT_SYSTEM = """\
You are a game object designer. Given an object classification, add tags and visual appearance.

## Tags (pick 0-3)
SHARP, HEAVY, LIGHT, BOUNCY, BREAKABLE, STICKY, REFLECTIVE, EXPLOSIVE, FLYING, WET

## Visual Descriptor
- visual_description: 1-2 sentences
- size_category: tiny | small | medium | large | huge

Respond with JSON:
{
  "tags": [...],
  "visual_descriptor": {"visual_description": "...", "size_category": "..."}
}
"""


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def chat_completion(
    client: httpx.Client,
    system: str,
    user: str,
    *,
    json_mode: bool = True,
) -> dict:
    """Single chat completion call. Returns dict with timing + token info."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    body: dict = {
        "model": MODEL,
        "messages": messages,
        **SAMPLING,
        **EXTRA_BODY,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    t0 = time.perf_counter()
    resp = client.post(f"{BASE_URL}/chat/completions", json=body, timeout=60)
    elapsed = time.perf_counter() - t0

    resp.raise_for_status()
    data = resp.json()

    usage = data.get("usage", {})
    content = data["choices"][0]["message"]["content"]

    return {
        "elapsed": elapsed,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "content": content,
    }


# ---------------------------------------------------------------------------
# Benchmark strategies
# ---------------------------------------------------------------------------

def run_single_call(client: httpx.Client, prompt: str) -> dict:
    """Strategy A: one big call with the full creator prompt."""
    user_msg = f"Create a game object for: {prompt}\n\nRespond with JSON."
    result = chat_completion(client, FULL_SYSTEM_PROMPT, user_msg)
    return {
        "strategy": "single",
        "prompt": prompt,
        "calls": 1,
        "total_elapsed": result["elapsed"],
        "call_times": [result["elapsed"]],
        "prompt_tokens": result["prompt_tokens"],
        "completion_tokens": result["completion_tokens"],
        "total_tokens": result["total_tokens"],
    }


def run_two_tier(client: httpx.Client, prompt: str) -> dict:
    """Strategy B: classify first, then specialize."""
    # Tier 1: classify
    t1 = chat_completion(client, TIER1_SYSTEM, f"Classify: {prompt}")

    # Parse tier 1 to decide tier 2 prompt
    try:
        classification = json.loads(t1["content"])
        is_creature = classification.get("is_creature", False)
    except (json.JSONDecodeError, KeyError):
        is_creature = False

    # Tier 2: specialize
    tier2_system = TIER2_CREATURE_SYSTEM if is_creature else TIER2_OBJECT_SYSTEM
    tier2_user = (
        f"Original prompt: {prompt}\n"
        f"Classification: {t1['content']}\n\n"
        f"Now add the remaining details. Respond with JSON."
    )
    t2 = chat_completion(client, tier2_system, tier2_user)

    total_elapsed = t1["elapsed"] + t2["elapsed"]
    return {
        "strategy": "two_tier",
        "prompt": prompt,
        "calls": 2,
        "is_creature": is_creature,
        "total_elapsed": total_elapsed,
        "call_times": [t1["elapsed"], t2["elapsed"]],
        "prompt_tokens": t1["prompt_tokens"] + t2["prompt_tokens"],
        "completion_tokens": t1["completion_tokens"] + t2["completion_tokens"],
        "total_tokens": t1["total_tokens"] + t2["total_tokens"],
    }


# ---------------------------------------------------------------------------
# Warmup + benchmark runner
# ---------------------------------------------------------------------------

def warmup(client: httpx.Client, n: int = 3) -> list[float]:
    """Send warmup requests to load model weights + fill KV cache.

    Returns list of warmup times so we can see the cold-start penalty.
    """
    print(f"\n{'='*60}")
    print(f"WARMUP ({n} requests to load model / fill caches)")
    print(f"{'='*60}")
    times = []
    for i in range(n):
        t0 = time.perf_counter()
        result = chat_completion(
            client, "You are a helpful assistant.", 'Say "ready" in JSON: {"status": "ready"}'
        )
        elapsed = time.perf_counter() - t0
        times.append(result["elapsed"])
        print(f"  warmup {i+1}: {result['elapsed']:.3f}s "
              f"({result['prompt_tokens']} -> {result['completion_tokens']} tokens)")
    return times


def run_benchmark(
    *,
    num_runs: int = 3,
    num_prompts: int | None = None,
) -> None:
    prompts = TEST_PROMPTS[:num_prompts] if num_prompts else TEST_PROMPTS

    # Check server is reachable
    print(f"Connecting to {BASE_URL} ...")
    client = httpx.Client(timeout=120)
    try:
        resp = client.get(f"{BASE_URL}/models")
        resp.raise_for_status()
        models = resp.json()
        model_ids = [m["id"] for m in models.get("data", [])]
        print(f"Server OK. Models: {model_ids}")
    except Exception as e:
        print(f"ERROR: Cannot reach SGLang at {BASE_URL}: {e}")
        print("Make sure the local LLM server is running (make gpu)")
        sys.exit(1)

    # Warmup
    warmup_times = warmup(client)

    # Results storage
    single_results: list[dict] = []
    two_tier_results: list[dict] = []

    for run_idx in range(num_runs):
        print(f"\n{'='*60}")
        print(f"RUN {run_idx + 1}/{num_runs}")
        print(f"{'='*60}")

        for prompt in prompts:
            # Alternate order to avoid systematic bias
            if run_idx % 2 == 0:
                s = run_single_call(client, prompt)
                single_results.append(s)
                t = run_two_tier(client, prompt)
                two_tier_results.append(t)
            else:
                t = run_two_tier(client, prompt)
                two_tier_results.append(t)
                s = run_single_call(client, prompt)
                single_results.append(s)

            delta = t["total_elapsed"] - s["total_elapsed"]
            sign = "+" if delta > 0 else ""
            print(
                f"  {prompt:20s} | "
                f"single: {s['total_elapsed']:.2f}s ({s['completion_tokens']:3d} out) | "
                f"two-tier: {t['total_elapsed']:.2f}s ({t['completion_tokens']:3d} out) | "
                f"delta: {sign}{delta:.2f}s"
            )

    client.close()

    # ---------------------------------------------------------------------------
    # Analysis
    # ---------------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")

    print(f"\nWarmup times: {', '.join(f'{t:.3f}s' for t in warmup_times)}")
    print(f"  Cold start penalty: {warmup_times[0] - warmup_times[-1]:.3f}s\n")

    def summarize(results: list[dict], label: str) -> dict:
        times = [r["total_elapsed"] for r in results]
        prompt_toks = [r["prompt_tokens"] for r in results]
        comp_toks = [r["completion_tokens"] for r in results]
        total_toks = [r["total_tokens"] for r in results]

        summary = {
            "label": label,
            "n": len(results),
            "time_mean": statistics.mean(times),
            "time_median": statistics.median(times),
            "time_stdev": statistics.stdev(times) if len(times) > 1 else 0,
            "time_min": min(times),
            "time_max": max(times),
            "prompt_tokens_mean": statistics.mean(prompt_toks),
            "completion_tokens_mean": statistics.mean(comp_toks),
            "total_tokens_mean": statistics.mean(total_toks),
        }

        print(f"\n--- {label} ({len(results)} samples) ---")
        print(f"  Latency:  mean={summary['time_mean']:.3f}s  "
              f"median={summary['time_median']:.3f}s  "
              f"stdev={summary['time_stdev']:.3f}s  "
              f"min={summary['time_min']:.3f}s  max={summary['time_max']:.3f}s")
        print(f"  Tokens:   prompt={summary['prompt_tokens_mean']:.0f}  "
              f"completion={summary['completion_tokens_mean']:.0f}  "
              f"total={summary['total_tokens_mean']:.0f}")
        return summary

    s_summary = summarize(single_results, "Single Call (full prompt)")
    t_summary = summarize(two_tier_results, "Two-Tier (classify -> specialize)")

    # Per-prompt comparison
    print(f"\n--- Per-prompt averages ---")
    print(f"  {'Prompt':20s} | {'Single':>8s} | {'Two-tier':>8s} | {'Delta':>8s} | {'Out tok S':>9s} | {'Out tok T':>9s}")
    print(f"  {'-'*20}-+-{'-'*8}-+-{'-'*8}-+-{'-'*8}-+-{'-'*9}-+-{'-'*9}")
    for prompt in prompts:
        s_times = [r["total_elapsed"] for r in single_results if r["prompt"] == prompt]
        t_times = [r["total_elapsed"] for r in two_tier_results if r["prompt"] == prompt]
        s_toks = [r["completion_tokens"] for r in single_results if r["prompt"] == prompt]
        t_toks = [r["completion_tokens"] for r in two_tier_results if r["prompt"] == prompt]
        s_avg = statistics.mean(s_times)
        t_avg = statistics.mean(t_times)
        delta = t_avg - s_avg
        sign = "+" if delta > 0 else ""
        print(
            f"  {prompt:20s} | {s_avg:7.2f}s | {t_avg:7.2f}s | {sign}{delta:7.2f}s | "
            f"{statistics.mean(s_toks):8.0f} | {statistics.mean(t_toks):8.0f}"
        )

    # Bottom line
    overhead = t_summary["time_mean"] - s_summary["time_mean"]
    pct = (overhead / s_summary["time_mean"]) * 100 if s_summary["time_mean"] > 0 else 0
    print(f"\n{'='*60}")
    print(f"BOTTOM LINE")
    print(f"{'='*60}")
    print(f"  Single call avg:   {s_summary['time_mean']:.3f}s")
    print(f"  Two-tier avg:      {t_summary['time_mean']:.3f}s")
    print(f"  Overhead:          {overhead:+.3f}s ({pct:+.1f}%)")
    print(f"  Token efficiency:  single={s_summary['total_tokens_mean']:.0f} "
          f"vs two-tier={t_summary['total_tokens_mean']:.0f} "
          f"({t_summary['total_tokens_mean'] - s_summary['total_tokens_mean']:+.0f})")

    # Break down two-tier call times
    t1_times = [r["call_times"][0] for r in two_tier_results]
    t2_times = [r["call_times"][1] for r in two_tier_results]
    print(f"\n  Two-tier breakdown:")
    print(f"    Tier 1 (classify):    mean={statistics.mean(t1_times):.3f}s  "
          f"median={statistics.median(t1_times):.3f}s")
    print(f"    Tier 2 (specialize):  mean={statistics.mean(t2_times):.3f}s  "
          f"median={statistics.median(t2_times):.3f}s")

    # Creature vs non-creature in two-tier
    creature_results = [r for r in two_tier_results if r.get("is_creature")]
    object_results = [r for r in two_tier_results if not r.get("is_creature")]
    if creature_results:
        print(f"\n  Two-tier creatures ({len(creature_results)} samples):  "
              f"mean={statistics.mean([r['total_elapsed'] for r in creature_results]):.3f}s  "
              f"comp_tokens={statistics.mean([r['completion_tokens'] for r in creature_results]):.0f}")
    if object_results:
        print(f"  Two-tier objects  ({len(object_results)} samples):  "
              f"mean={statistics.mean([r['total_elapsed'] for r in object_results]):.3f}s  "
              f"comp_tokens={statistics.mean([r['completion_tokens'] for r in object_results]):.0f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark single vs two-tier LLM calls")
    parser.add_argument("--runs", type=int, default=3, help="Number of full runs (default: 3)")
    parser.add_argument("--prompts", type=int, default=None, help="Number of prompts to test (default: all 12)")
    args = parser.parse_args()

    run_benchmark(num_runs=args.runs, num_prompts=args.prompts)
