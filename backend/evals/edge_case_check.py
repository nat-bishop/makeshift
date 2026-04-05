"""Quick check: would the firefighter find a burning tree via embeddings alone?
And would a vegetarian avoid meat?

Tests the exact scenarios the user is asking about.
"""

from __future__ import annotations

import asyncio
import math
import sys

import httpx

OLLAMA_URL = "http://127.0.0.1:11434"
RETRIEVAL_PREFIX = "Instruct: Retrieve objects matching this description.\nQuery: "


async def embed(texts: list[str], model: str = "qwen3-embedding:0.6b") -> list[list[float]]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{OLLAMA_URL}/api/embed", json={"model": model, "input": texts}
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]


def sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


async def main() -> None:
    try:
        httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5).raise_for_status()
    except Exception:
        print("Ollama not available")  # noqa: T201
        sys.exit(1)

    print("=" * 80)  # noqa: T201
    print("SCENARIO 1: Firefighter — would embeddings catch a burning tree?")  # noqa: T201
    print("=" * 80)  # noqa: T201

    firefighter_targets = [
        "fires and burning things",
    ]
    objects = [
        ("Oak Tree (normal)", "Oak Tree, a tall green oak tree, large, made of wood"),
        ("Oak Tree (burning)", "Oak Tree, a tall green oak tree, large, made of wood"),
        ("Campfire", "Campfire, dancing orange flames on logs, medium, made of fire"),
        ("Ice Cube (burning)", "Ice Cube, a small cube of translucent ice, small, made of ice"),
        ("Metal Shield (burning)", "Metal Shield, a round iron shield, medium, made of metal"),
        ("Rubber Duck (burning)", "Rubber Duck, a cheerful yellow rubber duck, small, made of rubber"),
        ("Stone Wall (burning)", "Stone Wall, a thick gray stone wall, huge, made of stone"),
    ]

    for target in firefighter_targets:
        # Test both raw and instructed queries
        raw_query = target
        inst_query = f"{RETRIEVAL_PREFIX}{target}"

        all_texts = [raw_query, inst_query] + [o[1] for o in objects]
        embeddings = await embed(all_texts)
        raw_emb = embeddings[0]
        inst_emb = embeddings[1]
        obj_embs = embeddings[2:]

        print(f'\n  Target: "{target}"')  # noqa: T201
        print(f"  Note: all objects have IDENTICAL identity (no tags in embedding).")  # noqa: T201
        print(f"  Whether it's burning is ONLY known via tags, not embeddings.\n")  # noqa: T201
        print(f"  {'Object':<30} {'Raw sim':>8} {'Match?':>7} | {'Instr sim':>9} {'Match?':>7}")  # noqa: T201
        print(f"  {'-'*70}")  # noqa: T201

        for i, (name, _text) in enumerate(objects):
            raw_s = sim(raw_emb, obj_embs[i])
            inst_s = sim(inst_emb, obj_embs[i])
            raw_m = "YES" if raw_s >= 0.5 else "no"
            inst_m = "YES" if inst_s >= 0.5 else "no"
            print(f"  {name:<30} {raw_s:>8.3f} {raw_m:>7} | {inst_s:>9.3f} {inst_m:>7}")  # noqa: T201

    print(f"\n  CONCLUSION: Embeddings alone can't tell if something is burning.")  # noqa: T201
    print(f"  The identity string is the same whether it's on fire or not.")  # noqa: T201
    print(f"  Only HEAT_SOURCE tag knows it's burning. Tags solve this.\n")  # noqa: T201

    print("=" * 80)  # noqa: T201
    print("SCENARIO 2: Vegetarian — does it avoid meat?")  # noqa: T201
    print("=" * 80)  # noqa: T201

    veg_targets = [
        "vegetables, fruits, and plants",
        "food",
    ]
    foods = [
        ("Carrot", "Carrot, an orange carrot with green leafy top, small, made of wood"),
        ("Apple", "Apple, a shiny red apple, small, made of flesh"),
        ("Salad", "Salad, a bowl of fresh green lettuce and tomatoes, small, made of wood"),
        ("Steak", "Steak, a juicy grilled ribeye steak, small, made of flesh"),
        ("Chicken Leg", "Chicken Leg, a roasted golden chicken drumstick, small, made of flesh"),
        ("Fish Fillet", "Fish Fillet, a fresh pink salmon fillet, small, made of flesh"),
        ("Bread", "Bread, a warm crusty loaf of bread, small, made of cloth"),
        ("Sword", "Steel Sword, a gleaming sharp steel blade, medium, made of metal"),
    ]

    for target in veg_targets:
        inst_query = f"{RETRIEVAL_PREFIX}{target}"
        all_texts = [inst_query] + [f[1] for f in foods]
        embeddings = await embed(all_texts)
        q_emb = embeddings[0]
        obj_embs = embeddings[1:]

        print(f'\n  Target: "{target}" (instructed)')  # noqa: T201
        print(f"  {'Object':<25} {'Sim':>8} {'Match (>=0.5)?':>15}")  # noqa: T201
        print(f"  {'-'*50}")  # noqa: T201

        for i, (name, _text) in enumerate(foods):
            s = sim(q_emb, obj_embs[i])
            m = "YES" if s >= 0.5 else "no"
            print(f"  {name:<25} {s:>8.3f} {m:>15}")  # noqa: T201

    print(f"\n  KEY QUESTION: Does 'vegetables, fruits, and plants' avoid meat?")  # noqa: T201
    print(f"  And does 'food' (too broad) match everything edible?")  # noqa: T201

    print(f"\n{'='*80}")  # noqa: T201
    print("SCENARIO 3: What tags would the LLM actually output?")  # noqa: T201
    print("=" * 80)  # noqa: T201
    print("""
  The LLM decides target_tags. Consider what it would output:

  Firefighter:  destroy -> "fires"         target_tags: [HEAT_SOURCE]  -> tag mode
  Vegetarian:   eat    -> "vegetables"     target_tags: []             -> embedding mode
  Wolf:         destroy -> "prey animals"  target_tags: [LIVING]       -> tag mode
  Cop:          eat    -> "donuts"         target_tags: []             -> embedding mode
  Guard:        destroy -> "enemies"       target_tags: [HOSTILE]      -> tag mode

  State-dependent behaviors get tags. Identity-only behaviors get embeddings.
  The LLM naturally separates these because it understands the intent.
""")  # noqa: T201


if __name__ == "__main__":
    asyncio.run(main())
