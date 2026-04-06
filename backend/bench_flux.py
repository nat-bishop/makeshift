"""Benchmark: FLUX image generation latency.

Tests the local FLUX server at port 5100 for sprite generation speed.

Usage:
    cd backend && uv run python bench_flux.py
"""

from __future__ import annotations

import base64
import statistics
import sys
import time

import httpx

FLUX_URL = "http://127.0.0.1:5100"
FLUX_MODEL = "black-forest-labs/FLUX.2-klein-9B"

# Sprite-style prompts matching what the creator pipeline generates
PROMPTS = [
    "a gleaming steel blade wreathed in dancing orange flames, game sprite, white background",
    "a glossy black spider dripping green acid from its fangs, game sprite, white background",
    "a yellow rubber duck with an orange beak, game sprite, white background",
    "a crackling campfire with orange flames dancing over charred logs, game sprite, white background",
    "a rough gray boulder with moss patches, game sprite, white background",
    "a stalwart knight in dented silver armor with a red plume, game sprite, white background",
]


def main():
    client = httpx.Client(timeout=120)

    # Check server
    print(f"Connecting to {FLUX_URL} ...")
    try:
        resp = client.get(f"{FLUX_URL}/v1/models")
        if resp.status_code == 200:
            models = resp.json()
            print(f"Server OK. Models: {[m['id'] for m in models.get('data', [])]}")
        else:
            # Try SGLang native endpoint
            resp = client.get(f"{FLUX_URL}/get_model_info")
            print(f"Server OK. Info: {resp.json()}")
    except Exception as e:
        print(f"ERROR: Cannot reach FLUX at {FLUX_URL}: {e}")
        sys.exit(1)

    # Figure out the right endpoint - SGLang image gen uses /v1/images/generations
    print("\nChecking available endpoints...")

    # Warmup
    print(f"\n{'='*60}")
    print("WARMUP (2 generations)")
    print(f"{'='*60}")
    for i in range(2):
        body = {
            "model": FLUX_MODEL,
            "prompt": "a red circle, white background",
            "n": 1,
            "size": "512x512",
        }
        t0 = time.perf_counter()
        resp = client.post(f"{FLUX_URL}/v1/images/generations", json=body)
        elapsed = time.perf_counter() - t0
        if resp.status_code != 200:
            print(f"  ERROR {resp.status_code}: {resp.text[:200]}")
            # Try alternate endpoints
            for endpoint in ["/generate", "/v1/images/generate"]:
                resp2 = client.post(f"{FLUX_URL}{endpoint}", json=body)
                if resp2.status_code == 200:
                    print(f"  Found working endpoint: {endpoint}")
                    break
            else:
                print("  Could not find working image gen endpoint")
                sys.exit(1)
        else:
            data = resp.json()
            has_image = bool(data.get("data", [{}])[0].get("b64_json") or
                           data.get("data", [{}])[0].get("url"))
            print(f"  warmup {i+1}: {elapsed:.2f}s (got image: {has_image})")

    # Benchmark different sizes
    print(f"\n{'='*60}")
    print("SIZE SCALING")
    print(f"{'='*60}")
    for size in ["256x256", "512x512", "768x768", "1024x1024"]:
        times = []
        for _ in range(3):
            body = {
                "model": FLUX_MODEL,
                "prompt": "a red sword with flames, game sprite, white background",
                "n": 1,
                "size": size,
            }
            t0 = time.perf_counter()
            resp = client.post(f"{FLUX_URL}/v1/images/generations", json=body)
            elapsed = time.perf_counter() - t0
            if resp.status_code == 200:
                times.append(elapsed)
            else:
                print(f"  {size}: ERROR {resp.status_code}")
                break
        if times:
            print(f"  {size}: mean={statistics.mean(times):.2f}s  "
                  f"min={min(times):.2f}s  max={max(times):.2f}s")

    # Benchmark with sprite prompts
    print(f"\n{'='*60}")
    print(f"SPRITE GENERATION (512x512, {len(PROMPTS)} prompts, 3 reps)")
    print(f"{'='*60}")
    all_times = []
    for prompt in PROMPTS:
        times = []
        for _ in range(3):
            body = {
                "model": FLUX_MODEL,
                "prompt": prompt,
                "n": 1,
                "size": "512x512",
            }
            t0 = time.perf_counter()
            resp = client.post(f"{FLUX_URL}/v1/images/generations", json=body)
            elapsed = time.perf_counter() - t0
            if resp.status_code == 200:
                times.append(elapsed)
                all_times.append(elapsed)
        if times:
            short_prompt = prompt[:50] + "..." if len(prompt) > 50 else prompt
            print(f"  {short_prompt:55s} {statistics.mean(times):.2f}s")

    # Concurrent generation
    print(f"\n{'='*60}")
    print("CONCURRENT GENERATION (512x512)")
    print(f"{'='*60}")

    import asyncio

    async def gen_async(aclient: httpx.AsyncClient, prompt: str) -> float:
        body = {
            "model": FLUX_MODEL,
            "prompt": prompt,
            "n": 1,
            "size": "512x512",
        }
        t0 = time.perf_counter()
        resp = await aclient.post(f"{FLUX_URL}/v1/images/generations", json=body)
        return time.perf_counter() - t0

    async def test_concurrent():
        async with httpx.AsyncClient(timeout=120) as aclient:
            for n in [1, 2, 3, 4]:
                walls = []
                for _ in range(3):
                    prompts_batch = PROMPTS[:n]
                    t0 = time.perf_counter()
                    results = await asyncio.gather(
                        *[gen_async(aclient, p) for p in prompts_batch]
                    )
                    wall = time.perf_counter() - t0
                    walls.append(wall)
                mean_wall = statistics.mean(walls)
                print(f"  {n} concurrent: wall={mean_wall:.2f}s  "
                      f"per_image={mean_wall/n:.2f}s  "
                      f"throughput={n/mean_wall:.2f} img/s")

    asyncio.run(test_concurrent())

    # Summary
    if all_times:
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        print(f"  Single 512x512 sprite: mean={statistics.mean(all_times):.2f}s  "
              f"min={min(all_times):.2f}s")
        print(f"  This runs in background after object creation (not blocking gameplay)")

    client.close()


if __name__ == "__main__":
    main()
