#!/usr/bin/env python3
"""Round 7: Simple movement animations — isolating one body part change per test.

Same cat, Gemini Flash, but focused on locomotion-style animations.

Usage:
    cd backend && uv run python -m experiments.spritesheet_round7
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

OUTPUT_DIR = SCRIPT_DIR / "output" / "round7"
IMAGE_MODEL = "gemini-3.1-flash-image-preview"
BG = "#1a1a1a"

CAT = "an orange tabby cat, mixed media collage style paper cutout, side view facing right"


@dataclass
class Test:
    id: str
    name: str
    prompt: str


@dataclass
class Result:
    test_id: str
    test_name: str
    path: str | None = None
    elapsed: float = 0.0
    error: str | None = None
    prompt: str = ""


TESTS = [
    Test("front-legs-only", "Front Legs Only", (
        f"2x2 grid sprite sheet with 4 animation frames, each frame centered in its quadrant. "
        f"{CAT}. "
        f"Frame 1 (top-left): cat standing, front right paw lifted forward. "
        f"Frame 2 (top-right): IDENTICAL cat, front right paw planted, front left paw lifted forward. "
        f"Frame 3 (bottom-left): IDENTICAL to frame 1. "
        f"Frame 4 (bottom-right): IDENTICAL to frame 2. "
        f"CRITICAL: the ONLY difference between frames is which front paw is forward. "
        f"Back legs, tail, head, body ALL stay exactly the same. "
        f"Solid {BG} background, no text."
    )),
    Test("all-legs-simple", "All Legs Walk (simple)", (
        f"2x2 grid sprite sheet with 4 animation frames, each frame centered in its quadrant. "
        f"{CAT}, walking. "
        f"Frame 1 (top-left): right legs forward, left legs back. "
        f"Frame 2 (top-right): legs passing through center, close together. "
        f"Frame 3 (bottom-left): left legs forward, right legs back. "
        f"Frame 4 (bottom-right): legs passing through center again. "
        f"CRITICAL: same cat, same size, same head position in every frame. "
        f"Only the leg positions change. "
        f"Solid {BG} background, no text."
    )),
    Test("bounce-squash", "Bounce (squash & stretch)", (
        f"2x2 grid sprite sheet with 4 animation frames, each frame centered in its quadrant. "
        f"{CAT}. "
        f"Frame 1 (top-left): cat at normal height, normal proportions. "
        f"Frame 2 (top-right): IDENTICAL cat but slightly squished shorter and wider, legs bent, about to jump. "
        f"Frame 3 (bottom-left): IDENTICAL cat but stretched slightly taller and narrower, paws off ground, at peak of small hop. "
        f"Frame 4 (bottom-right): IDENTICAL cat landing, slightly squished again. "
        f"CRITICAL: same cat, same style, same facing direction. "
        f"Only the height and compression of the body changes. "
        f"Solid {BG} background, no text."
    )),
    Test("pounce-ready", "Pounce Ready (crouch cycle)", (
        f"2x2 grid sprite sheet with 4 animation frames, each frame centered in its quadrant. "
        f"{CAT}. "
        f"Frame 1 (top-left): cat standing upright, alert. "
        f"Frame 2 (top-right): cat crouching lower, butt wiggling up. "
        f"Frame 3 (bottom-left): cat crouched very low, rear raised, about to pounce. "
        f"Frame 4 (bottom-right): cat back to half-crouch, settling. "
        f"CRITICAL: same cat, same style, same facing direction in every frame. "
        f"Solid {BG} background, no text."
    )),
]


def _generate_sync(prompt: str) -> bytes:
    from google import genai
    from google.genai import types

    client = genai.Client()
    response = client.models.generate_content(
        model=IMAGE_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(image_size="1K", aspect_ratio="1:1"),
        ),
    )
    if response.parts is None:
        reason = "unknown"
        if response.candidates and response.candidates[0].finish_reason:
            reason = str(response.candidates[0].finish_reason)
        raise ValueError(f"Blocked: {reason}")
    for part in response.parts:
        if part.inline_data is not None:
            return part.inline_data.data
    raise ValueError("No image in response")


async def run_test(test: Test, sem: asyncio.Semaphore) -> Result:
    result = Result(test_id=test.id, test_name=test.name, prompt=test.prompt)
    async with sem:
        t0 = time.monotonic()
        try:
            print(f"  [{test.id}] generating...")
            img_bytes = await asyncio.to_thread(_generate_sync, test.prompt)
            out_path = OUTPUT_DIR / f"{test.id}.png"
            if img_bytes[:4] != b"\x89PNG":
                img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                img_bytes = buf.getvalue()
            out_path.write_bytes(img_bytes)
            result.path = str(out_path)
            result.elapsed = time.monotonic() - t0
            print(f"  [{test.id}] done ({result.elapsed:.1f}s)")
        except Exception as e:
            result.error = f"{type(e).__name__}: {e}"
            result.elapsed = time.monotonic() - t0
            print(f"  [{test.id}] FAILED: {result.error}")
    return result


def generate_report(results: list[Result]) -> str:
    ok = [r for r in results if not r.error]
    total_time = sum(r.elapsed for r in results)

    cards = []
    for r in results:
        if r.path and not r.error:
            fname = Path(r.path).name
            prompt_short = r.prompt.replace("<", "&lt;").replace("\n", " ")
            cards.append(
                f'<div class="card">'
                f'<h3>{r.test_name}</h3>'
                f'<canvas class="anim" data-src="{fname}" data-grid="2" '
                f'width="240" height="240"></canvas>'
                f'<a href="{fname}" target="_blank">'
                f'<img src="{fname}" class="sheet" alt="{r.test_id}"></a>'
                f'<div class="meta">{r.elapsed:.1f}s</div>'
                f'<details><summary>Prompt</summary>'
                f'<code>{prompt_short}</code></details>'
                f'</div>'
            )
        elif r and r.error:
            cards.append(
                f'<div class="card error-card">'
                f'<h3>{r.test_name}</h3>'
                f'<div class="error-msg">FAILED: {r.error[:120].replace("<", "&lt;")}</div>'
                f'</div>'
            )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Round 7: Movement Animations</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: system-ui, sans-serif; background: #111; color: #ddd; padding: 24px; }}
  h1 {{ margin-bottom: 4px; }}
  h3 {{ font-size: 14px; margin-bottom: 8px; }}
  .summary {{ color: #999; margin-bottom: 20px; }}
  .controls {{ margin: 8px 0 20px; display: flex; gap: 16px; align-items: center; }}
  .controls label {{ font-size: 13px; color: #999; }}
  .controls input {{ width: 120px; }}
  .controls span {{ font-size: 13px; color: #fff; min-width: 36px; }}
  .row {{ display: flex; flex-wrap: wrap; gap: 20px; }}
  .card {{ background: #1a1a1a; border: 1px solid #333; border-radius: 8px;
           padding: 16px; width: 280px; }}
  canvas.anim {{ display: block; margin: 0 auto 8px; image-rendering: pixelated;
                 border: 1px solid #333; cursor: pointer; }}
  .sheet {{ width: 100%; border: 1px solid #222; margin-top: 4px; }}
  .meta {{ font-size: 11px; color: #666; margin-top: 4px; }}
  .error-card {{ border-color: #633; }}
  .error-msg {{ color: #c44; font-size: 12px; }}
  details {{ margin-top: 8px; }}
  summary {{ font-size: 11px; color: #888; cursor: pointer; }}
  code {{ font-size: 10px; color: #8f8; word-break: break-all; display: block; margin-top: 4px; }}
</style>
</head>
<body>
<h1>Round 7: Movement Animations &mdash; Orange Tabby Cat</h1>
<div class="summary">
  Testing simple locomotion choreographies with isolated body-part changes.<br>
  Model: {IMAGE_MODEL} | {len(ok)}/{len(results)} succeeded | {total_time:.0f}s
</div>
<div class="controls">
  <label>FPS:</label>
  <input type="range" id="fps" min="1" max="8" value="4">
  <span id="fps-val">4</span>
  <label>Click to pause</label>
</div>
<div class="row">{"".join(cards)}</div>

<script>
let fps = 4, paused = false, frameIndex = 0, lastTime = 0;
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
    print(f"Round 7: Movement Animations (cat)")
    print(f"  {len(TESTS)} tests | Model: {IMAGE_MODEL}")
    print(f"  Output: {OUTPUT_DIR}\n")

    sem = asyncio.Semaphore(2)
    t0 = time.monotonic()
    results = list(await asyncio.gather(*[run_test(t, sem) for t in TESTS]))
    wall = time.monotonic() - t0

    report = generate_report(results)
    report_path = OUTPUT_DIR / "report.html"
    report_path.write_text(report, encoding="utf-8")

    ok = [r for r in results if not r.error]
    print(f"\n{'=' * 60}")
    print(f"DONE in {wall:.0f}s: {len(ok)}/{len(results)} succeeded")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
