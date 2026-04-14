"""Benchmark the carry pipeline with RAW (LLM-bg) sword refs vs bg-removed refs.

The hypothesis: keeping the original Klein-generated background on the sword
reference gives the edit pipeline more visual context (the contrasting bg color,
the implied scene) and may improve composition + reduce "just-a-hand" outputs.

For each sword, runs TWO carry edits at ref=512:
  1. raw:   generate_image() output, NO bg removal, used directly as ref
  2. clean: full game pipeline (bg removal + crop) -> flattened to white-bg ref

Same prompt, same LLM description, same player ref. Only the sword ref differs.

Usage:
    uv run python -m scripts.bench_carry_swords_raw
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
from app.images.local_image import generate_image
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

OUT_DIR = Path(__file__).resolve().parent.parent / "sprite_comparison" / "carry_swords_raw"
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


def prepare_ref_raw(raw_bytes: bytes, ref_size: int) -> bytes:
    """Resize the raw t2i image (with Klein-generated bg) to ref_size. No alpha edits."""
    img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    img = img.resize((ref_size, ref_size), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def prepare_ref_white(sprite_bytes: bytes, ref_size: int) -> bytes:
    """Game default: bg-removed RGBA -> resize -> paste on white."""
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
    print(f"A/B = raw t2i (with Klein bg) vs bg-removed (game default)")

    # ── Step 1: For each sword, generate BOTH raw and bg-removed sprites ──
    print(f"\n[1/3] Generating {len(SWORDS)} swords (raw + bg-removed)...")
    swords: list[dict] = []
    t1 = time.monotonic()
    for sname, sdesc in SWORDS:
        prompt = build_text_to_image_prompt(sname, sdesc)

        # Raw t2i: just call generate_image, no bg removal
        t0 = time.monotonic()
        raw_bytes = await generate_image(prompt)
        raw_elapsed = time.monotonic() - t0
        (OUT_DIR / f"sword_{sname}_raw.png").write_bytes(raw_bytes)

        # Bg-removed: full pipeline (calls generate_image again internally; small extra cost)
        t0 = time.monotonic()
        clean_bytes = await generate_static_sprite(prompt)
        clean_elapsed = time.monotonic() - t0
        (OUT_DIR / f"sword_{sname}_clean.png").write_bytes(clean_bytes)

        swords.append(
            {
                "name": sname,
                "desc": sdesc,
                "raw_bytes": raw_bytes,
                "clean_bytes": clean_bytes,
                "raw_elapsed": raw_elapsed,
                "clean_elapsed": clean_elapsed,
            }
        )
        print(
            f"  {sname:18s} raw={raw_elapsed:.2f}s ({len(raw_bytes):,}B) "
            f"clean={clean_elapsed:.2f}s ({len(clean_bytes):,}B)"
        )
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

    # ── Step 3: Two edit calls per sword ──
    print(f"\n[3/3] Running carry edits at ref={REF_SIZE} (raw vs bg-removed)...")
    char_ref = prepare_ref_white(get_player_sprite(), REF_SIZE)

    edit_results: list[dict] = []
    t3 = time.monotonic()
    for s in swords:
        sword_raw_ref = prepare_ref_raw(s["raw_bytes"], REF_SIZE)
        sword_clean_ref = prepare_ref_white(s["clean_bytes"], REF_SIZE)

        # Raw bg
        t0 = time.monotonic()
        out_raw = await generate_edited_sprite(
            s["full_prompt"],
            [("character.png", char_ref), ("object.png", sword_raw_ref)],
        )
        elapsed_raw = time.monotonic() - t0
        (OUT_DIR / f"carry_{s['name']}_rawref.png").write_bytes(out_raw)

        # Bg-removed (game default)
        t0 = time.monotonic()
        out_clean = await generate_edited_sprite(
            s["full_prompt"],
            [("character.png", char_ref), ("object.png", sword_clean_ref)],
        )
        elapsed_clean = time.monotonic() - t0
        (OUT_DIR / f"carry_{s['name']}_cleanref.png").write_bytes(out_clean)

        edit_results.append(
            {
                "sword": s["name"],
                "raw": {"elapsed": elapsed_raw, "bytes": len(out_raw)},
                "clean": {"elapsed": elapsed_clean, "bytes": len(out_clean)},
            }
        )
        print(
            f"  {s['name']:18s} rawref={elapsed_raw:.2f}s  cleanref={elapsed_clean:.2f}s"
        )
    edit_total = time.monotonic() - t3

    # ── Summary ──
    raw_times = [r["raw"]["elapsed"] for r in edit_results]
    clean_times = [r["clean"]["elapsed"] for r in edit_results]
    print("\n--- Edit timing summary ---")
    print(
        f"  raw ref     mean={statistics.mean(raw_times):.2f}s "
        f"med={statistics.median(raw_times):.2f}s "
        f"stdev={statistics.stdev(raw_times):.2f}s"
    )
    print(
        f"  clean ref   mean={statistics.mean(clean_times):.2f}s "
        f"med={statistics.median(clean_times):.2f}s "
        f"stdev={statistics.stdev(clean_times):.2f}s"
    )
    print(f"  total: {edit_total:.2f}s")

    manifest = {
        "ref_size": REF_SIZE,
        "swords": [
            {k: v for k, v in s.items() if k not in ("raw_bytes", "clean_bytes")}
            for s in swords
        ],
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
    raw_times = [r["raw"]["elapsed"] for r in edit_results]
    clean_times = [r["clean"]["elapsed"] for r in edit_results]
    mean_raw = statistics.mean(raw_times)
    mean_clean = statistics.mean(clean_times)

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
            <div class="col">
              <div class="col-label"><span class="tag-raw">raw t2i</span> (Klein-generated bg)</div>
              <img src="sword_{s["name"]}_raw.png" alt="{s["name"]} raw" class="checker">
              <div class="img-meta">{s["raw_elapsed"]:.2f}s · {len(s["raw_bytes"]) // 1024}KB</div>
              <div class="arrow-down">+ player &darr;</div>
              <img src="carry_{s["name"]}_rawref.png" alt="carry rawref" class="checker">
              <div class="img-meta">{r["raw"]["elapsed"]:.2f}s · {r["raw"]["bytes"] // 1024}KB</div>
            </div>
            <div class="col">
              <div class="col-label"><span class="tag-clean">bg-removed</span> (game default)</div>
              <img src="sword_{s["name"]}_clean.png" alt="{s["name"]} clean" class="checker">
              <div class="img-meta">{s["clean_elapsed"]:.2f}s · {len(s["clean_bytes"]) // 1024}KB</div>
              <div class="arrow-down">+ player &darr;</div>
              <img src="carry_{s["name"]}_cleanref.png" alt="carry cleanref" class="checker">
              <div class="img-meta">{r["clean"]["elapsed"]:.2f}s · {r["clean"]["bytes"] // 1024}KB</div>
            </div>
          </div>
          <div class="llm-desc">LLM: {s["llm_desc"]}</div>
        </div>
        """

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>FLUX.2 Klein - sword carry: raw vs bg-removed reference</title>
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

  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(560px, 1fr)); gap: 16px; }}
  .card {{ background: #1c1f25; border-radius: 10px; padding: 16px; }}
  .card-header {{ margin-bottom: 12px; }}
  .oname {{ font-weight: 600; font-size: 15px; }}
  .odesc {{ font-size: 11px; color: #888; margin-top: 2px; }}
  .img-row {{ display: flex; gap: 16px; }}
  .col {{ flex: 1; }}
  .col-label {{ font-size: 11px; color: #aaa; padding-bottom: 6px; text-align: center; }}
  .col img {{ display: block; width: 100%; max-width: 240px; aspect-ratio: 1; object-fit: contain;
              border-radius: 6px; margin: 0 auto; }}
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
  .img-meta {{ font-size: 10px; color: #666; padding: 4px 0 0 0; text-align: center;
               font-family: ui-monospace, monospace; }}
  .arrow-down {{ color: #6aa9d4; font-size: 12px; text-align: center; padding: 8px 0; }}
  .tag-raw {{ background: #4a2a1a; color: #f0c8a0; padding: 1px 5px; border-radius: 3px; font-size: 9px; }}
  .tag-clean {{ background: #2a4a3a; color: #b0e0c8; padding: 1px 5px; border-radius: 3px; font-size: 9px; }}
  .llm-desc {{ font-size: 11px; color: #6aa9d4; margin-top: 12px; line-height: 1.45;
               border-left: 2px solid #2a4d6a; padding-left: 8px; }}
</style>
</head>
<body>
  <h1>FLUX.2 Klein - sword carry: raw vs bg-removed reference</h1>
  <div class="sub">Real game pipeline · ref size {REF_SIZE} · output 512x512 · 2 edits per sword</div>
  <div class="note">
    Each sword is generated twice in step 1: once as a <span class="tag-raw">raw t2i</span> output (Klein's
    own colored background, no bg removal) and once as a <span class="tag-clean">bg-removed</span> sprite
    flattened to white (game default). Each version is then used as the sword reference in a separate carry
    edit. Same prompt, same LLM description, same player reference - the only variable is whether the sword
    reference still has its original generated background.
    <br><br>
    <b>Watching for:</b> does the raw ref reduce "just-a-hand" outputs? Does the colored background bleed
    into the carry result? Does sword likeness improve or degrade?
  </div>

  <div class="summary">
    <div class="stat"><div class="label">swords</div><div class="value">{len(swords)}</div></div>
    <div class="stat"><div class="label">raw mean</div><div class="value">{mean_raw:.2f}s</div></div>
    <div class="stat"><div class="label">clean mean</div><div class="value">{mean_clean:.2f}s</div></div>
    <div class="stat"><div class="label">total edits</div><div class="value">{edit_total:.2f}s</div></div>
  </div>

  <div class="grid">{cards}</div>
</body>
</html>"""


if __name__ == "__main__":
    asyncio.run(main())
