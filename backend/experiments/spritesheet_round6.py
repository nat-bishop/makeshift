#!/usr/bin/env python3
"""Round 6: Single subject (cat), 4 very specific simple animation choreographies.

Tests whether hyper-specific per-frame descriptions produce usable animations.
Uses Gemini Flash direct (best paper cutout results).

Usage:
    cd backend && uv run python -m experiments.spritesheet_round6
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

OUTPUT_DIR = SCRIPT_DIR / "output" / "round6"
IMAGE_MODEL = "gemini-3.1-flash-image-preview"
BG = "#1a1a1a"

CAT_BASE = (
    "an orange tabby cat, mixed media collage style paper cutout, "
    "side view facing right, green with white accents"
)


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
    Test("breathing", "Breathing (chest only)", (
        f"2x2 grid sprite sheet with 4 animation frames, each frame centered in its quadrant. "
        f"{CAT_BASE}. "
        f"Frame 1 (top-left): cat standing relaxed, normal posture. "
        f"Frame 2 (top-right): IDENTICAL cat, chest slightly puffed out from inhaling. "
        f"Frame 3 (bottom-left): IDENTICAL to frame 1, chest back to normal. "
        f"Frame 4 (bottom-right): IDENTICAL cat, chest slightly compressed from exhaling. "
        f"CRITICAL: the ONLY difference between frames is the chest size. "
        f"Same legs, same head, same tail, same position, same size. "
        f"Solid {BG} background, no text."
    )),
    Test("tail-swish", "Tail Swish", (
        f"2x2 grid sprite sheet with 4 animation frames, each frame centered in its quadrant. "
        f"{CAT_BASE}. "
        f"Frame 1 (top-left): cat standing, tail curved upward to the right. "
        f"Frame 2 (top-right): IDENTICAL cat, tail straight out behind. "
        f"Frame 3 (bottom-left): IDENTICAL cat, tail curved downward to the left. "
        f"Frame 4 (bottom-right): IDENTICAL cat, tail straight out behind. "
        f"CRITICAL: the ONLY difference between frames is the tail position. "
        f"Same body, same legs, same head position, same size. "
        f"Solid {BG} background, no text."
    )),
    Test("head-bob", "Head Bob", (
        f"2x2 grid sprite sheet with 4 animation frames, each frame centered in its quadrant. "
        f"{CAT_BASE}. "
        f"Frame 1 (top-left): cat standing, head at normal height. "
        f"Frame 2 (top-right): IDENTICAL cat, head raised slightly, ears perked. "
        f"Frame 3 (bottom-left): IDENTICAL cat, head back to normal height. "
        f"Frame 4 (bottom-right): IDENTICAL cat, head dipped slightly lower. "
        f"CRITICAL: the ONLY difference between frames is the head height. "
        f"Same body, same legs, same tail, same size. "
        f"Solid {BG} background, no text."
    )),
    Test("blink", "Blink Cycle", (
        f"2x2 grid sprite sheet with 4 animation frames, each frame centered in its quadrant. "
        f"{CAT_BASE}. "
        f"Frame 1 (top-left): cat standing, eyes fully open. "
        f"Frame 2 (top-right): IDENTICAL cat, eyes half-closed, sleepy. "
        f"Frame 3 (bottom-left): IDENTICAL cat, eyes fully closed, blinking. "
        f"Frame 4 (bottom-right): IDENTICAL cat, eyes half-open, waking back up. "
        f"CRITICAL: the ONLY difference between frames is the eyes. "
        f"Same body, same legs, same tail, same head position, same size. "
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


async def run_test(test: Test) -> Result:
    result = Result(test_id=test.id, test_name=test.name, prompt=test.prompt)
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
        elif r.error:
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
<title>Round 6: Simple Choreography Test</title>
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
<h1>Round 6: Simple Choreography &mdash; Orange Tabby Cat</h1>
<div class="summary">
  Each test animates ONE specific body part. Everything else stays identical.<br>
  Model: {IMAGE_MODEL} | {len(ok)}/{len(results)} succeeded | {total_time:.0f}s
</div>
<div class="controls">
  <label>FPS:</label>
  <input type="range" id="fps" min="1" max="8" value="3">
  <span id="fps-val">3</span>
  <label>Click to pause</label>
</div>
<div class="row">{"".join(cards)}</div>

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
    print(f"Round 6: Simple Choreography (cat)")
    print(f"  {len(TESTS)} tests | Model: {IMAGE_MODEL}")
    print(f"  Output: {OUTPUT_DIR}\n")

    # Run 2 at a time
    sem = asyncio.Semaphore(2)

    async def limited(test):
        async with sem:
            return await run_test(test)

    t0 = time.monotonic()
    results = list(await asyncio.gather(*[limited(t) for t in TESTS]))
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
