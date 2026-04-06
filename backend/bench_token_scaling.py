"""Benchmark: how does latency scale with output token count?

Measures the per-token decode cost on top of the ~58ms base.

Usage:
    cd backend && uv run python bench_token_scaling.py
"""

from __future__ import annotations

import asyncio
import statistics
import time

import httpx

BASE_URL = "http://127.0.0.1:5200/v1"
MODEL = "Qwen/Qwen3.5-35B-A3B-FP8"
EXTRA_BODY = {"chat_template_kwargs": {"enable_thinking": False}}

# We force exact token counts by asking the model to count
# and setting max_tokens as the cap
TOKEN_TARGETS = [1, 2, 3, 5, 10, 15, 20, 25, 50, 75, 100]


async def chat(client: httpx.AsyncClient, max_tokens: int) -> dict:
    body = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "messages": [
            {"role": "system", "content": f"Count from 1 to {max_tokens * 2}. Write one number per word. Nothing else."},
            {"role": "user", "content": "Go."},
        ],
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
        "completion_tokens": usage.get("completion_tokens", 0),
    }


async def main():
    async with httpx.AsyncClient(timeout=30) as client:
        # Warmup
        print("Warming up...")
        for _ in range(10):
            await chat(client, 5)

        print(f"\n{'='*60}")
        print(f"OUTPUT TOKEN SCALING (20 reps each)")
        print(f"{'='*60}")
        print(f"  {'Target':>6s} | {'Actual':>6s} | {'Mean':>7s} | {'Median':>7s} | {'Min':>7s} | {'ms/tok':>6s}")
        print(f"  {'-'*6}-+-{'-'*6}-+-{'-'*7}-+-{'-'*7}-+-{'-'*7}-+-{'-'*6}")

        results = []
        for target in TOKEN_TARGETS:
            times = []
            actual_tokens = []
            for _ in range(20):
                r = await chat(client, target)
                times.append(r["elapsed"])
                actual_tokens.append(r["completion_tokens"])

            mean_ms = statistics.mean(times) * 1000
            median_ms = statistics.median(times) * 1000
            min_ms = min(times) * 1000
            avg_tokens = statistics.mean(actual_tokens)
            ms_per_tok = mean_ms / avg_tokens if avg_tokens > 0 else 0

            results.append((target, avg_tokens, mean_ms, median_ms, min_ms, ms_per_tok))
            print(f"  {target:6d} | {avg_tokens:5.1f} | {mean_ms:6.1f}ms | {median_ms:6.1f}ms | {min_ms:6.1f}ms | {ms_per_tok:5.1f}")

        # Estimate base overhead and per-token cost via linear regression
        # y = base + per_token * x
        xs = [r[1] for r in results]  # actual tokens
        ys = [r[2] for r in results]  # mean ms
        n = len(xs)
        x_mean = sum(xs) / n
        y_mean = sum(ys) / n
        num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
        den = sum((x - x_mean) ** 2 for x in xs)
        per_token = num / den if den > 0 else 0
        base = y_mean - per_token * x_mean

        print(f"\n{'='*60}")
        print(f"LINEAR FIT: latency = {base:.1f}ms + {per_token:.2f}ms * output_tokens")
        print(f"{'='*60}")
        print(f"  Base overhead (0 tokens): ~{base:.0f}ms")
        print(f"  Per output token:         ~{per_token:.1f}ms")
        print(f"  Decode speed:             ~{1000/per_token:.0f} tokens/sec")
        print()
        print(f"  Estimated latencies:")
        for n_tok in [1, 5, 10, 25, 50, 100, 150]:
            est = base + per_token * n_tok
            print(f"    {n_tok:4d} tokens -> {est:6.0f}ms")


if __name__ == "__main__":
    asyncio.run(main())
