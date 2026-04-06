"""Benchmark: minimal-output LLM calls (1-3 tokens).

Tests how fast a warmed-up local LLM can answer simple classification
questions with single-token or near-single-token responses. This tells
us whether LLM calls are viable at interaction time (per-frame or
per-collision) vs only at creation time.

Usage:
    cd backend && uv run python bench_single_token.py
"""

from __future__ import annotations

import asyncio
import statistics
import sys
import time

import httpx

BASE_URL = "http://127.0.0.1:5200/v1"
MODEL = "Qwen/Qwen3.5-35B-A3B-FP8"

SAMPLING = {
    "temperature": 0.0,  # deterministic for latency testing
    "top_p": 1.0,
}

EXTRA_BODY = {
    "chat_template_kwargs": {"enable_thinking": False},
}


async def async_chat(
    client: httpx.AsyncClient,
    system: str,
    user: str,
    max_tokens: int = 4,
) -> dict:
    body: dict = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        **SAMPLING,
        **EXTRA_BODY,
    }
    t0 = time.perf_counter()
    resp = await client.post(f"{BASE_URL}/chat/completions", json=body, timeout=30)
    elapsed = time.perf_counter() - t0
    resp.raise_for_status()
    data = resp.json()
    usage = data.get("usage", {})
    return {
        "elapsed": elapsed,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "content": data["choices"][0]["message"]["content"].strip(),
    }


# ---------------------------------------------------------------------------
# Test scenarios — things you might ask at interaction time
# ---------------------------------------------------------------------------

TESTS = [
    {
        "name": "yes/no question",
        "system": "Answer YES or NO only.",
        "user": "Can fire melt ice?",
        "max_tokens": 2,
    },
    {
        "name": "pick a number (0-5)",
        "system": "Reply with ONLY a number 0-5.\n0=none 1=low 2=medium 3=high 4=very high 5=extreme",
        "user": "How much damage does a fire sword do to a wooden barrel?",
        "max_tokens": 2,
    },
    {
        "name": "pick from list",
        "system": "Reply with ONLY the number.\n0=ignite 1=freeze 2=corrode 3=electrify 4=nothing",
        "user": "What happens when lava touches wood?",
        "max_tokens": 2,
    },
    {
        "name": "short classification",
        "system": "Reply with ONLY: solid, liquid, gas, or energy",
        "user": "What state is smoke?",
        "max_tokens": 3,
    },
    {
        "name": "boolean with context",
        "system": "You are a game physics engine. Reply 0 or 1 only.\n0=no 1=yes",
        "user": "Object A has tags: HEAT_SOURCE, HOT. Object B has tags: FLAMMABLE, LIGHT. Does A ignite B?",
        "max_tokens": 2,
    },
    {
        "name": "interaction result",
        "system": "Reply with ONLY the number.\n0=nothing 1=damage 2=heal 3=transform 4=destroy 5=bounce",
        "user": "A heavy stone boulder falls on a glass bottle. What happens?",
        "max_tokens": 2,
    },
    {
        "name": "longer prompt, 1 token out",
        "system": "You are a game rule engine. Objects interact based on their substance and tags. "
                  "Given two objects and their properties, reply with ONLY a number 0-9 indicating "
                  "the interaction type.\n"
                  "0=nothing 1=burn 2=freeze 3=corrode 4=electrify 5=break 6=bounce 7=stick 8=explode 9=heal",
        "user": "Object A: 'Fire Sword' substance=metal element=burning tags=[SHARP, HEAT_SOURCE, HOT] categories=[WEAPON]\n"
                "Object B: 'Ice Golem' substance=ice element=freezing tags=[FROZEN, RIGID, COLD, HEAVY] categories=[CREATURE]\n"
                "What interaction type?",
        "max_tokens": 2,
    },
    {
        "name": "trivial (warmup baseline)",
        "system": "Reply 1.",
        "user": "Go.",
        "max_tokens": 2,
    },
]


