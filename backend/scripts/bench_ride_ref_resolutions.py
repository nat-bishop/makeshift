"""Benchmark the carry/ride img2img edit pipeline across reference image resolutions.

For each mount: generate the mount sprite (real pipeline), call the ride LLM
instruction once, then run the FLUX.2 Klein edit pipeline at three reference
image sizes — 256 (current game default), 512, 1024.

Uses the real game functions so output reflects production behavior.

Usage:
    uv run python -m scripts.bench_ride_ref_resolutions
"""

from __future__ import annotations

import asyncio
import io
import json
import statistics
import time
from pathlib import Path

from PIL import Image

from app.creator.llm import ask_text
from app.images.pipeline import (
    _IMG2IMG_MAX_TOKENS,
    generate_edited_sprite,
    generate_static_sprite,
    get_player_sprite,
)
from app.prompts.image import (
    IMG2IMG_STYLE,
    IMG2IMG_SUFFIX_SCENE,
    RIDE_INSTRUCTION,
    build_text_to_image_prompt,
)

OUT_DIR = Path(__file__).resolve().parent.parent / "sprite_comparison" / "ride_ref_resolutions"
REF_SIZES = [256, 512, 1024]

MOUNTS: list[tuple[str, str]] = [
    ("horse", "a brown horse with a flowing mane and saddle"),
    ("dragon", "a small green wyrm dragon with leathery wings and spiked tail"),
    ("ostrich", "a large speckled racing ostrich with long pink legs"),
    ("giant_spider", "a huge furry tarantula with eight thick legs and red eyes"),
    ("griffin", "a majestic golden griffin with eagle head and lion body"),
]


def prepare_reference_at_size(sprite_bytes: bytes, ref_size: int) -> bytes:
    """Resize a 512 RGBA sprite to ref_size on a white background (PNG bytes)."""
    img = Image.open(io.BytesIO(sprite_bytes)).convert("RGBA")
    img = img.resize((ref_size, ref_size), Image.Resampling.LANCZOS)
    bg = Image.new("RGBA", (ref_size, ref_size), (255, 255, 255, 255))
    bg.paste(img, (0, 0), img)
    buf = io.BytesIO()
    bg.save(buf, format="PNG")
    return buf.getvalue()


