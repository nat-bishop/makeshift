"""Benchmark the carry pipeline on 15 sword variations.

Bonus: for each sword, runs TWO edit calls -- one with the game-default white
background reference, and one with an actually-transparent background reference.
Lets us see whether keeping alpha vs flattening to white materially changes
edit quality.

Single output resolution: 512x512. Reference resolution: 512x512.

Usage:
    uv run python -m scripts.bench_carry_swords
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

OUT_DIR = Path(__file__).resolve().parent.parent / "sprite_comparison" / "carry_swords"
REF_SIZE = 512

SWORDS: list[tuple[str, str]] = [
    ("iron_longsword", "a plain iron longsword with a leather-wrapped grip and steel crossguard"),
    ("flaming_sword", "a steel sword wrapped in dancing orange flames along the blade"),
    ("frost_sword", "a sword encased in glowing pale-blue ice crystals"),
    ("cursed_blade", "a black cursed sword dripping shadowy purple energy"),
    ("golden_sword", "an ornate golden sword with a jeweled red pommel and engraved blade"),
    ("crystal_sword", "a translucent purple crystal sword that refracts light"),
    ("wooden_practice", "a chipped wooden practice sword with a rough handle"),
    ("broken_sword", "an old steel sword broken in half with jagged edges"),
    ("saw_sword", "a serrated saw-blade sword with rusted iron teeth"),
    ("katana", "a curved Japanese katana with red silk-wrapped handle and lacquered scabbard"),
    ("claymore", "a massive Scottish claymore with a basket hilt"),
    ("dagger", "a small steel dagger with a carved bone handle"),
    ("scimitar", "a curved Persian scimitar with an engraved silver blade"),
    ("zweihander", "a huge two-handed German zweihander sword with side rings"),
    ("obsidian_sword", "a black obsidian sword with glassy razor edges"),
]


def prepare_ref_white(sprite_bytes: bytes, ref_size: int) -> bytes:
    """Game default: paste RGBA sprite onto a white background."""
    img = Image.open(io.BytesIO(sprite_bytes)).convert("RGBA")
    img = img.resize((ref_size, ref_size), Image.Resampling.LANCZOS)
    bg = Image.new("RGBA", (ref_size, ref_size), (255, 255, 255, 255))
    bg.paste(img, (0, 0), img)
    buf = io.BytesIO()
    bg.save(buf, format="PNG")
    return buf.getvalue()


def prepare_ref_transparent(sprite_bytes: bytes, ref_size: int) -> bytes:
    """Alternative: keep alpha channel, no white fill."""
    img = Image.open(io.BytesIO(sprite_bytes)).convert("RGBA")
    img = img.resize((ref_size, ref_size), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output dir: {OUT_DIR}")
    print(f"Reference size: {REF_SIZE}, A/B = white-bg vs transparent")

    # ── Step 1: t2i sword sprites ──
    print(f"\n[1/3] Generating {len(SWORDS)} sword sprites at 512 (real pipeline)...")
    swords: list[dict] = []
    t1 = time.monotonic()
    for sname, sdesc in SWORDS:
        prompt = build_text_to_image_prompt(sname, sdesc)
        t0 = time.monotonic()
        sprite_bytes = await generate_static_sprite(prompt)
        elapsed = time.monotonic() - t0
        (OUT_DIR / f"sword_{sname}.png").write_bytes(sprite_bytes)
        swords.append(
            {"name": sname, "desc": sdesc, "sprite_bytes": sprite_bytes, "gen_elapsed": elapsed}
        )
        print(f"  {sname:18s} {elapsed:5.2f}s")
    print(f"  step1 total: {time.monotonic() - t1:.2f}s")

    # ── Step 2: LLM carry descriptions ──
    print(f"\n[2/3] LLM carry descriptions...")
    t2 = time.monotonic()
    for s in swords:
        user_prompt = (
            f"Character: player\n"
            f"Object: {s['name']} - {s['desc']}\n"
            f"Describe the player carrying the object:"
        )
        t0 = time.monotonic()
        llm_desc = await ask_text(
            user_prompt,
            max_tokens=_IMG2IMG_MAX_TOKENS,
            instructions=CARRY_INSTRUCTION,
        )
        s["llm_desc"] = llm_desc
        s["llm_elapsed"] = time.monotonic() - t0
        s["full_prompt"] = f"{IMG2IMG_STYLE}, {llm_desc}, {IMG2IMG_SUFFIX_SCENE}"
        print(f"  {s['name']:18s} ({s['llm_elapsed']:.2f}s) -> {llm_desc}")
    print(f"  step2 total: {time.monotonic() - t2:.2f}s")

    # ── Step 3: Edit pipeline -- both white and transparent refs ──
    print(f"\n[3/3] Running edits at ref={REF_SIZE} for both white-bg and transparent...")
    char_ref_white = prepare_ref_white(get_player_sprite(), REF_SIZE)
    char_ref_trans = prepare_ref_transparent(get_player_sprite(), REF_SIZE)

    edit_results: list[dict] = []
    t3 = time.monotonic()
    for s in swords:
        obj_white = prepare_ref_white(s["sprite_bytes"], REF_SIZE)
        obj_trans = prepare_ref_transparent(s["sprite_bytes"], REF_SIZE)

        # White-bg (game default behavior, just at ref=512 instead of 256)
        t0 = time.monotonic()
        out_white = await generate_edited_sprite(
            s["full_prompt"],
            [("character.png", char_ref_white), ("object.png", obj_white)],
        )
        elapsed_white = time.monotonic() - t0
        (OUT_DIR / f"carry_{s['name']}_white.png").write_bytes(out_white)

        # Transparent
        t0 = time.monotonic()
        out_trans = await generate_edited_sprite(
            s["full_prompt"],
            [("character.png", char_ref_trans), ("object.png", obj_trans)],
        )
        elapsed_trans = time.monotonic() - t0
        (OUT_DIR / f"carry_{s['name']}_transparent.png").write_bytes(out_trans)

        edit_results.append(
            {
                "sword": s["name"],
                "white": {"elapsed": elapsed_white, "bytes": len(out_white)},
                "transparent": {"elapsed": elapsed_trans, "bytes": len(out_trans)},
            }
        )
        print(
            f"  {s['name']:18s} white={elapsed_white:.2f}s  trans={elapsed_trans:.2f}s"
        )
    edit_total = time.monotonic() - t3

    # ── Summary ──
    white_times = [r["white"]["elapsed"] for r in edit_results]
    trans_times = [r["transparent"]["elapsed"] for r in edit_results]
    print("\n--- Edit timing summary ---")
    print(
        f"  white-bg     mean={statistics.mean(white_times):.2f}s "
        f"med={statistics.median(white_times):.2f}s "
        f"stdev={statistics.stdev(white_times):.2f}s"
    )
    print(
        f"  transparent  mean={statistics.mean(trans_times):.2f}s "
        f"med={statistics.median(trans_times):.2f}s "
        f"stdev={statistics.stdev(trans_times):.2f}s"
    )
    print(f"  total: {edit_total:.2f}s")

    manifest = {
        "ref_size": REF_SIZE,
        "swords": [{k: v for k, v in s.items() if k != "sprite_bytes"} for s in swords],
        "edits": edit_results,
        "edit_total_elapsed": edit_total,
    }
    (OUT_DIR / "results.json").write_text(json.dumps(manifest, indent=2, default=str))

    html = build_dashboard(swords, edit_results, edit_total)
    dashboard_path = OUT_DIR / "dashboard.html"
    dashboard_path.write_text(html, encoding="utf-8")
    print(f"\nDashboard: {dashboard_path}")


def build_dashboard(
    swords: list[dict], edit_results: list[dict], edit_total: float
) -> str:
    by_sword = {r["sword"]: r for r in edit_results}
    white_times = [r["white"]["elapsed"] for r in edit_results]
    trans_times = [r["transparent"]["elapsed"] for r in edit_results]
    mean_white = statistics.mean(white_times)
    mean_trans = statistics.mean(trans_times)

    cards = ""
    for s in swords:
        r = by_sword.get(s["name"])
        if not r:
            continue
        cards += f"""
        <div class="card">
          <div class="card-header">
            <div class="oname">{s["name"]}</div>
            <div class="odesc">{s["desc"]}</div>
          </div>
          <div class="img-row">
            <div class="img-cell">
              <img src="sword_{s["name"]}.png" alt="{s["name"]}" class="checker">
              <div class="img-label">sword input</div>
              <div class="img-meta">{s["gen_elapsed"]:.2f}s · t2i</div>
            </div>
            <div class="img-cell">
              <img src="carry_{s["name"]}_white.png" alt="carry white" class="checker">
              <div class="img-label">carry · <span class="tag-white">white-bg ref</span></div>
              <div class="img-meta">{r["white"]["elapsed"]:.2f}s · {r["white"]["bytes"] // 1024}KB</div>
            </div>
            <div class="img-cell">
              <img src="carry_{s["name"]}_transparent.png" alt="carry transparent" class="checker">
              <div class="img-label">carry · <span class="tag-trans">transparent ref</span></div>
              <div class="img-meta">{r["transparent"]["elapsed"]:.2f}s · {r["transparent"]["bytes"] // 1024}KB</div>
            </div>
          </div>
          <div class="llm-desc">LLM: {s["llm_desc"]}</div>
        </div>
        """

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>FLUX.2 Klein - sword carry + transparency A/B</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; background: #14161a; color: #e6e6e6;
         margin: 0; padding: 24px; }}
  h1 {{ margin: 0 0 4px 0; font-weight: 600; }}
  .sub {{ color: #888; margin-bottom: 6px; font-size: 14px; }}
  .note {{ color: #888; margin-bottom: 24px; font-size: 13px; max-width: 980px; line-height: 1.5; }}

  .summary {{ display: flex; gap: 32px; margin-bottom: 28px; padding: 16px 20px;
              background: #1c1f25; border-radius: 8px; max-width: 800px; }}
  .stat .label {{ color: #888; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }}
  .stat .value {{ font-size: 22px; font-weight: 600; font-family: ui-monospace, monospace; }}

  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(820px, 1fr)); gap: 16px; }}
  .card {{ background: #1c1f25; border-radius: 10px; padding: 16px; }}
  .card-header {{ margin-bottom: 12px; }}
  .oname {{ font-weight: 600; font-size: 15px; }}
  .odesc {{ font-size: 11px; color: #888; margin-top: 2px; }}
  .img-row {{ display: flex; gap: 14px; }}
  .img-cell {{ flex-shrink: 0; }}
  .img-cell img {{ display: block; width: 240px; height: 240px; object-fit: contain;
                   border-radius: 6px; }}
  /* Checkered bg so transparent images are visible */
  .checker {{
    background-color: #2a2d33;
    background-image:
      linear-gradient(45deg, #14161a 25%, transparent 25%),
      linear-gradient(-45deg, #14161a 25%, transparent 25%),
      linear-gradient(45deg, transparent 75%, #14161a 75%),
      linear-gradient(-45deg, transparent 75%, #14161a 75%);
    background-size: 16px 16px;
    background-position: 0 0, 0 8px, 8px -8px, -8px 0px;
  }}
  .img-label {{ font-size: 11px; color: #aaa; padding-top: 4px; text-align: center; }}
  .img-meta {{ font-size: 10px; color: #666; padding-top: 2px; text-align: center;
               font-family: ui-monospace, monospace; }}
  .tag-white {{ background: #4a3a1a; color: #e8d29a; padding: 1px 5px; border-radius: 3px; font-size: 9px; }}
  .tag-trans {{ background: #1a3a4a; color: #9adbe8; padding: 1px 5px; border-radius: 3px; font-size: 9px; }}
  .llm-desc {{ font-size: 11px; color: #6aa9d4; margin-top: 12px; line-height: 1.45;
               border-left: 2px solid #2a4d6a; padding-left: 8px; }}
</style>
</head>
<body>
  <h1>FLUX.2 Klein - sword carry pipeline + transparency A/B ({len(swords)} swords)</h1>
  <div class="sub">Real game pipeline · ref size {REF_SIZE} · output 512x512 · 2 edits per sword (white-bg vs transparent)</div>
  <div class="note">
    Each sword is rendered through the carry pipeline twice. <span class="tag-white">white-bg ref</span>
    flattens the alpha to white pixels (this is what <code>prepare_reference()</code> in <code>pipeline.py</code> does today).
    <span class="tag-trans">transparent ref</span> keeps the alpha channel intact. Same prompt, same LLM
    description, same player reference, same generation seed (random) — the only variable is the reference image background.
    Compare side-by-side to judge whether flattening to white affects edit quality.
  </div>

  <div class="summary">
    <div class="stat"><div class="label">swords</div><div class="value">{len(swords)}</div></div>
    <div class="stat"><div class="label">white-bg mean</div><div class="value">{mean_white:.2f}s</div></div>
    <div class="stat"><div class="label">transparent mean</div><div class="value">{mean_trans:.2f}s</div></div>
    <div class="stat"><div class="label">total edits</div><div class="value">{edit_total:.2f}s</div></div>
  </div>

  <div class="grid">{cards}</div>
</body>
</html>"""


if __name__ == "__main__":
    asyncio.run(main())
