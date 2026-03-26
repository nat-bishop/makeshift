#!/usr/bin/env python3
"""Round 5: Nano Banana 2 — idle animations with paper-cutout style variations.

All tests use fal-ai/nano-banana-2 with 2x2 idle sprite sheets.
Explores different art style prompts in the paper-craft vibe.

Usage:
    cd backend && uv run python -m experiments.spritesheet_round5
"""

from __future__ import annotations

import asyncio
import io
import sys
import time
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from PIL import Image

OUTPUT_DIR = SCRIPT_DIR / "output" / "round5"
ENDPOINT = "fal-ai/nano-banana-2"
CONCURRENCY = 2

BG = "#1a1a1a"


@dataclass
class Style:
    id: str
    name: str
    desc: str  # art style clause inserted into prompt


@dataclass
class Subject:
    id: str
    name: str
    what: str  # object description
    idle: str  # idle animation description


@dataclass
class Result:
    style_id: str
    style_name: str
    subject_id: str
    subject_name: str
    path: str | None = None
    elapsed: float = 0.0
    error: str | None = None
    prompt: str = ""


STYLES = [
    Style(
        "paper-cutout", "Paper Cutout (baseline)",
        "mixed media collage style paper cutout, flat lighting, clean edges",
    ),
    Style(
        "torn-paper", "Torn Paper Collage",
        "torn newspaper and colored paper collage, visible paper grain and rough edges, "
        "layered scraps of old book pages and craft paper",
    ),
    Style(
        "felt-craft", "Felt & Fabric Craft",
        "handmade felt craft style, stitched fabric pieces with visible thread, "
        "soft textile texture, embroidered details",
    ),
    Style(
        "cardboard", "Cardboard Puppet",
        "corrugated cardboard and brown kraft paper construction, "
        "brass brad joints, hand-painted details on recycled cardboard",
    ),
    Style(
        "papercraft-3d", "3D Papercraft",
        "low-poly papercraft style, folded geometric paper surfaces with visible creases, "
        "matte colored card stock, origami-inspired construction",
    ),
    Style(
        "woodblock", "Woodblock Print",
        "Japanese woodblock print style, bold ink outlines on textured washi paper, "
        "flat color fills with visible wood grain texture in the ink",
    ),
    Style(
        "stained-glass", "Stained Glass",
        "stained glass window style, bold dark leading lines separating flat colored segments, "
        "translucent jewel tones, mosaic construction",
    ),
]

SUBJECTS = [
    Subject("cow", "Green Cow",
            "medium cow, green with white spots",
            "gentle breathing, chest rising and falling"),
    Subject("dragon", "Fire Dragon",
            "medium dragon, red with orange accents, small wings",
            "slow wing flutter and tail sway"),
    Subject("slime", "Blue Slime",
            "medium slime blob, blue with cyan highlights, translucent gel",
            "gentle wobble and pulse, slight shape shift"),
    Subject("knight", "Knight",
            "small knight in armor, silver with red cape",
            "subtle weight shift and cape sway"),
]


def build_prompt(style: Style, subject: Subject) -> str:
    return (
        f"2x2 grid sprite sheet with 4 animation frames, "
        f"each frame centered in its own quadrant. "
        f"{subject.what}, {style.desc}, side view. "
        f"4-frame idle animation: {subject.idle}. "
        f"CRITICAL: same character, same proportions, same facing direction in every frame. "
        f"Only subtle movement between frames. "
        f"Solid {BG} background in every quadrant, no text, no labels."
    )