async def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output dir: {OUT_DIR}")

    # ── Step 1: Generate mount sprites (the real t2i pipeline w/ bg removal) ──
    print("\n[1/3] Generating mount sprites at 512 (real pipeline)...")
    mounts: list[dict] = []
    for mname, mdesc in MOUNTS:
        prompt = build_text_to_image_prompt(mname, mdesc)
        t0 = time.monotonic()
        sprite_bytes = await generate_static_sprite(prompt)
        elapsed = time.monotonic() - t0
        path = OUT_DIR / f"mount_{mname}.png"
        path.write_bytes(sprite_bytes)
        mounts.append(
            {
                "name": mname,
                "desc": mdesc,
                "sprite_bytes": sprite_bytes,
                "gen_elapsed": elapsed,
            }
        )
        print(f"  {mname:14s} {elapsed:5.2f}s ({len(sprite_bytes):,} bytes)")

    # ── Step 2: Run the LLM ride instruction once per mount ──
    print("\n[2/3] Calling LLM ride instruction once per mount...")
    for m in mounts:
        user_prompt = (
            f"Character: player\n"
            f"Mount: {m['name']} — {m['desc']}\n"
            f"Describe the player riding the mount:"
        )
        t0 = time.monotonic()
        llm_desc = await ask_text(
            user_prompt,
            max_tokens=_IMG2IMG_MAX_TOKENS,
            instructions=RIDE_INSTRUCTION,
        )
        m["llm_desc"] = llm_desc
        m["llm_elapsed"] = time.monotonic() - t0
        m["full_prompt"] = f"{IMG2IMG_STYLE}, {llm_desc}, {IMG2IMG_SUFFIX_SCENE}"
        print(f"  {m['name']:14s} ({m['llm_elapsed']:.2f}s) -> {llm_desc}")

    # ── Step 3: Edit pipeline at each ref size for every mount ──
    print(f"\n[3/3] Running edit pipeline at refs {REF_SIZES} for each mount...")
    char_refs = {size: prepare_reference_at_size(get_player_sprite(), size) for size in REF_SIZES}

    edit_results: list[dict] = []
    edit_total_t0 = time.monotonic()
    for m in mounts:
        for ref_size in REF_SIZES:
            mount_ref = prepare_reference_at_size(m["sprite_bytes"], ref_size)
            t0 = time.monotonic()
            output_bytes = await generate_edited_sprite(
                m["full_prompt"],
                [("character.png", char_refs[ref_size]), ("mount.png", mount_ref)],
            )
            elapsed = time.monotonic() - t0
            fname = f"ride_{m['name']}_ref{ref_size}.png"
            (OUT_DIR / fname).write_bytes(output_bytes)
            edit_results.append(
                {
                    "mount": m["name"],
                    "ref_size": ref_size,
                    "elapsed": elapsed,
                    "filename": fname,
                    "bytes": len(output_bytes),
                }
            )
            print(
                f"  {m['name']:14s} ref={ref_size:4d}  {elapsed:5.2f}s "
                f"({len(output_bytes):,} bytes)"
            )
    edit_total = time.monotonic() - edit_total_t0

    # ── Summary ──
    print("\n--- Edit timing per ref size ---")
    summary: dict[int, dict[str, float]] = {}
    for ref_size in REF_SIZES:
        times = [r["elapsed"] for r in edit_results if r["ref_size"] == ref_size]
        summary[ref_size] = {
            "mean": statistics.mean(times),
            "median": statistics.median(times),
            "min": min(times),
            "max": max(times),
            "stdev": statistics.stdev(times) if len(times) > 1 else 0.0,
        }
        s = summary[ref_size]
        print(
            f"  ref={ref_size:4d}  mean={s['mean']:.2f}s  med={s['median']:.2f}s  "
            f"min={s['min']:.2f}s  max={s['max']:.2f}s  stdev={s['stdev']:.2f}s"
        )
    print(f"  total edit wall time: {edit_total:.2f}s")

    # Save manifest
    manifest = {
        "mounts": [
            {k: v for k, v in m.items() if k != "sprite_bytes"} for m in mounts
        ],
        "edits": edit_results,
        "summary": summary,
        "total_edit_elapsed": edit_total,
    }
    (OUT_DIR / "results.json").write_text(json.dumps(manifest, indent=2, default=str))

    html = build_dashboard(mounts, edit_results, summary, edit_total)
    dashboard_path = OUT_DIR / "dashboard.html"
    dashboard_path.write_text(html, encoding="utf-8")
    print(f"\nDashboard: {dashboard_path}")


