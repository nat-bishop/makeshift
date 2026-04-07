"""Benchmark: single LLM call vs parallel graph of tiny calls.

The graph approach breaks the creator output into independent micro-decisions,
each outputting minimal tokens (a number or short word). Independent branches
run in parallel; dependent branches chain sequentially.

Graph structure:
  Layer 1 (parallel):  substance, element, categories, name
  Layer 2 (parallel):  tags (knows substance/element), behaviors (if creature), visual

Usage:
    cd backend && uv run python bench_graph.py
    cd backend && uv run python bench_graph.py --runs 3 --prompts 4
"""

from __future__ import annotations

import argparse
import asyncio
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

SAMPLING = {
    "temperature": 0.7,
    "top_p": 0.95,
    "top_k": 20,
    "min_p": 0.0,
    "presence_penalty": 1.5,
    "repetition_penalty": 1.0,
}

EXTRA_BODY = {
    "chat_template_kwargs": {"enable_thinking": False},
}

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
# Full single-call prompt (same as bench_two_tier.py)
# ---------------------------------------------------------------------------
FULL_SYSTEM_PROMPT = """\
You are a game object designer for a 2D sandbox game. Given a player's description, \
create a game object by choosing a substance, optional element, categories, tags, behaviors, and visual appearance.

## Substance (pick exactly 1)

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

| Element | Adds traits | Example |
|---------|------------|---------|
| burning | HEAT_SOURCE, HOT | fire sword, lava golem |
| electric | ELECTRIC | lightning rod, electric eel |
| magnetic | MAGNETIC | lodestone, magnetic crane |
| freezing | COLD | ice breath, frost wand |
| acidic | ACIDIC | acid spider, corrosive slime |
| toxic | TOXIC | poison dart, toxic mushroom |
| windy | WIND_SOURCE | fan, tornado, jet engine |

## Categories (pick 0-3)

CREATURE, FOOD, WEAPON, PLANT, VALUABLE, VEHICLE, TOOL

## Tags (pick 0-3)

SHARP, HEAVY, LIGHT, BOUNCY, BREAKABLE, STICKY, REFLECTIVE, EXPLOSIVE, FLYING, WET

## Behaviors (0-4, for CREATURE objects)

Verbs: destroy, eat, investigate, follow, protect, flee
- target_tag: CREATURE, FOOD, WEAPON, PLANT, VALUABLE, VEHICLE, TOOL, HOSTILE, HEAT_SOURCE, or empty
- target_description: freeform text
- destroy/eat/flee MUST have a target_tag

## Visual Descriptor

- visual_description: 1-2 sentences
- size_category: tiny | small | medium | large | huge

## Name: 1-3 words

## Examples

"fire sword" -> substance: metal, element: burning, categories: [WEAPON], tags: [SHARP], behaviors: [], \
visual: "a gleaming steel blade wreathed in dancing orange flames"

"acid spider" -> substance: flesh, element: acidic, categories: [CREATURE], tags: [], \
behaviors: [destroy target_tag=CREATURE "small insects and prey", flee target_tag=HEAT_SOURCE "fire"], \
visual: "a glossy black spider dripping green acid from its fangs"

"campfire" -> substance: fire, element: null, categories: [], tags: [], behaviors: [], \
visual: "a crackling campfire with orange flames dancing over charred logs"

Respond with JSON matching the full schema.\
"""

# ---------------------------------------------------------------------------
# Graph micro-prompts — each elicits minimal output tokens
# ---------------------------------------------------------------------------

