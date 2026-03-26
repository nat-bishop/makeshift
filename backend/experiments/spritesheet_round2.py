#!/usr/bin/env python3
"""Round 2: Gemini Flash sprite sheet experiments — movement animation + prompt styles.

Focused on gemini-3.1-flash-image-preview only, testing:
- Walk/movement vs idle
- Template vs text-only
- Different prompt styles (minimal, descriptive, per-frame choreography)
- Different subjects

Usage:
    cd backend && uv run python -m experiments.spritesheet_round2
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

from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = SCRIPT_DIR / "output" / "round2"
GEMINI_MODEL = "gemini-3.1-flash-image-preview"
CONCURRENCY = 2


@dataclass
class Test:
    id: str
    name: str
    subject: str
    uses_template: bool
    grid: int
    prompt: str
    system: str | None = None  # only for template approaches


@dataclass
class Result:
    test_id: str
    test_name: str
    subject: str
    path: str | None = None
    elapsed: float = 0.0
    error: str | None = None
    prompt: str = ""
    grid: int = 2
    uses_template: bool = False


# ── Template ────────────────────────────────────────────────────────────


def make_template_bytes(grid: int, bg: str = "#1a1a1a") -> bytes:
    cell = 1024 // grid
    size = grid * cell
    line_color = "#ff0000"
    img = Image.new("RGB", (size, size), bg)
    draw = ImageDraw.Draw(img)
    for i in range(1, grid):
        pos = i * cell
        draw.line([(pos, 0), (pos, size - 1)], fill=line_color, width=2)
        draw.line([(0, pos), (size - 1, pos)], fill=line_color, width=2)
    draw.rectangle([0, 0, size - 1, size - 1], outline=line_color, width=2)
    font = ImageFont.load_default(size=28)
    r = cell // 6
    for row in range(grid):
        for col in range(grid):
            num = row * grid + col + 1
            cx, cy = col * cell + cell // 2, row * cell + cell // 2
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill="#ffffff", outline=line_color, width=2)
            label = str(num)
            bbox = draw.textbbox((0, 0), label, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text((cx - tw // 2, cy - th // 2 - bbox[1]), label, fill="#000000", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def template_system(grid: int, bg: str = "#1a1a1a") -> str:
    n = grid * grid
    return (
        f"Using the attached template image as an exact layout guide: "
        f"generate a sprite sheet. "
        f"The image is a {grid}x{grid} grid of {n} equal cells separated by red lines. "
        f"Replace each numbered cell with the corresponding content, "
        f"reading left-to-right, top-to-bottom (cell 1 = first, cell {n} = last).\n\n"
        f"Rules:\n"
        f"- KEEP the red grid lines exactly where they are in the template\n"
        f"- Each cell's content must be CENTERED in its cell and NOT cross into adjacent cells\n"
        f"- CRITICAL: fill ALL empty space with flat solid {bg}\n"
        f"- Maintain consistent style, lighting direction, and proportions across all {n} cells\n"
        f"- CRITICAL: do NOT draw the numbered circles from the template"
    )


# ── Test definitions ────────────────────────────────────────────────────

BG = "#1a1a1a"

TESTS = [
    # ── COW: walk animation, different prompt styles ──

    # Text-only, minimal
    Test(
        "cow-text-walk-minimal", "Cow walk (text, minimal)", "cow",
        False, 2,
        "2x2 grid sprite sheet, 4-frame walk cycle of a green cow, "
        "mixed media collage paper cutout style, green with white accents, "
        f"consistent character, solid {BG} background, no text",
    ),
    # Text-only, descriptive choreography
    Test(
        "cow-text-walk-choreo", "Cow walk (text, choreography)", "cow",
        False, 2,
        "2x2 grid sprite sheet with 4 animation frames, each frame centered in its quadrant. "
        "A green cow walking, mixed media collage paper cutout style, green with white accents. "
        "Frame 1 (top-left): right legs forward, left legs back. "
        "Frame 2 (top-right): legs passing, body slightly lifted. "
        "Frame 3 (bottom-left): left legs forward, right legs back. "
        "Frame 4 (bottom-right): legs passing again, completing the cycle. "
        f"CRITICAL: same cow, same proportions, same facing direction in every frame. "
        f"Solid {BG} background in every quadrant, no text.",
    ),
    # Template 4x4, walk
    Test(
        "cow-tpl-walk", "Cow walk (template 4x4)", "cow",
        True, 4,
        "Animation: a green cow walking, mixed media collage paper cutout style, "
        "green with white accents, 16-frame walk cycle",
        template_system(4, BG),
    ),
    # Template 2x2, walk
    Test(
        "cow-tpl2-walk", "Cow walk (template 2x2)", "cow",
        True, 2,
        "Animation: a green cow walking, mixed media collage paper cutout style, "
        "green with white accents, 4-frame walk cycle",
        template_system(2, BG),
    ),

    # ── DRAGON: walk animation, different prompt styles ──

    Test(
        "dragon-text-walk-minimal", "Dragon walk (text, minimal)", "dragon",
        False, 2,
        "2x2 grid sprite sheet, 4-frame walk cycle of a red fire dragon, "
        "mixed media collage paper cutout style, red with orange accents, "
        f"consistent character, solid {BG} background, no text",
    ),
    Test(
        "dragon-text-walk-choreo", "Dragon walk (text, choreography)", "dragon",
        False, 2,
        "2x2 grid sprite sheet with 4 animation frames, each frame centered in its quadrant. "
        "A red fire dragon walking right, mixed media collage paper cutout style, "
        "red with orange accents, side view. "
        "Frame 1: right front leg forward, left hind leg forward. "
        "Frame 2: legs mid-stride, wings slightly raised. "
        "Frame 3: left front leg forward, right hind leg forward. "
        "Frame 4: legs mid-stride, wings slightly lowered. "
        f"CRITICAL: same dragon, same size, same facing direction in every frame. "
        f"Solid {BG} background, no text.",
    ),
    Test(
        "dragon-tpl-walk", "Dragon walk (template 4x4)", "dragon",
        True, 4,
        "Animation: a red fire dragon walking, mixed media collage paper cutout style, "
        "red with orange accents, side view, 16-frame walk cycle",
        template_system(4, BG),
    ),
    Test(
        "dragon-tpl2-walk", "Dragon walk (template 2x2)", "dragon",
        True, 2,
        "Animation: a red fire dragon walking, mixed media collage paper cutout style, "
        "red with orange accents, side view, 4-frame walk cycle",
        template_system(2, BG),
    ),

    # ── SLIME: bounce animation ──

    Test(
        "slime-text-bounce-minimal", "Slime bounce (text, minimal)", "slime",
        False, 2,
        "2x2 grid sprite sheet, 4-frame bounce cycle of a blue slime blob, "
        "mixed media collage paper cutout style, blue with cyan accents, "
        f"consistent character, solid {BG} background, no text",
    ),
    Test(
        "slime-text-bounce-choreo", "Slime bounce (text, choreography)", "slime",
        False, 2,
        "2x2 grid sprite sheet with 4 animation frames, each frame centered in its quadrant. "
        "A blue slime blob bouncing, mixed media collage paper cutout style, "
        "blue with cyan accents, translucent gel material. "
        "Frame 1: resting on ground, wide and flat. "
        "Frame 2: compressing down, very wide and squished. "
        "Frame 3: stretching up tall and narrow, leaving the ground. "
        "Frame 4: at peak height, round shape, starting to fall back. "
        f"CRITICAL: same slime, same style in every frame, only shape changes. "
        f"Solid {BG} background, no text.",
    ),
    Test(
        "slime-tpl-bounce", "Slime bounce (template 4x4)", "slime",
        True, 4,
        "Animation: a blue slime blob bouncing up and down, "
        "mixed media collage paper cutout style, blue with cyan accents, "
        "16-frame bounce cycle showing squash and stretch",
        template_system(4, BG),
    ),
    Test(
        "slime-tpl2-bounce", "Slime bounce (template 2x2)", "slime",
        True, 2,
        "Animation: a blue slime blob bouncing, "
        "mixed media collage paper cutout style, blue with cyan accents, "
        "4-frame bounce cycle with squash and stretch",
        template_system(2, BG),
    ),

    # ── EXTRA SUBJECTS: walk with the best prompt styles from above ──

    Test(
        "knight-text-walk", "Knight walk (text, choreo)", "knight",
        False, 2,
        "2x2 grid sprite sheet with 4 animation frames, each frame centered in its quadrant. "
        "A small knight in silver armor walking right, mixed media collage paper cutout style, "
        "silver with red cape accents. "
        "Frame 1: right foot forward. Frame 2: feet together mid-stride. "
        "Frame 3: left foot forward. Frame 4: feet together mid-stride. "
        f"CRITICAL: same knight, same proportions in every frame. "
        f"Solid {BG} background, no text.",
    ),
    Test(
        "knight-tpl2-walk", "Knight walk (template 2x2)", "knight",
        True, 2,
        "Animation: a small knight in silver armor walking, "
        "mixed media collage paper cutout style, silver with red cape accents, "
        "4-frame walk cycle, side view",
        template_system(2, BG),
    ),
    Test(
        "cat-text-walk", "Cat walk (text, choreo)", "cat",
        False, 2,
        "2x2 grid sprite sheet with 4 animation frames, each frame centered in its quadrant. "
        "An orange tabby cat walking right, mixed media collage paper cutout style, "
        "orange with cream accents. "
        "Frame 1: right front paw forward. Frame 2: mid-stride. "
        "Frame 3: left front paw forward. Frame 4: mid-stride. "
        f"CRITICAL: same cat, same proportions in every frame. "
        f"Solid {BG} background, no text.",
    ),
    Test(
        "cat-tpl2-walk", "Cat walk (template 2x2)", "cat",
        True, 2,
        "Animation: an orange tabby cat walking, "
        "mixed media collage paper cutout style, orange with cream accents, "
        "4-frame walk cycle, side view",
        template_system(2, BG),
    ),
]


# ── Generator ───────────────────────────────────────────────────────────


def _generate_sync(test: Test, template_bytes_map: dict[int, bytes]) -> bytes:
    from google import genai
    from google.genai import types

    client = genai.Client()
    contents: list = []

    if test.uses_template:
        tb = template_bytes_map.get(test.grid)
        if tb:
            contents.append(types.Part.from_bytes(data=tb, mime_type="image/png"))
        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            system_instruction=test.system,
            image_config=types.ImageConfig(image_size="1K", aspect_ratio="1:1"),
        )
    else:
        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(image_size="1K", aspect_ratio="1:1"),
        )

    contents.append(test.prompt)

    response = client.models.generate_content(
        model=GEMINI_MODEL, contents=contents, config=config,
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


async def run_test(
    test: Test, template_bytes_map: dict[int, bytes], sem: asyncio.Semaphore,
) -> Result:
    result = Result(
        test_id=test.id, test_name=test.name, subject=test.subject,
        prompt=test.prompt, grid=test.grid, uses_template=test.uses_template,
    )
    async with sem:
        t0 = time.monotonic()
        try:
            print(f"  [{test.id}] generating...")
            img_bytes = await asyncio.to_thread(_generate_sync, test, template_bytes_map)

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


# ── Report ──────────────────────────────────────────────────────────────


def generate_report(results: list[Result]) -> str:
    # Group by subject
    subjects_order = []
    seen = set()
    for t in TESTS:
        if t.subject not in seen:
            subjects_order.append(t.subject)
            seen.add(t.subject)

    subject_results: dict[str, list[Result]] = {s: [] for s in subjects_order}
    for r in results:
        subject_results[r.subject].append(r)

    sections = []
    for subj in subjects_order:
        rs = subject_results[subj]
        cards = []
        for r in rs:
            if r.path and not r.error:
                fname = Path(r.path).name
                tpl_tag = f"{r.grid}x{r.grid} template" if r.uses_template else "text-only"
                cards.append(
                    f'<div class="card">'
                    f'<div class="card-title">{r.test_name}</div>'
                    f'<div class="card-meta">{tpl_tag} | {r.elapsed:.1f}s</div>'
                    f'<canvas class="anim" data-src="{fname}" data-grid="{r.grid}" '
                    f'width="200" height="200"></canvas>'
                    f'<a href="{fname}" target="_blank">'
                    f'<img src="{fname}" class="sheet" alt="{r.test_id}"></a>'
                    f'<details><summary>Prompt</summary>'
                    f'<code>{r.prompt.replace("<", "&lt;")}</code></details>'
                    f'</div>'
                )
            elif r.error:
                cards.append(
                    f'<div class="card error-card">'
                    f'<div class="card-title">{r.test_name}</div>'
                    f'<div class="error-msg">FAILED: {r.error[:120].replace("<", "&lt;")}</div>'
                    f'</div>'
                )

        sections.append(
            f'<h2>{subj.title()}</h2><div class="row">{"".join(cards)}</div>'
        )

    ok = [r for r in results if not r.error]
    total_cost = len(ok) * 7
    total_time = sum(r.elapsed for r in results)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Round 2: Gemini Flash Sprite Sheets</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: system-ui, sans-serif; background: #111; color: #ddd; padding: 24px; }}
  h1 {{ margin-bottom: 4px; }}
  .summary {{ color: #999; margin-bottom: 24px; }}
  h2 {{ margin: 32px 0 12px; color: #fff; border-bottom: 1px solid #333; padding-bottom: 4px; }}
  .controls {{ margin: 12px 0 20px; display: flex; gap: 16px; align-items: center; }}
  .controls label {{ font-size: 13px; color: #999; }}
  .controls input {{ width: 100px; }}
  .controls span {{ font-size: 13px; color: #fff; min-width: 36px; }}
  .row {{ display: flex; flex-wrap: wrap; gap: 16px; }}
  .card {{ background: #1a1a1a; border: 1px solid #333; border-radius: 8px;
           padding: 12px; width: 220px; }}
  .card-title {{ font-size: 13px; font-weight: 600; margin-bottom: 4px; }}
  .card-meta {{ font-size: 11px; color: #666; margin-bottom: 8px; }}
  canvas.anim {{ display: block; margin: 0 auto 8px; image-rendering: pixelated;
                 border: 1px solid #333; cursor: pointer; }}
  .sheet {{ width: 100%; border: 1px solid #222; margin-top: 4px; }}
  .error-card {{ border-color: #633; }}
  .error-msg {{ color: #c44; font-size: 12px; }}
  details {{ margin-top: 8px; }}
  summary {{ font-size: 11px; color: #888; cursor: pointer; }}
  code {{ font-size: 10px; color: #8f8; word-break: break-all; display: block; margin-top: 4px; }}
</style>
</head>
<body>
<h1>Round 2: Gemini Flash Sprite Sheets</h1>
<div class="summary">
  Model: {GEMINI_MODEL} |
  {len(ok)}/{len(results)} succeeded |
  ~{total_cost}c total |
  {total_time:.0f}s wall time
</div>
<div class="controls">
  <label>FPS:</label>
  <input type="range" id="fps" min="1" max="12" value="4">
  <span id="fps-val">4</span>
  <label>Click animation to pause</label>
</div>
{"".join(sections)}

<script>
let fps = 4;
let paused = false;
let frameIndex = 0;
let lastTime = 0;
const cells = [];

document.querySelectorAll("canvas.anim").forEach(canvas => {{
  const ctx = canvas.getContext("2d");
  const img = new Image();
  const grid = parseInt(canvas.dataset.grid);
  const cell = {{ canvas, ctx, img, grid, loaded: false }};
  img.onload = () => {{ cell.loaded = true; }};
  img.src = canvas.dataset.src;
  cells.push(cell);
  canvas.addEventListener("click", () => {{
    paused = !paused;
  }});
}});

function draw() {{
  for (const c of cells) {{
    if (!c.loaded) continue;
    const frame = frameIndex % (c.grid * c.grid);
    const col = frame % c.grid;
    const row = Math.floor(frame / c.grid);
    const fw = c.img.naturalWidth / c.grid;
    const fh = c.img.naturalHeight / c.grid;
    c.ctx.clearRect(0, 0, c.canvas.width, c.canvas.height);
    c.ctx.drawImage(c.img, col*fw, row*fh, fw, fh, 0, 0, c.canvas.width, c.canvas.height);
  }}
}}

function animate(ts) {{
  if (!paused && ts - lastTime >= 1000 / fps) {{
    lastTime = ts;
    frameIndex++;
    draw();
  }}
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


# ── Main ────────────────────────────────────────────────────────────────


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cost_est = len(TESTS) * 7
    print(f"Round 2: Gemini Flash Sprite Sheets")
    print(f"  {len(TESTS)} tests | ~{cost_est}c estimated | Model: {GEMINI_MODEL}")
    print(f"  Output: {OUTPUT_DIR}\n")

    # Templates
    template_bytes: dict[int, bytes] = {}
    for grid_size in {t.grid for t in TESTS if t.uses_template}:
        tb = make_template_bytes(grid_size)
        template_bytes[grid_size] = tb
        p = OUTPUT_DIR / f"template_{grid_size}x{grid_size}.png"
        p.write_bytes(tb)
        print(f"  Template {grid_size}x{grid_size} -> {p.name}")

    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = [run_test(t, template_bytes, sem) for t in TESTS]
    print(f"\nRunning {len(tasks)} generations (max {CONCURRENCY} concurrent)...\n")

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
    print(f"Estimated cost: ~{len(ok) * 7}c")
    print(f"Report: {report_path}")
    if failed:
        print("\nFailures:")
        for r in failed:
            print(f"  {r.test_id}: {r.error}")


if __name__ == "__main__":
    asyncio.run(main())