async def generate(
    style: Style, subject: Subject, sem: asyncio.Semaphore,
) -> Result:
    import fal_client
    import httpx

    prompt = build_prompt(style, subject)
    result = Result(
        style_id=style.id, style_name=style.name,
        subject_id=subject.id, subject_name=subject.name,
        prompt=prompt,
    )
    async with sem:
        t0 = time.monotonic()
        try:
            tag = f"{style.id} x {subject.id}"
            print(f"  [{tag}] generating...")

            handler = await fal_client.submit_async(ENDPOINT, arguments={
                "prompt": prompt,
                "resolution": "1K",
                "aspect_ratio": "1:1",
                "output_format": "png",
            })
            fal_result = await handler.get()

            images = fal_result.get("images") or []
            if not images:
                img_data = fal_result.get("image")
                if img_data:
                    images = [img_data]
            if not images:
                raise ValueError(f"No images: {list(fal_result.keys())}")

            image_url = images[0]["url"] if isinstance(images[0], dict) else images[0]

            async with httpx.AsyncClient() as client:
                resp = await client.get(image_url)
                resp.raise_for_status()
                img_bytes = resp.content

            out_path = OUTPUT_DIR / f"{style.id}_{subject.id}.png"
            if img_bytes[:4] != b"\x89PNG":
                img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                img_bytes = buf.getvalue()
            out_path.write_bytes(img_bytes)

            result.path = str(out_path)
            result.elapsed = time.monotonic() - t0
            print(f"  [{tag}] done ({result.elapsed:.1f}s)")

        except Exception as e:
            result.error = f"{type(e).__name__}: {e}"
            result.elapsed = time.monotonic() - t0
            print(f"  [{tag}] FAILED: {result.error}")
    return result


