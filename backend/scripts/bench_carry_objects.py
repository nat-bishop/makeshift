"""Benchmark the carry img2img edit pipeline on a wide set of carryable objects.

Single reference resolution (512x512). Uses real game functions: t2i + bg removal
for the object sprite, then the LLM carry instruction, then the edit pipeline.

Usage:
    uv run python -m scripts.bench_carry_objects
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
    CARRY_INSTRUCTION,
    IMG2IMG_STYLE,
    IMG2IMG_SUFFIX_SCENE,
    build_text_to_image_prompt,
)

OUT_DIR = Path(__file__).resolve().parent.parent / "sprite_comparison" / "carry_objects"
REF_SIZE = 512  # override the game default (256) for this experiment

OBJECTS: list[tuple[str, str]] = [
    ("longsword", "a steel longsword with a leather-wrapped grip and crossguard"),
    ("torch", "a wooden torch with bright orange flames at the tip"),
    ("lantern", "a brass lantern with a glowing yellow flame inside glass panes"),
    ("fish", "a large silver fish with iridescent scales"),
    ("log", "a thick wooden log with bark and sawn ends"),
    ("basket", "a woven wicker basket full of red apples"),
    ("crystal", "a huge glowing purple crystal shard"),
    ("treasure_chest", "a small wooden treasure chest with brass fittings overflowing with gold coins"),
    ("scroll", "an ornate rolled parchment scroll tied with red ribbon"),
    ("axe", "a heavy double-bladed iron woodcutter's axe with a wooden haft"),
    ("watermelon", "a huge round green watermelon with dark stripes"),
    ("ice_block", "a large pale blue block of frozen ice"),
    ("anvil", "a heavy black iron blacksmith's anvil"),
    ("skull", "a bleached white animal skull with curling horns"),
    ("bouquet", "a colorful bouquet of pink and yellow wildflowers wrapped in paper"),
]


def prepare_reference_at_size(sprite_bytes: bytes, ref_size: int) -> bytes:
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
    print(f"Reference size: {REF_SIZE} (game default is 256)")

    # ── Step 1: Generate object sprites via the real t2i pipeline ──
    print(f"\n[1/3] Generating {len(OBJECTS)} object sprites at 512 (real pipeline)...")
    objects: list[dict] = []
    t_step1 = time.monotonic()
    for oname, odesc in OBJECTS:
        prompt = build_text_to_image_prompt(oname, odesc)
        t0 = time.monotonic()
        sprite_bytes = await generate_static_sprite(prompt)
        elapsed = time.monotonic() - t0
        path = OUT_DIR / f"object_{oname}.png"
        path.write_bytes(sprite_bytes)
        objects.append(
            {
                "name": oname,
                "desc": odesc,
                "sprite_bytes": sprite_bytes,
                "gen_elapsed": elapsed,
            }
        )
        print(f"  {oname:16s} {elapsed:5.2f}s ({len(sprite_bytes):,} bytes)")
    print(f"  step1 total: {time.monotonic() - t_step1:.2f}s")

    # ── Step 2: LLM carry description per object ──
    print(f"\n[2/3] Calling LLM carry instruction for each object...")
    t_step2 = time.monotonic()
    for o in objects:
        user_prompt = (
            f"Character: player\n"
            f"Object: {o['name']} - {o['desc']}\n"
            f"Describe the player carrying the object:"
        )
        t0 = time.monotonic()
        llm_desc = await ask_text(
            user_prompt,
            max_tokens=_IMG2IMG_MAX_TOKENS,
            instructions=CARRY_INSTRUCTION,
        )
        o["llm_desc"] = llm_desc
        o["llm_elapsed"] = time.monotonic() - t0
        o["full_prompt"] = f"{IMG2IMG_STYLE}, {llm_desc}, {IMG2IMG_SUFFIX_SCENE}"
        print(f"  {o['name']:16s} ({o['llm_elapsed']:.2f}s) -> {llm_desc}")
    print(f"  step2 total: {time.monotonic() - t_step2:.2f}s")

    # ── Step 3: Edit pipeline at REF_SIZE ──
    print(f"\n[3/3] Running carry edit pipeline at ref={REF_SIZE} for each object...")
    char_ref = prepare_reference_at_size(get_player_sprite(), REF_SIZE)
    t_step3 = time.monotonic()
    edit_results: list[dict] = []
    for o in objects:
        obj_ref = prepare_reference_at_size(o["sprite_bytes"], REF_SIZE)
        t0 = time.monotonic()
        output_bytes = await generate_edited_sprite(
            o["full_prompt"],
            [("character.png", char_ref), ("object.png", obj_ref)],
        )
        elapsed = time.monotonic() - t0
        fname = f"carry_{o['name']}.png"
        (OUT_DIR / fname).write_bytes(output_bytes)
        edit_results.append(
            {
                "object": o["name"],
                "elapsed": elapsed,
                "filename": fname,
                "bytes": len(output_bytes),
            }
        )
        print(f"  {o['name']:16s} {elapsed:5.2f}s ({len(output_bytes):,} bytes)")
    edit_total = time.monotonic() - t_step3

    # ── Summary ──
    edit_times = [r["elapsed"] for r in edit_results]
    print("\n--- Edit timing summary ---")
    print(f"  mean   = {statistics.mean(edit_times):.2f}s")
    print(f"  median = {statistics.median(edit_times):.2f}s")
    print(f"  min    = {min(edit_times):.2f}s")
    print(f"  max    = {max(edit_times):.2f}s")
    print(f"  stdev  = {statistics.stdev(edit_times):.2f}s")
    print(f"  total  = {edit_total:.2f}s")

    manifest = {
        "ref_size": REF_SIZE,
        "objects": [{k: v for k, v in o.items() if k != "sprite_bytes"} for o in objects],
        "edits": edit_results,
        "edit_total_elapsed": edit_total,
    }
    (OUT_DIR / "results.json").write_text(json.dumps(manifest, indent=2, default=str))

    html = build_dashboard(objects, edit_results, edit_total)
    dashboard_path = OUT_DIR / "dashboard.html"
    dashboard_path.write_text(html, encoding="utf-8")
    print(f"\nDashboard: {dashboard_path}")


def build_dashboard(
    objects: list[dict],
    edit_results: list[dict],
    edit_total: float,
) -> str:
    by_obj = {r["object"]: r for r in edit_results}
    edit_times = [r["elapsed"] for r in edit_results]
    mean_edit = statistics.mean(edit_times)
    median_edit = statistics.median(edit_times)

    cards = ""
    for o in objects:
        r = by_obj.get(o["name"])
        if not r:
            continue
        cards += f"""
        <div class="card">
          <div class="card-header">
            <div class="oname">{o["name"]}</div>
            <div class="odesc">{o["desc"]}</div>
          </div>
          <div class="img-row">
            <div class="img-cell">
              <img src="object_{o["name"]}.png" alt="{o["name"]}">
              <div class="img-label">object input</div>
              <div class="img-meta">{o["gen_elapsed"]:.2f}s · t2i</div>
            </div>
            <div class="arrow">+ player &rarr;</div>
            <div class="img-cell">
              <img src="{r["filename"]}" alt="carrying {o["name"]}">
              <div class="img-label">carry result</div>
              <div class="img-meta">{r["elapsed"]:.2f}s · edit · {r["bytes"] // 1024}KB</div>
            </div>
          </div>
          <div class="llm-desc">LLM: {o["llm_desc"]}</div>
        </div>
        """

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>FLUX.2 Klein - carry pipeline benchmark (15 objects, 512 refs)</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; background: #14161a; color: #e6e6e6;
         margin: 0; padding: 24px; }}
  h1 {{ margin: 0 0 4px 0; font-weight: 600; }}
  .sub {{ color: #888; margin-bottom: 6px; font-size: 14px; }}
  .note {{ color: #888; margin-bottom: 24px; font-size: 13px; max-width: 900px; line-height: 1.5; }}

  .summary {{ display: flex; gap: 32px; margin-bottom: 28px; padding: 16px 20px;
              background: #1c1f25; border-radius: 8px; max-width: 700px; }}
  .stat .label {{ color: #888; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }}
  .stat .value {{ font-size: 22px; font-weight: 600; font-family: ui-monospace, monospace; }}

  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(560px, 1fr)); gap: 16px; }}
  .card {{ background: #1c1f25; border-radius: 10px; padding: 16px; }}
  .card-header {{ margin-bottom: 12px; }}
  .oname {{ font-weight: 600; font-size: 15px; }}
  .odesc {{ font-size: 11px; color: #888; margin-top: 2px; }}
  .img-row {{ display: flex; align-items: center; gap: 12px; }}
  .img-cell {{ flex-shrink: 0; }}
  .img-cell img {{ display: block; width: 220px; height: 220px; object-fit: contain;
                   background: #0a0b0e; border-radius: 6px; }}
  .img-label {{ font-size: 11px; color: #aaa; padding-top: 4px; text-align: center; }}
  .img-meta {{ font-size: 10px; color: #666; padding-top: 2px; text-align: center;
               font-family: ui-monospace, monospace; }}
  .arrow {{ color: #6aa9d4; font-size: 14px; flex-shrink: 0; }}
  .llm-desc {{ font-size: 11px; color: #6aa9d4; margin-top: 12px; line-height: 1.45;
               border-left: 2px solid #2a4d6a; padding-left: 8px; }}
</style>
</head>
<body>
  <h1>FLUX.2 Klein - carry pipeline ({len(objects)} objects)</h1>
  <div class="sub">Real game pipeline · reference size = {REF_SIZE} (game default 256) · output 512x512</div>
  <div class="note">
    For each object: <code>generate_static_sprite</code> (t2i + bg removal) produces the input sprite,
    then <code>CARRY_INSTRUCTION</code> generates the carry description, then <code>generate_edited_sprite</code>
    runs the FLUX.2 Klein edit pipeline with the player sprite (T10) and object sprite (T20) as references.
  </div>

  <div class="summary">
    <div class="stat"><div class="label">edits</div><div class="value">{len(edit_results)}</div></div>
    <div class="stat"><div class="label">mean / edit</div><div class="value">{mean_edit:.2f}s</div></div>
    <div class="stat"><div class="label">median / edit</div><div class="value">{median_edit:.2f}s</div></div>
    <div class="stat"><div class="label">total edits</div><div class="value">{edit_total:.2f}s</div></div>
  </div>

  <div class="grid">{cards}</div>
</body>
</html>"""


if __name__ == "__main__":
    asyncio.run(main())
