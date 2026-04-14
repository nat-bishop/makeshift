"""Benchmark FLUX.2 Klein at 256/512/1024 across 10 character-with-sword prompts.

Generates 30 sprites total (sequential), times each call, writes a JSON manifest
and an HTML dashboard for visual + timing comparison.

Usage:
    uv run python -m scripts.bench_character_resolutions
"""

from __future__ import annotations

import asyncio
import base64
import json
import statistics
import time
from pathlib import Path

import httpx

URL = "http://127.0.0.1:5100/v1/images/generations"
MODEL = "black-forest-labs/FLUX.2-klein-4B"
SIZES = [256, 512, 1024]

OUT_DIR = Path(__file__).resolve().parent.parent / "sprite_comparison" / "char_resolutions"

CHARACTERS: list[tuple[str, str]] = [
    ("knight", "a knight in plate armor wielding a longsword"),
    ("samurai", "a samurai warrior in red lacquered armor holding a katana"),
    ("wizard", "an old wizard in a star-patterned robe holding a glowing enchanted sword"),
    ("viking", "a viking berserker with fur cloak and braided beard wielding a heavy broadsword"),
    ("pirate", "a pirate captain with tricorn hat and red coat brandishing a curved cutlass"),
    ("ninja", "a ninja in dark blue garb holding a short straight ninjato blade"),
    ("gladiator", "a roman gladiator with crested helm and round shield holding a short gladius"),
    ("dark_elf", "a dark elf rogue with white hair and black leather wielding a curved scimitar"),
    ("paladin", "a paladin in golden armor with a blue tabard holding a massive two-handed greatsword"),
    ("musketeer", "a swashbuckling musketeer in feathered hat and blue cape thrusting a thin rapier"),
]


def build_prompt(name: str, desc: str) -> str:
    return (
        f"A mixed media collage of {name} made from cut paper, magazine clippings, "
        f"and cardboard, held together with visible scotch tape and glue. "
        f"{desc}. "
        f"Side view, single centered character on a solid contrasting background. "
        f"Flat lighting, clean edges, no text."
    )


async def generate(client: httpx.AsyncClient, prompt: str, size: int) -> tuple[bytes, float]:
    t0 = time.monotonic()
    resp = await client.post(
        URL,
        json={
            "model": MODEL,
            "prompt": prompt,
            "n": 1,
            "size": f"{size}x{size}",
            "response_format": "b64_json",
            "num_inference_steps": 4,
            "guidance_scale": 1.0,
        },
    )
    elapsed = time.monotonic() - t0
    resp.raise_for_status()
    data = base64.b64decode(resp.json()["data"][0]["b64_json"])
    return data, elapsed


async def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output dir: {OUT_DIR}")

    results: list[dict] = []

    async with httpx.AsyncClient(timeout=600.0) as client:
        # Warmup at 512 to avoid cold-start skewing the first measurement.
        print("Warmup @ 512x512 ...", end=" ", flush=True)
        _, warmup_elapsed = await generate(client, build_prompt("warmup", "a plain stone"), 512)
        print(f"{warmup_elapsed:.2f}s")

        total_t0 = time.monotonic()
        for cname, cdesc in CHARACTERS:
            prompt = build_prompt(cname, cdesc)
            for size in SIZES:
                print(f"  {cname:10s} @ {size:4d}...", end=" ", flush=True)
                data, elapsed = await generate(client, prompt, size)
                fname = f"{cname}_{size}.png"
                (OUT_DIR / fname).write_bytes(data)
                print(f"{elapsed:5.2f}s  ({len(data):>8,} bytes)")
                results.append(
                    {
                        "character": cname,
                        "description": cdesc,
                        "size": size,
                        "filename": fname,
                        "elapsed": elapsed,
                        "bytes": len(data),
                    }
                )
        total_elapsed = time.monotonic() - total_t0

    (OUT_DIR / "results.json").write_text(json.dumps(results, indent=2))

    # Summary stats
    print("\n--- Timing summary ---")
    summary: dict[int, dict[str, float]] = {}
    for size in SIZES:
        times = [r["elapsed"] for r in results if r["size"] == size]
        summary[size] = {
            "mean": statistics.mean(times),
            "median": statistics.median(times),
            "min": min(times),
            "max": max(times),
            "stdev": statistics.stdev(times) if len(times) > 1 else 0.0,
        }
        s = summary[size]
        print(
            f"  {size:4d}x{size:<4d}  mean={s['mean']:.2f}s  med={s['median']:.2f}s  "
            f"min={s['min']:.2f}s  max={s['max']:.2f}s  stdev={s['stdev']:.2f}s"
        )
    print(f"  total wall time (excl warmup): {total_elapsed:.2f}s")

    html = build_dashboard(results, summary, total_elapsed, warmup_elapsed)
    dashboard_path = OUT_DIR / "dashboard.html"
    dashboard_path.write_text(html, encoding="utf-8")
    print(f"\nDashboard: {dashboard_path}")


