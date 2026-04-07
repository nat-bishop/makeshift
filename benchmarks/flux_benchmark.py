"""Benchmark FLUX image generation: 9B vs 4B at 512x512 and 256x256."""

import httpx
import statistics
import time
import sys

URL = "http://127.0.0.1:5100/v1/images/generations"
TIMEOUT = 180.0  # generous for cold starts / warmup
STEPS = 4
GUIDANCE = 1.0
ROUNDS = 3

PROMPTS = [
    "a glowing fire sword",
    "a wooden treasure chest",
    "a bouncy rubber ball",
    "a glass potion bottle",
    "a stone castle tower",
    "a metal robot",
    "an ice crystal",
    "a cloth flag",
    "a bone skeleton key",
    "a lava rock",
]


def generate(prompt: str, size: str) -> float:
    """Generate one image, return wall-clock seconds."""
    payload = {
        "model": "flux",
        "prompt": f"mixed media collage style paper cutout, side view, flat lighting, clean edges, {prompt}, single centered object, contrasting solid background color, no text",
        "n": 1,
        "size": size,
        "response_format": "b64_json",
        "num_inference_steps": STEPS,
        "guidance_scale": GUIDANCE,
    }
    t0 = time.perf_counter()
    r = httpx.post(URL, json=payload, timeout=TIMEOUT)
    elapsed = time.perf_counter() - t0
    r.raise_for_status()
    return elapsed


def run_round(size: str, round_num: int) -> list[float]:
    """Run all prompts at a given size, return list of times."""
    times = []
    for i, prompt in enumerate(PROMPTS):
        t = generate(prompt, size)
        times.append(t)
        print(f"  [{round_num}] {i+1:2d}/10  {t:6.2f}s  {prompt}")
    return times


def stats_line(label: str, times: list[float]) -> str:
    return (
        f"  {label:<12s}  "
        f"mean={statistics.mean(times):5.2f}s  "
        f"median={statistics.median(times):5.2f}s  "
        f"min={min(times):5.2f}s  "
        f"max={max(times):5.2f}s  "
        f"stdev={statistics.stdev(times):5.2f}s"
    )


def benchmark_resolution(size: str) -> dict:
    """Run ROUNDS rounds at a given resolution, print per-round and overall stats."""
    print(f"\n{'='*60}")
    print(f"  Resolution: {size}")
    print(f"{'='*60}")

    all_times = []
    round_times = []

    for r in range(1, ROUNDS + 1):
        print(f"\n  --- Round {r}/{ROUNDS} ---")
        times = run_round(size, r)
        round_times.append(times)
        all_times.extend(times)
        print(stats_line(f"Round {r}", times))

    print(f"\n  --- Summary ({size}) ---")
    print(stats_line("All rounds", all_times))

    # Show cold start effect: first image of round 1 vs rest
    first_image = round_times[0][0]
    rest = [t for rnd in round_times for j, t in enumerate(rnd) if not (rnd is round_times[0] and j == 0)]
    print(f"  First image (cold): {first_image:.2f}s  |  Rest mean: {statistics.mean(rest):.2f}s")

    # Per-round means to show warmup trend
    for r, times in enumerate(round_times, 1):
        print(f"  Round {r} mean: {statistics.mean(times):.2f}s")

    return {"all": all_times, "rounds": round_times}


def wait_healthy(max_wait: int = 600):
    """Wait for SGLang health endpoint."""
    print("  Waiting for SGLang to be healthy...", end="", flush=True)
    t0 = time.time()
    while time.time() - t0 < max_wait:
        try:
            r = httpx.get("http://127.0.0.1:5100/health", timeout=5)
            if r.status_code == 200:
                print(f" ready ({time.time()-t0:.0f}s)")
                return True
        except (httpx.ConnectError, httpx.ReadTimeout):
            pass
        time.sleep(5)
        print(".", end="", flush=True)
    print(" TIMEOUT")
    return False


def main():
    model_label = sys.argv[1] if len(sys.argv) > 1 else "unknown"

    print(f"\n{'#'*60}")
    print(f"  FLUX Benchmark — Model: {model_label}")
    print(f"  {ROUNDS} rounds × {len(PROMPTS)} prompts × 2 resolutions")
    print(f"  Steps: {STEPS}, Guidance: {GUIDANCE}")
    print(f"{'#'*60}")

    if not wait_healthy(30):
        print("ERROR: SGLang not reachable on port 5100")
        sys.exit(1)

    results = {}
    for size in ["512x512", "256x256"]:
        results[size] = benchmark_resolution(size)

    # Final comparison table
    print(f"\n{'='*60}")
    print(f"  FINAL RESULTS — {model_label}")
    print(f"{'='*60}")
    print(f"  {'Resolution':<12s}  {'Mean':>7s}  {'Median':>7s}  {'Min':>7s}  {'Max':>7s}  {'Stdev':>7s}")
    print(f"  {'-'*55}")
    for size in ["512x512", "256x256"]:
        t = results[size]["all"]
        print(
            f"  {size:<12s}  {statistics.mean(t):6.2f}s  {statistics.median(t):6.2f}s  "
            f"{min(t):6.2f}s  {max(t):6.2f}s  {statistics.stdev(t):6.2f}s"
        )


if __name__ == "__main__":
    main()