def build_dashboard(
    mounts: list[dict],
    edit_results: list[dict],
    summary: dict[int, dict[str, float]],
    edit_total: float,
) -> str:
    by_mount: dict[str, dict[int, dict]] = {}
    for r in edit_results:
        by_mount.setdefault(r["mount"], {})[r["ref_size"]] = r

    summary_rows = "".join(
        f"<tr><td>ref {size}×{size}</td>"
        f"<td>{s['mean']:.2f}s</td>"
        f"<td>{s['median']:.2f}s</td>"
        f"<td>{s['min']:.2f}s</td>"
        f"<td>{s['max']:.2f}s</td>"
        f"<td>{s['stdev']:.2f}s</td></tr>"
        for size, s in summary.items()
    )

    grid_rows = ""
    for m in mounts:
        cells = ""
        # Mount sprite cell
        cells += (
            f'<td class="cell mount-cell">'
            f'<img src="mount_{m["name"]}.png" alt="{m["name"]}">'
            f'<div class="meta">mount sprite · {m["gen_elapsed"]:.2f}s</div>'
            f"</td>"
        )
        for ref_size in REF_SIZES:
            r = by_mount.get(m["name"], {}).get(ref_size)
            if not r:
                cells += "<td>—</td>"
                continue
            current_marker = ' <span class="badge">game default</span>' if ref_size == 256 else ""
            cells += (
                f'<td class="cell">'
                f'<img src="{r["filename"]}" alt="{m["name"]} ref{ref_size}">'
                f'<div class="meta">ref {ref_size}×{ref_size} · '
                f'{r["elapsed"]:.2f}s · {r["bytes"] // 1024}KB{current_marker}</div>'
                f"</td>"
            )
        grid_rows += (
            f'<tr><th class="row-label"><div class="cname">{m["name"]}</div>'
            f'<div class="cdesc">{m["desc"]}</div>'
            f'<div class="llm-desc">LLM: {m["llm_desc"]}</div></th>{cells}</tr>'
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>FLUX.2 Klein — ride pipeline reference resolution test</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; background: #14161a; color: #e6e6e6;
         margin: 0; padding: 24px; }}
  h1 {{ margin: 0 0 4px 0; font-weight: 600; }}
  .sub {{ color: #888; margin-bottom: 6px; font-size: 14px; }}
  .note {{ color: #888; margin-bottom: 24px; font-size: 13px; max-width: 900px; line-height: 1.5; }}
  table {{ border-collapse: collapse; }}
  .summary {{ margin-bottom: 32px; }}
  .summary th, .summary td {{ padding: 6px 14px; text-align: left; border-bottom: 1px solid #2a2d33; }}
  .summary th {{ color: #888; font-weight: 500; font-size: 12px; text-transform: uppercase; }}
  .grid th, .grid td {{ padding: 8px; vertical-align: top; }}
  .grid thead th {{ color: #888; font-weight: 500; font-size: 13px; padding-bottom: 12px; }}
  .row-label {{ text-align: left; min-width: 240px; max-width: 240px; padding-right: 16px; }}
  .cname {{ font-weight: 600; font-size: 14px; }}
  .cdesc {{ font-size: 11px; color: #888; margin-top: 2px; }}
  .llm-desc {{ font-size: 11px; color: #6aa9d4; margin-top: 8px; line-height: 1.4;
               border-left: 2px solid #2a4d6a; padding-left: 8px; }}
  .cell {{ background: #1c1f25; border-radius: 8px; }}
  .mount-cell {{ background: #21181c; }}
  .cell img {{ display: block; width: 220px; height: 220px; object-fit: contain;
               background: #0a0b0e; border-radius: 6px; }}
  .meta {{ font-size: 11px; color: #aaa; padding-top: 6px; font-family: ui-monospace, monospace; }}
  .badge {{ background: #2a4d6a; color: #cfe6f7; padding: 1px 5px; border-radius: 3px; font-size: 9px; }}
</style>
</head>
<body>
  <h1>FLUX.2 Klein — ride pipeline reference resolution test</h1>
  <div class="sub">5 mounts × 3 reference sizes · real game pipeline (LLM + img2img edits + bg removal)</div>
  <div class="note">
    Each row uses the same LLM-generated ride description and the same player reference,
    but the player+mount reference images are resized to 256, 512, or 1024 before being
    sent to <code>/v1/images/edits</code>. Output size is fixed at 512×512.
    The 256 column is what the game actually does today (<code>REFERENCE_SIZE</code> in <code>pipeline.py</code>).
    Total edit wall time: {edit_total:.2f}s.
  </div>

  <table class="summary">
    <thead><tr><th>resolution</th><th>mean</th><th>median</th><th>min</th><th>max</th><th>stdev</th></tr></thead>
    <tbody>{summary_rows}</tbody>
  </table>

  <table class="grid">
    <thead><tr><th></th><th>mount sprite (input)</th><th>ride @ ref 256</th><th>ride @ ref 512</th><th>ride @ ref 1024</th></tr></thead>
    <tbody>{grid_rows}</tbody>
  </table>
</body>
</html>"""


if __name__ == "__main__":
    asyncio.run(main())