async def main():
    print(f"Connecting to {BASE_URL} ...")
    async with httpx.AsyncClient(timeout=30) as client:
        # Check server
        resp = await client.get(f"{BASE_URL}/models")
        if resp.status_code != 200:
            print(f"ERROR: Cannot reach server")
            sys.exit(1)
        print("Server OK.\n")

        # Warmup
        print("=" * 70)
        print("WARMUP (10 sequential calls)")
        print("=" * 70)
        warmup_times = []
        for i in range(10):
            r = await async_chat(client, "Reply 1.", "Go.", max_tokens=2)
            warmup_times.append(r["elapsed"])
            print(f"  {i+1:2d}: {r['elapsed']*1000:6.1f}ms  ({r['completion_tokens']} tokens) -> {r['content']!r}")

        print(f"\n  First:  {warmup_times[0]*1000:.1f}ms")
        print(f"  Last 5: {statistics.mean(warmup_times[-5:])*1000:.1f}ms avg")
        print(f"  Min:    {min(warmup_times)*1000:.1f}ms")

        # Sequential test — one at a time
        print(f"\n{'='*70}")
        print("SEQUENTIAL (one call at a time, 20 reps each)")
        print(f"{'='*70}")
        seq_results: dict[str, list[float]] = {}
        for test in TESTS:
            times = []
            for _ in range(20):
                r = await async_chat(client, test["system"], test["user"], max_tokens=test["max_tokens"])
                times.append(r["elapsed"])
            seq_results[test["name"]] = times
            print(f"  {test['name']:30s} | "
                  f"mean={statistics.mean(times)*1000:5.1f}ms  "
                  f"median={statistics.median(times)*1000:5.1f}ms  "
                  f"p95={sorted(times)[int(len(times)*0.95)]*1000:5.1f}ms  "
                  f"min={min(times)*1000:5.1f}ms")

        # Parallel burst — fire N calls at once
        print(f"\n{'='*70}")
        print("PARALLEL BURST (all tests fired at once, 10 reps)")
        print(f"{'='*70}")
        burst_wall_times = []
        burst_individual_times: list[float] = []
        for rep in range(10):
            tasks = []
            for test in TESTS:
                tasks.append(async_chat(client, test["system"], test["user"], max_tokens=test["max_tokens"]))
            t0 = time.perf_counter()
            results = await asyncio.gather(*tasks)
            wall = time.perf_counter() - t0
            burst_wall_times.append(wall)
            for r in results:
                burst_individual_times.append(r["elapsed"])
            print(f"  Rep {rep+1:2d}: wall={wall*1000:5.1f}ms  "
                  f"slowest={max(r['elapsed'] for r in results)*1000:5.1f}ms  "
                  f"fastest={min(r['elapsed'] for r in results)*1000:5.1f}ms")

        # Parallel burst — just the number-output calls (simulating graph layer 1)
        print(f"\n{'='*70}")
        print("PARALLEL BURST - 4 number-only calls (simulating graph layer 1)")
        print(f"{'='*70}")
        number_tests = [t for t in TESTS if "number" in t["name"] or "pick" in t["name"]
                        or "yes/no" in t["name"] or "boolean" in t["name"]]
        if len(number_tests) < 4:
            number_tests = TESTS[:4]
        layer1_times = []
        for rep in range(20):
            tasks = [async_chat(client, t["system"], t["user"], max_tokens=2) for t in number_tests]
            t0 = time.perf_counter()
            results = await asyncio.gather(*tasks)
            wall = time.perf_counter() - t0
            layer1_times.append(wall)
        print(f"  {len(number_tests)} parallel calls, 20 reps:")
        print(f"  mean={statistics.mean(layer1_times)*1000:5.1f}ms  "
              f"median={statistics.median(layer1_times)*1000:5.1f}ms  "
              f"min={min(layer1_times)*1000:5.1f}ms  "
              f"max={max(layer1_times)*1000:5.1f}ms")

        # Summary
        print(f"\n{'='*70}")
        print("SUMMARY")
        print(f"{'='*70}")
        all_seq = [t for times in seq_results.values() for t in times]
        print(f"  Single sequential call (1-3 token output):")
        print(f"    mean={statistics.mean(all_seq)*1000:5.1f}ms  "
              f"median={statistics.median(all_seq)*1000:5.1f}ms  "
              f"min={min(all_seq)*1000:5.1f}ms  "
              f"max={max(all_seq)*1000:5.1f}ms")
        print(f"\n  Parallel burst ({len(TESTS)} calls at once), wall-clock:")
        print(f"    mean={statistics.mean(burst_wall_times)*1000:5.1f}ms  "
              f"median={statistics.median(burst_wall_times)*1000:5.1f}ms  "
              f"min={min(burst_wall_times)*1000:5.1f}ms")
        print(f"\n  4-call parallel layer, wall-clock:")
        print(f"    mean={statistics.mean(layer1_times)*1000:5.1f}ms  "
              f"median={statistics.median(layer1_times)*1000:5.1f}ms  "
              f"min={min(layer1_times)*1000:5.1f}ms")

        # Feasibility assessment
        seq_mean_ms = statistics.mean(all_seq) * 1000
        burst_mean_ms = statistics.mean(burst_wall_times) * 1000
        print(f"\n  --- Feasibility for interaction-time use ---")
        print(f"  60 FPS frame budget:  16.7ms")
        print(f"  30 FPS frame budget:  33.3ms")
        print(f"  Typical interaction:  ~100-200ms acceptable")
        print(f"  Sequential call:      {seq_mean_ms:.1f}ms {'OK' if seq_mean_ms < 200 else 'TOO SLOW'}")
        print(f"  Parallel burst:       {burst_mean_ms:.1f}ms {'OK' if burst_mean_ms < 200 else 'TOO SLOW'}")


if __name__ == "__main__":
    asyncio.run(main())