def build_dashboard(
    results: list[dict],
    summary: dict[int, dict[str, float]],
    total_elapsed: float,
    warmup_elapsed: float,
) -> str:
    by_char: dict[str, dict[int, dict]] = {}
    for r in results:
        by_char.setdefault(r["character"], {})[r["size"]] = r

    summary_rows = "".join(
        f"<tr><td>{size}×{size}</td>"
        f"<td>{s['mean']:.2f}s</td>"
        f"<td>{s['median']:.2f}s</td>"
        f"<td>{s['min']:.2f}s</td>"
        f"<td>{s['max']:.2f}s</td>"
        f"<td>{s['stdev']:.2f}s</td></tr>"
        for size, s in summary.items()
    )

    grid_rows = ""
    for cname, by_size in by_char.items():
        cells = ""
        for size in SIZES:
            r = by_size.get(size)
            if not r:
                cells += "<td>—</td>"
                continue
            cells += (
                f'<td class="cell">'
                f'<img src="{r["filename"]}" alt="{cname} {size}">'
                f'<div class="meta">{size}×{size} · {r["elapsed"]:.2f}s · {r["bytes"] // 1024}KB</div>'
                f"</td>"
            )
        desc = next(d for c, d in CHARACTERS if c == cname)
        grid_rows += (
            f'<tr><th class="row-label"><div class="cname">{cname}</div>'
            f'<div class="cdesc">{desc}</div></th>{cells}</tr>'
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>FLUX.2 Klein resolution benchmark</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; background: #14161a; color: #e6e6e6;
         margin: 0; padding: 24px; }}
  h1 {{ margin: 0 0 4px 0; font-weight: 600; }}
  .sub {{ color: #888; margin-bottom: 24px; font-size: 14px; }}
  table {{ border-collapse: collapse; }}
  .summary {{ margin-bottom: 32px; }}
  .summary th, .summary td {{ padding: 6px 14px; text-align: left; border-bottom: 1px solid #2a2d33; }}
  .summary th {{ color: #888; font-weight: 500; font-size: 12px; text-transform: uppercase; }}
  .grid th, .grid td {{ padding: 8px; vertical-align: top; }}
  .grid thead th {{ color: #888; font-weight: 500; font-size: 13px; padding-bottom: 12px; }}
  .row-label {{ text-align: left; min-width: 180px; padding-right: 16px; }}
  .cname {{ font-weight: 600; }}
  .cdesc {{ font-size: 11px; color: #888; max-width: 200px; }}
  .cell {{ background: #1c1f25; border-radius: 8px; }}
  .cell img {{ display: block; width: 256px; height: 256px; object-fit: contain;
               background: #0a0b0e; border-radius: 6px; }}
  .meta {{ font-size: 11px; color: #aaa; padding-top: 6px; font-family: ui-monospace, monospace; }}
</style>
</head>
<body>
  <h1>FLUX.2 Klein — resolution benchmark</h1>
  <div class="sub">10 characters × 3 resolutions = 30 sprites · sequential · warmup {warmup_elapsed:.2f}s · total {total_elapsed:.2f}s</div>

  <table class="summary">
    <thead><tr><th>resolution</th><th>mean</th><th>median</th><th>min</th><th>max</th><th>stdev</th></tr></thead>
    <tbody>{summary_rows}</tbody>
  </table>

  <table class="grid">
    <thead><tr><th></th><th>256×256</th><th>512×512</th><th>1024×1024</th></tr></thead>
    <tbody>{grid_rows}</tbody>
  </table>
</body>
</html>"""


if __name__ == "__main__":
    asyncio.run(main())