SUBSTANCE_PROMPT = """\
Pick the best substance for a game object. Reply with ONLY the number.

0=metal  1=wood  2=stone  3=glass  4=rubber  5=bone  6=ceramic  7=cloth
8=water  9=oil  10=slime  11=ice  12=lava  13=fire  14=smoke  15=flesh

metal: swords, armor, coins, anvils
wood: furniture, sticks, barrels, trees
stone: rocks, boulders, walls, statues
glass: bottles, windows, crystal, mirrors
rubber: balls, tires, erasers, bouncy things
bone: skeletons, fossils, horns, tusks
ceramic: pottery, tiles, bricks
cloth: flags, clothing, sails, carpets
water: water bodies, puddles
oil: oil slicks, fuel, grease
slime: slime blobs, ooze, goop
ice: ice blocks, icicles, frost
lava: lava flows, magma pools
fire: flames, campfires, infernos
smoke: smoke clouds, steam, mist
flesh: creatures, monsters, animals, people"""

SUBSTANCES = [
    "metal", "wood", "stone", "glass", "rubber", "bone", "ceramic", "cloth",
    "water", "oil", "slime", "ice", "lava", "fire", "smoke", "flesh",
]

ELEMENT_PROMPT = """\
Pick an optional element for a game object. Reply with ONLY the number.

0=none  1=burning  2=electric  3=magnetic  4=freezing  5=acidic  6=toxic  7=windy

burning: fire sword, lava golem
electric: lightning rod, electric eel
magnetic: lodestone, magnetic crane
freezing: ice breath, frost wand
acidic: acid spider, corrosive slime
toxic: poison dart, toxic mushroom
windy: fan, tornado, jet engine"""

ELEMENTS = [None, "burning", "electric", "magnetic", "freezing", "acidic", "toxic", "windy"]

CATEGORIES_PROMPT = """\
Pick 0-3 categories for a game object. Reply with ONLY the numbers, comma-separated. Reply "none" if no categories fit.

0=CREATURE (living being)  1=FOOD (edible)  2=WEAPON (deals damage)  3=PLANT (plant/fungus)
4=VALUABLE (precious/collectible)  5=VEHICLE (rideable)  6=TOOL (utility)

A wolf=[0]. A donut=[1]. A fire sword=[2]. A tree=[3]. A gold coin=[4]. A cart=[5]. A rope=[6]. A campfire=none."""

CATEGORIES = ["CREATURE", "FOOD", "WEAPON", "PLANT", "VALUABLE", "VEHICLE", "TOOL"]

NAME_PROMPT = """\
Give this game object a name. Reply with ONLY the name (1-3 words, no quotes, no explanation)."""

TAGS_PROMPT = """\
Pick 0-3 physical tags for a game object. Reply with ONLY the numbers, comma-separated. Reply "none" if no tags fit.

0=SHARP (cutting edge)  1=HEAVY (dense, massive)  2=LIGHT (low mass)  3=BOUNCY (elastic)
4=BREAKABLE (fragile)  5=STICKY (adhesive)  6=REFLECTIVE (mirror-like)  7=EXPLOSIVE (volatile)
8=FLYING (defies gravity)  9=WET (damp)

The object is made of {substance}{element_str}. Don't pick tags the substance already provides."""

TAGS = ["SHARP", "HEAVY", "LIGHT", "BOUNCY", "BREAKABLE", "STICKY", "REFLECTIVE", "EXPLOSIVE", "FLYING", "WET"]

BEHAVIORS_PROMPT = """\
Design 1-4 behaviors for this creature, in priority order. Reply with JSON array ONLY.
Each: {{"verb": N, "target": N, "desc": "short phrase"}}

Verbs: 0=destroy 1=eat 2=investigate 3=follow 4=protect 5=flee
Targets: 0=CREATURE 1=FOOD 2=WEAPON 3=PLANT 4=VALUABLE 5=VEHICLE 6=TOOL 7=HOSTILE 8=HEAT_SOURCE 9=(empty/anything)

destroy/eat/flee MUST have target 0-8. investigate/follow/protect can use 9.

Examples:
- Wolf: [{{"verb":0,"target":0,"desc":"hunt prey"}},{{"verb":5,"target":8,"desc":"fire"}}]
- Knight: [{{"verb":0,"target":7,"desc":"monsters"}},{{"verb":4,"target":0,"desc":"villagers"}}]"""

