"""Benchmark: how does concurrent request count affect latency?

Tests batching 1, 2, 4, 8, 16, 32, 64 simultaneous requests
to find where throughput saturates and latency degrades.

Usage:
    cd backend && uv run python bench_concurrency.py
"""

from __future__ import annotations

import asyncio
import statistics
import time

import httpx

BASE_URL = "http://127.0.0.1:5200/v1"
MODEL = "Qwen/Qwen3.5-35B-A3B-FP8"
EXTRA_BODY = {"chat_template_kwargs": {"enable_thinking": False}}

BATCH_SIZES = [1, 2, 4, 8, 16, 32, 64, 128]
REPS = 5


async def chat(client: httpx.AsyncClient, max_tokens: int = 5) -> dict:
    body = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": "Reply with ONLY a number 0-5."},
            {"role": "user", "content": "How dangerous is fire to wood? 0=none 5=extreme"},
        ],
        **EXTRA_BODY,
    }
    t0 = time.perf_counter()
    resp = await client.post(f"{BASE_URL}/chat/completions", json=body, timeout=120)
    elapsed = time.perf_counter() - t0
    resp.raise_for_status()
    data = resp.json()
    usage = data.get("usage", {})
    return {
        "elapsed": elapsed,
        "completion_tokens": usage.get("completion_tokens", 0),
    }


async def main():
    async with httpx.AsyncClient(timeout=120, limits=httpx.Limits(
        max_connections=200, max_keepalive_connections=200,
    )) as client:
        # Warmup
        print("Warming up...")
        for _ in range(10):
            await chat(client)

        # --- Test 1: minimal output (1-2 tokens) - pure scheduling overhead ---
        print(f"\n{'='*70}")
        print(f"CONCURRENCY SCALING - minimal output (max_tokens=2)")
        print(f"{'='*70}")
        print(f"  {'Batch':>5s} | {'Wall':>7s} | {'Slowest':>8s} | {'Fastest':>8s} | {'Throughput':>10s} | {'Per-req':>7s}")
        print(f"  {'-'*5}-+-{'-'*7}-+-{'-'*8}-+-{'-'*8}-+-{'-'*10}-+-{'-'*7}")

        for batch_size in BATCH_SIZES:
            walls = []
            all_individual = []
            for _ in range(REPS):
                t0 = time.perf_counter()
                results = await asyncio.gather(*[chat(client, max_tokens=2) for _ in range(batch_size)])
                wall = time.perf_counter() - t0
                walls.append(wall)
                all_individual.extend([r["elapsed"] for r in results])

            mean_wall = statistics.mean(walls)
            throughput = batch_size / mean_wall
            mean_individual = statistics.mean(all_individual)
            slowest = max(all_individual)
            fastest = min(all_individual)
            print(f"  {batch_size:5d} | {mean_wall*1000:6.0f}ms | {slowest*1000:7.0f}ms | "
                  f"{fastest*1000:7.0f}ms | {throughput:8.1f}/s | {mean_individual*1000:6.0f}ms")

        # --- Test 2: 10 token output - more realistic ---
        print(f"\n{'='*70}")
        print(f"CONCURRENCY SCALING - 10 token output")
        print(f"{'='*70}")
        print(f"  {'Batch':>5s} | {'Wall':>7s} | {'Slowest':>8s} | {'Fastest':>8s} | {'Throughput':>10s}")
        print(f"  {'-'*5}-+-{'-'*7}-+-{'-'*8}-+-{'-'*8}-+-{'-'*10}")

        for batch_size in BATCH_SIZES:
            walls = []
            all_individual = []
            for _ in range(REPS):
                t0 = time.perf_counter()
                results = await asyncio.gather(*[chat(client, max_tokens=10) for _ in range(batch_size)])
                wall = time.perf_counter() - t0
                walls.append(wall)
                all_individual.extend([r["elapsed"] for r in results])

            mean_wall = statistics.mean(walls)
            throughput = batch_size / mean_wall
            slowest = max(all_individual)
            fastest = min(all_individual)
            print(f"  {batch_size:5d} | {mean_wall*1000:6.0f}ms | {slowest*1000:7.0f}ms | "
                  f"{fastest*1000:7.0f}ms | {throughput:8.1f}/s")

        # --- Test 3: mixed - simulating graph approach ---
        print(f"\n{'='*70}")
        print(f"CONCURRENCY SCALING - mixed (4x tiny + 1x medium, like graph)")
        print(f"{'='*70}")

        async def graph_like_burst(client):
            """4 tiny calls + 1 medium call in parallel"""
            tiny = [chat(client, max_tokens=2) for _ in range(4)]
            medium = [chat(client, max_tokens=25)]
            t0 = time.perf_counter()
            results = await asyncio.gather(*tiny, *medium)
            wall = time.perf_counter() - t0
            return wall, results

        # Multiple graph bursts running at the same time (simulating multiple players)
        for num_players in [1, 2, 4, 8]:
            walls = []
            for _ in range(REPS):
                t0 = time.perf_counter()
                player_results = await asyncio.gather(
                    *[graph_like_burst(client) for _ in range(num_players)]
                )
                wall = time.perf_counter() - t0
                walls.append(wall)

            mean_wall = statistics.mean(walls)
            print(f"  {num_players} player(s): wall={mean_wall*1000:.0f}ms  "
                  f"per_player={mean_wall/num_players*1000:.0f}ms")


if __name__ == "__main__":
    asyncio.run(main())