def generate_report(results: list[Result]) -> str:
    style_ids = [s.id for s in STYLES]
    subject_ids = [s.id for s in SUBJECTS]
    styles_map = {s.id: s for s in STYLES}
    subjects_map = {s.id: s for s in SUBJECTS}

    ok = [r for r in results if not r.error]
    total_time = sum(r.elapsed for r in results)

    headers = "".join(
        f'<th>{styles_map[s].name}</th>' for s in style_ids
    )

    rows = []
    for sid in subject_ids:
        cells = []
        for stid in style_ids:
            r = next((r for r in results if r.style_id == stid and r.subject_id == sid), None)
            if r and r.path and not r.error:
                fname = Path(r.path).name
                cells.append(
                    f'<td class="cell">'
                    f'<canvas class="anim" data-src="{fname}" data-grid="2" '
                    f'width="180" height="180"></canvas>'
                    f'<a href="{fname}" target="_blank">'
                    f'<img src="{fname}" class="sheet" alt="{stid} {sid}"></a>'
                    f'<div class="meta">{r.elapsed:.1f}s</div></td>'
                )
            elif r and r.error:
                short = r.error[:100].replace("<", "&lt;")
                cells.append(
                    f'<td class="cell error"><div class="error-msg">FAILED<br>'
                    f'<small>{short}</small></div></td>'
                )
            else:
                cells.append('<td class="cell">-</td>')
        rows.append(
            f'<tr><th class="subject">{subjects_map[sid].name}</th>{"".join(cells)}</tr>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Round 5: Nano Banana 2 Style Variations</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: system-ui, sans-serif; background: #111; color: #ddd; padding: 24px; }}
  h1 {{ margin-bottom: 4px; }}
  .summary {{ color: #999; margin-bottom: 20px; }}
  .controls {{ margin: 8px 0 20px; display: flex; gap: 16px; align-items: center; }}
  .controls label {{ font-size: 13px; color: #999; }}
  .controls input {{ width: 100px; }}
  .controls span {{ font-size: 13px; color: #fff; min-width: 36px; }}
  table {{ border-collapse: collapse; margin: 16px 0; }}
  th, td {{ border: 1px solid #333; padding: 6px; text-align: center; vertical-align: top; }}
  th {{ background: #1a1a1a; font-size: 11px; max-width: 120px; }}
  .subject {{ text-align: right; padding-right: 12px; font-size: 14px; font-weight: 600; }}
  .cell {{ background: #0a0a0a; }}
  canvas.anim {{ display: block; margin: 0 auto 4px; image-rendering: pixelated;
                 border: 1px solid #333; cursor: pointer; }}
  .sheet {{ width: 100%; max-width: 180px; border: 1px solid #222; margin-top: 2px; }}
  .cell .meta {{ font-size: 10px; color: #666; }}
  .cell.error {{ background: #1a0808; }}
  .error-msg {{ color: #c44; font-size: 11px; padding: 20px 4px; }}
</style>
</head>
<body>
<h1>Round 5: Nano Banana 2 &mdash; Style Variations</h1>
<div class="summary">
  Model: {ENDPOINT} | {len(ok)}/{len(results)} succeeded |
  {total_time:.0f}s wall | ~$0.08/img @1K |
  Top row = animated preview, bottom = full sheet
</div>
<div class="controls">
  <label>FPS:</label>
  <input type="range" id="fps" min="1" max="8" value="3">
  <span id="fps-val">3</span>
  <label>Click animation to pause</label>
</div>

<table>
  <tr><th>Subject</th>{headers}</tr>
  {"".join(rows)}
</table>

<script>
let fps = 3, paused = false, frameIndex = 0, lastTime = 0;
const cells = [];
document.querySelectorAll("canvas.anim").forEach(canvas => {{
  const ctx = canvas.getContext("2d");
  const img = new Image();
  const grid = parseInt(canvas.dataset.grid);
  const cell = {{ canvas, ctx, img, grid, loaded: false }};
  img.onload = () => {{ cell.loaded = true; }};
  img.src = canvas.dataset.src;
  cells.push(cell);
  canvas.addEventListener("click", () => {{ paused = !paused; }});
}});
function draw() {{
  for (const c of cells) {{
    if (!c.loaded) continue;
    const frame = frameIndex % (c.grid * c.grid);
    const col = frame % c.grid, row = Math.floor(frame / c.grid);
    const fw = c.img.naturalWidth / c.grid, fh = c.img.naturalHeight / c.grid;
    c.ctx.clearRect(0, 0, c.canvas.width, c.canvas.height);
    c.ctx.drawImage(c.img, col*fw, row*fh, fw, fh, 0, 0, c.canvas.width, c.canvas.height);
  }}
}}
function animate(ts) {{
  if (!paused && ts - lastTime >= 1000/fps) {{ lastTime = ts; frameIndex++; draw(); }}
  requestAnimationFrame(animate);
}}
document.getElementById("fps").addEventListener("input", e => {{
  fps = parseInt(e.target.value);
  document.getElementById("fps-val").textContent = fps;
}});
requestAnimationFrame(animate);
</script>
</body>
</html>"""


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    n = len(STYLES) * len(SUBJECTS)
    cost = n * 0.08
    print(f"Round 5: Nano Banana 2 Style Variations")
    print(f"  {len(STYLES)} styles x {len(SUBJECTS)} subjects = {n} generations")
    print(f"  ~${cost:.2f} estimated | Endpoint: {ENDPOINT}")
    print(f"  Output: {OUTPUT_DIR}\n")

    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = [generate(style, subject, sem) for style in STYLES for subject in SUBJECTS]

    print(f"Running {len(tasks)} generations (max {CONCURRENCY} concurrent)...\n")
    t0 = time.monotonic()
    results = list(await asyncio.gather(*tasks))
    wall = time.monotonic() - t0

    report = generate_report(results)
    report_path = OUTPUT_DIR / "report.html"
    report_path.write_text(report, encoding="utf-8")

    ok = [r for r in results if not r.error]
    failed = [r for r in results if r.error]
    print(f"\n{'=' * 60}")
    print(f"DONE in {wall:.0f}s: {len(ok)} succeeded, {len(failed)} failed")
    print(f"Report: {report_path}")
    if failed:
        print("\nFailures:")
        for r in failed:
            print(f"  {r.style_id} x {r.subject_id}: {r.error}")


if __name__ == "__main__":
    asyncio.run(main())