BEHAVIOR_VERBS = ["destroy", "eat", "investigate", "follow", "protect", "flee"]
BEHAVIOR_TARGETS = ["CREATURE", "FOOD", "WEAPON", "PLANT", "VALUABLE", "VEHICLE", "TOOL", "HOSTILE", "HEAT_SOURCE", ""]

VISUAL_PROMPT = """\
Write a visual description for a game sprite. Reply with JSON ONLY:
{{"desc": "1-2 sentences describing appearance", "size": N}}

Sizes: 0=tiny 1=small 2=medium 3=large 4=huge

The object is: {description}
Made of: {substance}{element_str}
Categories: {categories}"""

SIZES = ["tiny", "small", "medium", "large", "huge"]


# ---------------------------------------------------------------------------
# Async HTTP helper
# ---------------------------------------------------------------------------

async def async_chat(
    client: httpx.AsyncClient,
    system: str,
    user: str,
    *,
    json_mode: bool = False,
    max_tokens: int = 256,
) -> dict:
    """Single async chat completion. Returns timing + token info."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    body: dict = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        **SAMPLING,
        **EXTRA_BODY,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    t0 = time.perf_counter()
    resp = await client.post(f"{BASE_URL}/chat/completions", json=body, timeout=60)
    elapsed = time.perf_counter() - t0
    resp.raise_for_status()
    data = resp.json()

    usage = data.get("usage", {})
    content = data["choices"][0]["message"]["content"]

    return {
        "elapsed": elapsed,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "content": content.strip(),
    }


def parse_number(text: str, max_val: int) -> int | None:
    """Extract first integer from text, bounded."""
    text = text.strip().strip('"').strip("'")
    for word in text.replace(",", " ").split():
        try:
            n = int(word)
            if 0 <= n <= max_val:
                return n
        except ValueError:
            continue
    return None


def parse_number_list(text: str, max_val: int) -> list[int]:
    """Extract comma-separated integers."""
    if "none" in text.lower():
        return []
    nums = []
    for word in text.replace(",", " ").split():
        try:
            n = int(word)
            if 0 <= n <= max_val:
                nums.append(n)
        except ValueError:
            continue
    return nums


# ---------------------------------------------------------------------------
# Sync HTTP helper (for single-call baseline + warmup)
# ---------------------------------------------------------------------------

def sync_chat(
    client: httpx.Client,
    system: str,
    user: str,
    *,
    json_mode: bool = True,
) -> dict:
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
        "content": content,
    }


# ---------------------------------------------------------------------------
# Graph strategy
# ---------------------------------------------------------------------------

async def run_graph(client: httpx.AsyncClient, prompt: str) -> dict:
    """Graph approach: parallel micro-calls with minimal output tokens."""
    t0 = time.perf_counter()
    call_log: list[dict] = []

    # --- Layer 1: parallel independent decisions ---
    layer1_tasks = {
        "substance": async_chat(client, SUBSTANCE_PROMPT, f"Object: {prompt}", max_tokens=8),
        "element": async_chat(client, ELEMENT_PROMPT, f"Object: {prompt}", max_tokens=8),
        "categories": async_chat(client, CATEGORIES_PROMPT, f"Object: {prompt}", max_tokens=16),
        "name": async_chat(client, NAME_PROMPT, f"Object: {prompt}", max_tokens=16),
    }

    layer1_results = {}
    layer1_items = list(layer1_tasks.items())
    results = await asyncio.gather(*[t for _, t in layer1_items])
    for (key, _), result in zip(layer1_items, results):
        layer1_results[key] = result
        call_log.append({"call": key, "elapsed": result["elapsed"],
                         "prompt_tokens": result["prompt_tokens"],
                         "completion_tokens": result["completion_tokens"],
                         "content": result["content"]})

    layer1_elapsed = time.perf_counter() - t0

    # Parse layer 1
    sub_idx = parse_number(layer1_results["substance"]["content"], 15)
    substance = SUBSTANCES[sub_idx] if sub_idx is not None else "stone"

    elem_idx = parse_number(layer1_results["element"]["content"], 7)
    element = ELEMENTS[elem_idx] if elem_idx is not None else None

    cat_indices = parse_number_list(layer1_results["categories"]["content"], 6)
    categories = [CATEGORIES[i] for i in cat_indices[:3]]

    name = layer1_results["name"]["content"].strip('"').strip("'")[:50]

    is_creature = "CREATURE" in categories
    element_str = f" + {element}" if element else ""

    # --- Layer 2: parallel dependent decisions ---
    t1 = time.perf_counter()

    tags_system = TAGS_PROMPT.format(substance=substance, element_str=element_str)
    layer2_tasks: dict[str, any] = {
        "tags": async_chat(client, tags_system, f"Object: {prompt}", max_tokens=16),
        "visual": async_chat(
            client,
            VISUAL_PROMPT.format(
                description=prompt, substance=substance,
                element_str=element_str, categories=", ".join(categories) or "none",
            ),
            f"Describe: {prompt}",
            json_mode=True, max_tokens=128,
        ),
    }
    if is_creature:
        layer2_tasks["behaviors"] = async_chat(
            client, BEHAVIORS_PROMPT, f"Creature: {prompt}", json_mode=True, max_tokens=128,
        )

    layer2_items = list(layer2_tasks.items())
    results2 = await asyncio.gather(*[t for _, t in layer2_items])
    for (key, _), result in zip(layer2_items, results2):
        layer1_results[key] = result
        call_log.append({"call": key, "elapsed": result["elapsed"],
                         "prompt_tokens": result["prompt_tokens"],
                         "completion_tokens": result["completion_tokens"],
                         "content": result["content"]})

    layer2_elapsed = time.perf_counter() - t1
    total_elapsed = time.perf_counter() - t0

    # Aggregate tokens
    total_prompt_tokens = sum(c["prompt_tokens"] for c in call_log)
    total_completion_tokens = sum(c["completion_tokens"] for c in call_log)
    total_calls = len(call_log)

    return {
        "strategy": "graph",
        "prompt": prompt,
        "calls": total_calls,
        "is_creature": is_creature,
        "total_elapsed": total_elapsed,
        "layer1_elapsed": layer1_elapsed,
        "layer2_elapsed": layer2_elapsed,
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
        "total_tokens": total_prompt_tokens + total_completion_tokens,
        "call_log": call_log,
        # Parsed output for inspection
        "parsed": {
            "name": name,
            "substance": substance,
            "element": element,
            "categories": categories,
            "tags": [TAGS[i] for i in parse_number_list(
                layer1_results.get("tags", {}).get("content", ""), 9)][:3],
        },
    }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def async_main(num_runs: int, num_prompts: int | None) -> None:
    prompts = TEST_PROMPTS[:num_prompts] if num_prompts else TEST_PROMPTS

    # Check server
    print(f"Connecting to {BASE_URL} ...")
    sync_client = httpx.Client(timeout=120)
    try:
        resp = sync_client.get(f"{BASE_URL}/models")
        resp.raise_for_status()
        models = resp.json()
        print(f"Server OK. Models: {[m['id'] for m in models.get('data', [])]}")
    except Exception as e:
        print(f"ERROR: Cannot reach SGLang at {BASE_URL}: {e}")
        sys.exit(1)

    # Warmup
    print(f"\n{'='*70}")
    print("WARMUP (3 requests)")
    print(f"{'='*70}")
    for i in range(3):
        r = sync_chat(sync_client, "You are helpful.", 'Say "ready" in JSON: {"status": "ready"}')
        print(f"  warmup {i+1}: {r['elapsed']:.3f}s")

    # Results
    single_results: list[dict] = []
    graph_results: list[dict] = []

    async with httpx.AsyncClient(timeout=120) as async_client:
        for run_idx in range(num_runs):
            print(f"\n{'='*70}")
            print(f"RUN {run_idx + 1}/{num_runs}")
            print(f"{'='*70}")

            for prompt in prompts:
                # Single call (sync — no parallelism to compare against)
                s = sync_chat(
                    sync_client,
                    FULL_SYSTEM_PROMPT,
                    f"Create a game object for: {prompt}\n\nRespond with JSON.",
                )
                single_result = {
                    "strategy": "single",
                    "prompt": prompt,
                    "calls": 1,
                    "total_elapsed": s["elapsed"],
                    "prompt_tokens": s["prompt_tokens"],
                    "completion_tokens": s["completion_tokens"],
                    "total_tokens": s["prompt_tokens"] + s["completion_tokens"],
                }
                single_results.append(single_result)

                # Graph call (async parallel)
                g = await run_graph(async_client, prompt)
                graph_results.append(g)

                delta = g["total_elapsed"] - s["elapsed"]
                sign = "+" if delta > 0 else ""
                print(
                    f"  {prompt:20s} | "
                    f"single: {s['elapsed']:.2f}s ({s['completion_tokens']:3d} out) | "
                    f"graph: {g['total_elapsed']:.2f}s ({g['completion_tokens']:3d} out, "
                    f"{g['calls']} calls) | "
                    f"delta: {sign}{delta:.2f}s"
                )

    sync_client.close()

    # ---------------------------------------------------------------------------
    # Analysis
    # ---------------------------------------------------------------------------
    print(f"\n{'='*70}")
    print("RESULTS SUMMARY")
    print(f"{'='*70}")

    def summarize(results: list[dict], label: str) -> dict:
        times = [r["total_elapsed"] for r in results]
        ptoks = [r["prompt_tokens"] for r in results]
        ctoks = [r["completion_tokens"] for r in results]
        ttoks = [r["total_tokens"] for r in results]
        s = {
            "time_mean": statistics.mean(times),
            "time_median": statistics.median(times),
            "time_stdev": statistics.stdev(times) if len(times) > 1 else 0,
            "time_min": min(times),
            "time_max": max(times),
            "prompt_tokens_mean": statistics.mean(ptoks),
            "completion_tokens_mean": statistics.mean(ctoks),
            "total_tokens_mean": statistics.mean(ttoks),
        }
        print(f"\n--- {label} ({len(results)} samples) ---")
        print(f"  Latency:  mean={s['time_mean']:.3f}s  "
              f"median={s['time_median']:.3f}s  "
              f"stdev={s['time_stdev']:.3f}s  "
              f"range=[{s['time_min']:.3f}s, {s['time_max']:.3f}s]")
        print(f"  Tokens:   prompt={s['prompt_tokens_mean']:.0f}  "
              f"completion={s['completion_tokens_mean']:.0f}  "
              f"total={s['total_tokens_mean']:.0f}")
        return s

    s_sum = summarize(single_results, "Single Call (full prompt)")
    g_sum = summarize(graph_results, "Graph (parallel micro-calls)")

    # Per-prompt
    print(f"\n--- Per-prompt averages ---")
    print(f"  {'Prompt':20s} | {'Single':>8s} | {'Graph':>8s} | {'Delta':>8s} | "
          f"{'Out S':>6s} | {'Out G':>6s} | {'Calls':>5s}")
    print(f"  {'-'*20}-+-{'-'*8}-+-{'-'*8}-+-{'-'*8}-+-{'-'*6}-+-{'-'*6}-+-{'-'*5}")
    for prompt in prompts:
        st = [r["total_elapsed"] for r in single_results if r["prompt"] == prompt]
        gt = [r["total_elapsed"] for r in graph_results if r["prompt"] == prompt]
        sc = [r["completion_tokens"] for r in single_results if r["prompt"] == prompt]
        gc = [r["completion_tokens"] for r in graph_results if r["prompt"] == prompt]
        gn = [r["calls"] for r in graph_results if r["prompt"] == prompt]
        s_avg, g_avg = statistics.mean(st), statistics.mean(gt)
        d = g_avg - s_avg
        sign = "+" if d > 0 else ""
        print(f"  {prompt:20s} | {s_avg:7.2f}s | {g_avg:7.2f}s | {sign}{d:7.2f}s | "
              f"{statistics.mean(sc):5.0f} | {statistics.mean(gc):5.0f} | {statistics.mean(gn):4.0f}")

    # Bottom line
    overhead = g_sum["time_mean"] - s_sum["time_mean"]
    pct = (overhead / s_sum["time_mean"]) * 100 if s_sum["time_mean"] > 0 else 0
    print(f"\n{'='*70}")
    print(f"BOTTOM LINE")
    print(f"{'='*70}")
    print(f"  Single call avg:    {s_sum['time_mean']:.3f}s  ({s_sum['completion_tokens_mean']:.0f} output tokens)")
    print(f"  Graph avg:          {g_sum['time_mean']:.3f}s  ({g_sum['completion_tokens_mean']:.0f} output tokens)")
    print(f"  Overhead:           {overhead:+.3f}s ({pct:+.1f}%)")
    print(f"  Prompt token total: single={s_sum['prompt_tokens_mean']:.0f} vs graph={g_sum['prompt_tokens_mean']:.0f}")

    # Graph layer breakdown
    l1 = [r["layer1_elapsed"] for r in graph_results]
    l2 = [r["layer2_elapsed"] for r in graph_results]
    print(f"\n  Graph layer breakdown (wall-clock, parallel):")
    print(f"    Layer 1 (substance+element+categories+name):  "
          f"mean={statistics.mean(l1):.3f}s  median={statistics.median(l1):.3f}s")
    print(f"    Layer 2 (tags+visual+behaviors):              "
          f"mean={statistics.mean(l2):.3f}s  median={statistics.median(l2):.3f}s")

    # Per-call breakdown within graph
    print(f"\n  Per-call latency within graph:")
    call_names = ["substance", "element", "categories", "name", "tags", "visual", "behaviors"]
    for cname in call_names:
        ctimes = []
        ctokens = []
        for r in graph_results:
            for c in r["call_log"]:
                if c["call"] == cname:
                    ctimes.append(c["elapsed"])
                    ctokens.append(c["completion_tokens"])
        if ctimes:
            print(f"    {cname:14s}: mean={statistics.mean(ctimes):.3f}s  "
                  f"out_tokens={statistics.mean(ctokens):.1f}  (n={len(ctimes)})")

    # Creature vs non-creature
    creature_g = [r for r in graph_results if r.get("is_creature")]
    object_g = [r for r in graph_results if not r.get("is_creature")]
    if creature_g:
        print(f"\n  Graph creatures ({len(creature_g)} samples):  "
              f"mean={statistics.mean([r['total_elapsed'] for r in creature_g]):.3f}s")
    if object_g:
        print(f"  Graph objects  ({len(object_g)} samples):  "
              f"mean={statistics.mean([r['total_elapsed'] for r in object_g]):.3f}s")

    # Show a few parsed examples
    print(f"\n--- Sample parsed outputs (graph) ---")
    seen = set()
    for r in graph_results:
        if r["prompt"] not in seen and len(seen) < 4:
            seen.add(r["prompt"])
            p = r["parsed"]
            print(f"  {r['prompt']:20s} -> {p['name']}, {p['substance']}, "
                  f"{p['element']}, cats={p['categories']}, tags={p['tags']}")


def main():
    parser = argparse.ArgumentParser(description="Benchmark single vs graph LLM calls")
    parser.add_argument("--runs", type=int, default=3, help="Number of full runs (default: 3)")
    parser.add_argument("--prompts", type=int, default=None, help="Number of prompts (default: all 12)")
    args = parser.parse_args()
    asyncio.run(async_main(num_runs=args.runs, num_prompts=args.prompts))


if __name__ == "__main__":
    main()
