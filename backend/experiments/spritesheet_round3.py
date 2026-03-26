#!/usr/bin/env python3
"""Round 3: LLM-rewritten choreography + strict technical requirements.

Two-step approach inspired by FalSprite:
  1. LLM rewrites subject into CHARACTER + CHOREOGRAPHY
  2. Strict technical requirements wrap the rewrite
  3. Gemini Flash generates the sprite sheet

Tests LLM-rewrite vs hand-written, 2x2 vs 4x4, template vs text-only.

Usage:
    cd backend && uv run python -m experiments.spritesheet_round3
"""

from __future__ import annotations

import asyncio
import io
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = SCRIPT_DIR / "output" / "round3"
IMAGE_MODEL = "gemini-3.1-flash-image-preview"
TEXT_MODEL = "gemini-3.1-flash-lite-preview"
CONCURRENCY = 2


# ── LLM rewrite ────────────────────────────────────────────────────────

REWRITE_SYSTEM_2x2 = """\
You are an animation director and character designer for a sprite sheet pipeline.
Given a character concept, return exactly two sections:

CHARACTER: vivid appearance description -- body type, shape, colors, \
surface texture, silhouette, art style (mixed media collage paper cutout).

CHOREOGRAPHY: a 4-beat continuous animation loop. Each beat = one cell in a \
2x2 grid (top-left, top-right, bottom-left, bottom-right). \
Last beat loops seamlessly back to first. \
Describe body position, weight distribution, limb placement per beat.

Rules: no numbers, no mention of grids/pixels/frames/sprites. \
Write as if directing a real actor through mocap. \
Keep motions simple and subtle -- this is a small game sprite."""

REWRITE_SYSTEM_4x4 = """\
You are an animation director and character designer for a sprite sheet pipeline.
Given a character concept, return exactly two sections:

CHARACTER: vivid appearance description -- body type, shape, colors, \
surface texture, silhouette, art style (mixed media collage paper cutout).

CHOREOGRAPHY: a 4-beat continuous animation loop. Each beat = one row of 4 \
cells (4 sub-moments per beat, 16 cells total). Last beat loops seamlessly \
back to first. Describe body position, weight distribution, limb placement \
per beat and how the 4 sub-moments within each beat progress.

Rules: no numbers, no mention of grids/pixels/frames/sprites. \
Write as if directing a real actor through mocap. \
Keep motions simple and subtle -- this is a small game sprite."""


def _rewrite_sync(subject_prompt: str, system: str) -> str:
    """Use Gemini text model to rewrite subject into character + choreography."""
    from google import genai
    from google.genai import types

    client = genai.Client()
    response = client.models.generate_content(
        model=TEXT_MODEL,
        contents=f"Design the character and choreograph a four-beat animation loop for: {subject_prompt}",
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.7,
        ),
    )
    return response.text


STRICT_REQUIREMENTS_2x2 = """\
STRICT TECHNICAL REQUIREMENTS FOR THIS IMAGE:

FORMAT: A single image containing a two-by-two grid of equally sized cells.
Every cell must be the exact same dimensions, perfectly aligned, with no gaps or overlap.

FORBIDDEN: Absolutely no text, no numbers, no letters, no digits, no labels, \
no watermarks, no signatures, no UI elements anywhere in the image.

CONSISTENCY: The exact same single character must appear in every cell.
Same proportions, same art style, same level of detail, same camera angle throughout.
Side view. Full body visible head to toe in every cell.
Strong clean silhouette against a plain solid flat-color background ({bg}).

ANIMATION FLOW: The cells read left-to-right, top-to-bottom, like reading a page.
Each cell shows the next moment in the movement. The very last cell loops back \
seamlessly to the very first cell.

MOTION QUALITY: Show real weight and physics. Bodies shift weight between feet.
Arms counterbalance legs. For locomotion: strictly alternate left and right legs.
Never repeat the same pose twice in a row.

CHARACTER AND ANIMATION DIRECTION:
{choreography}"""

STRICT_REQUIREMENTS_4x4 = """\
STRICT TECHNICAL REQUIREMENTS FOR THIS IMAGE:

FORMAT: A single image containing a four-by-four grid of equally sized cells.
Every cell must be the exact same dimensions, perfectly aligned, with no gaps or overlap.

FORBIDDEN: Absolutely no text, no numbers, no letters, no digits, no labels, \
no watermarks, no signatures, no UI elements anywhere in the image.

CONSISTENCY: The exact same single character must appear in every cell.
Same proportions, same art style, same level of detail, same camera angle throughout.
Side view. Full body visible head to toe in every cell.
Strong clean silhouette against a plain solid flat-color background ({bg}).

ANIMATION FLOW: The cells read left-to-right, top-to-bottom, like reading a page.
Each cell shows the next moment in the movement. The very last cell loops back \
seamlessly to the very first cell.

MOTION QUALITY: Show real weight and physics. Bodies shift weight between feet.
Arms counterbalance legs. For locomotion: strictly alternate left and right legs.
Never repeat the same pose twice in a row.

CHARACTER AND ANIMATION DIRECTION:
{choreography}"""


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
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill="#fff", outline=line_color, width=2)
            label = str(num)
            bbox = draw.textbbox((0, 0), label, font=font)
            tw = bbox[2] - bbox[0]
            draw.text((cx - tw // 2, cy - bbox[1] // 2 - bbox[1]), label, fill="#000", font=font)
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
        f"reading left-to-right, top-to-bottom.\n\n"
        f"Rules:\n"
        f"- KEEP the red grid lines exactly where they are\n"
        f"- Each cell's content must be CENTERED and NOT cross into adjacent cells\n"
        f"- CRITICAL: fill ALL empty space with flat solid {bg}\n"
        f"- Maintain consistent style, lighting, proportions across all {n} cells\n"
        f"- Do NOT draw the numbered circles from the template"
    )


# ── Test definitions ────────────────────────────────────────────────────

BG = "#1a1a1a"


@dataclass
class Subject:
    id: str
    name: str
    prompt: str  # what we send to the LLM rewriter
    action: str  # for non-LLM fallback


SUBJECTS = [
    Subject("cow", "green cow", "a green cow with white spots, walking", "walking"),
    Subject("dragon", "fire dragon", "a red fire dragon with orange accents, walking", "walking"),
    Subject("slime", "blue slime", "a blue translucent slime blob, bouncing up and down", "bouncing"),
    Subject("knight", "knight", "a small knight in silver armor with red cape, walking", "walking"),
    Subject("cat", "orange cat", "an orange tabby cat, walking", "walking"),
]


@dataclass
class Test:
    id: str
    name: str
    subject_id: str
    grid: int
    uses_template: bool
    uses_llm_rewrite: bool
    prompt: str = ""  # filled at runtime
    rewrite_text: str = ""  # filled at runtime


@dataclass
class Result:
    test_id: str
    test_name: str
    subject: str
    path: str | None = None
    elapsed: float = 0.0
    error: str | None = None
    prompt: str = ""
    rewrite: str = ""
    grid: int = 2
    uses_template: bool = False


def build_tests() -> list[Test]:
    tests = []
    for s in SUBJECTS:
        # 1. LLM rewrite, text-only, 2x2
        tests.append(Test(
            f"{s.id}-llm-2x2", f"{s.name} (LLM rewrite, 2x2)",
            s.id, 2, False, True,
        ))
        # 2. LLM rewrite, text-only, 4x4
        tests.append(Test(
            f"{s.id}-llm-4x4", f"{s.name} (LLM rewrite, 4x4)",
            s.id, 4, False, True,
        ))
        # 3. LLM rewrite + template, 2x2
        tests.append(Test(
            f"{s.id}-llm-tpl2", f"{s.name} (LLM rewrite + tpl 2x2)",
            s.id, 2, True, True,
        ))
        # 4. Strict requirements only (no LLM), text-only, 2x2
        tests.append(Test(
            f"{s.id}-strict-2x2", f"{s.name} (strict only, 2x2)",
            s.id, 2, False, False,
        ))
    return tests


# ── Generators ──────────────────────────────────────────────────────────


def _generate_image_sync(
    prompt: str,
    uses_template: bool,
    grid: int,
    template_bytes_map: dict[int, bytes],
) -> bytes:
    from google import genai
    from google.genai import types

    client = genai.Client()
    contents: list = []

    if uses_template:
        tb = template_bytes_map.get(grid)
        if tb:
            contents.append(types.Part.from_bytes(data=tb, mime_type="image/png"))
        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            system_instruction=template_system(grid, BG),
            image_config=types.ImageConfig(image_size="1K", aspect_ratio="1:1"),
        )
    else:
        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(image_size="1K", aspect_ratio="1:1"),
        )

    contents.append(prompt)

    response = client.models.generate_content(
        model=IMAGE_MODEL, contents=contents, config=config,
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
    test: Test,
    subject: Subject,
    template_bytes_map: dict[int, bytes],
    sem: asyncio.Semaphore,
) -> Result:
    result = Result(
        test_id=test.id, test_name=test.name, subject=subject.name,
        grid=test.grid, uses_template=test.uses_template,
    )
    async with sem:
        t0 = time.monotonic()
        try:
            # Step 1: LLM rewrite (if applicable)
            if test.uses_llm_rewrite:
                rewrite_sys = REWRITE_SYSTEM_2x2 if test.grid == 2 else REWRITE_SYSTEM_4x4
                print(f"  [{test.id}] LLM rewriting...")
                rewrite = await asyncio.to_thread(
                    _rewrite_sync, subject.prompt, rewrite_sys,
                )
                test.rewrite_text = rewrite
                result.rewrite = rewrite
            else:
                # Build a simple choreography without LLM
                rewrite = (
                    f"CHARACTER: a {subject.prompt}, mixed media collage paper cutout style.\n\n"
                    f"CHOREOGRAPHY: The character is {subject.action} in a continuous loop. "
                    f"Weight shifts between legs with each step. Arms/limbs counterbalance. "
                    f"Each beat shows a distinct phase of the motion."
                )
                result.rewrite = rewrite

            # Step 2: Wrap in strict requirements
            if test.grid == 2:
                full_prompt = STRICT_REQUIREMENTS_2x2.format(bg=BG, choreography=rewrite)
            else:
                full_prompt = STRICT_REQUIREMENTS_4x4.format(bg=BG, choreography=rewrite)

            test.prompt = full_prompt
            result.prompt = full_prompt

            # Step 3: Generate image
            print(f"  [{test.id}] generating image...")
            img_bytes = await asyncio.to_thread(
                _generate_image_sync,
                full_prompt,
                test.uses_template,
                test.grid,
                template_bytes_map,
            )

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


def generate_report(results: list[Result], tests: list[Test]) -> str:
    # Group by subject
    subjects_order = []
    seen = set()
    for s in SUBJECTS:
        if s.id not in seen:
            subjects_order.append(s)
            seen.add(s.id)

    approach_suffixes = ["-llm-2x2", "-llm-4x4", "-llm-tpl2", "-strict-2x2"]
    approach_labels = [
        "LLM rewrite (2x2)",
        "LLM rewrite (4x4)",
        "LLM + template (2x2)",
        "Strict only (2x2)",
    ]

    ok = [r for r in results if not r.error]
    total_cost = len(ok) * 7
    total_time = sum(r.elapsed for r in results)

    sections = []
    for s in subjects_order:
        cards = []
        for suffix, label in zip(approach_suffixes, approach_labels):
            tid = f"{s.id}{suffix}"
            r = next((r for r in results if r.test_id == tid), None)
            if r and r.path and not r.error:
                fname = Path(r.path).name
                # Truncate rewrite for display
                rewrite_short = r.rewrite.replace("<", "&lt;").replace("\n", "<br>")
                if len(rewrite_short) > 600:
                    rewrite_short = rewrite_short[:600] + "..."
                tpl_tag = "template" if r.uses_template else "text-only"
                cards.append(
                    f'<div class="card">'
                    f'<div class="card-title">{label}</div>'
                    f'<div class="card-meta">{r.grid}x{r.grid} {tpl_tag} | {r.elapsed:.1f}s</div>'
                    f'<canvas class="anim" data-src="{fname}" data-grid="{r.grid}" '
                    f'width="200" height="200"></canvas>'
                    f'<a href="{fname}" target="_blank">'
                    f'<img src="{fname}" class="sheet" alt="{tid}"></a>'
                    f'<details><summary>LLM Rewrite</summary>'
                    f'<div class="rewrite">{rewrite_short}</div></details>'
                    f'</div>'
                )
            elif r and r.error:
                cards.append(
                    f'<div class="card error-card">'
                    f'<div class="card-title">{label}</div>'
                    f'<div class="error-msg">FAILED: {r.error[:120].replace("<", "&lt;")}</div>'
                    f'</div>'
                )
        sections.append(
            f'<h2>{s.name.title()}</h2><div class="row">{"".join(cards)}</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Round 3: LLM Choreography Sprite Sheets</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: system-ui, sans-serif; background: #111; color: #ddd; padding: 24px; }}
  h1 {{ margin-bottom: 4px; }}
  .summary {{ color: #999; margin-bottom: 20px; }}
  .controls {{ margin: 12px 0 20px; display: flex; gap: 16px; align-items: center; }}
  .controls label {{ font-size: 13px; color: #999; }}
  .controls input {{ width: 100px; }}
  .controls span {{ font-size: 13px; color: #fff; min-width: 36px; }}
  h2 {{ margin: 32px 0 12px; color: #fff; border-bottom: 1px solid #333; padding-bottom: 4px; }}
  .row {{ display: flex; flex-wrap: wrap; gap: 16px; }}
  .card {{ background: #1a1a1a; border: 1px solid #333; border-radius: 8px;
           padding: 12px; width: 240px; }}
  .card-title {{ font-size: 13px; font-weight: 600; margin-bottom: 4px; }}
  .card-meta {{ font-size: 11px; color: #666; margin-bottom: 8px; }}
  canvas.anim {{ display: block; margin: 0 auto 8px; image-rendering: pixelated;
                 border: 1px solid #333; cursor: pointer; }}
  .sheet {{ width: 100%; border: 1px solid #222; margin-top: 4px; }}
  .error-card {{ border-color: #633; }}
  .error-msg {{ color: #c44; font-size: 12px; }}
  details {{ margin-top: 8px; }}
  summary {{ font-size: 11px; color: #888; cursor: pointer; }}
  .rewrite {{ font-size: 10px; color: #aaa; margin-top: 4px; line-height: 1.4;
              max-height: 200px; overflow-y: auto; }}
</style>
</head>
<body>
<h1>Round 3: LLM-Rewritten Choreography</h1>
<div class="summary">
  2-step: LLM ({TEXT_MODEL}) rewrites subject into CHARACTER + CHOREOGRAPHY,
  then strict technical requirements wrap it for {IMAGE_MODEL}.<br>
  {len(ok)}/{len(results)} succeeded | ~{total_cost}c total | {total_time:.0f}s wall time
</div>
<div class="controls">
  <label>FPS:</label>
  <input type="range" id="fps" min="1" max="12" value="4">
  <span id="fps-val">4</span>
  <label>Click animation to pause</label>
</div>
{"".join(sections)}

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


# ── Main ────────────────────────────────────────────────────────────────


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tests = build_tests()
    cost_est = len(tests) * 7 + len([t for t in tests if t.uses_llm_rewrite])  # +1c per rewrite
    print(f"Round 3: LLM Choreography Sprite Sheets")
    print(f"  {len(tests)} tests | ~{cost_est}c estimated")
    print(f"  Text model: {TEXT_MODEL} | Image model: {IMAGE_MODEL}")
    print(f"  Output: {OUTPUT_DIR}\n")

    # Templates
    template_bytes: dict[int, bytes] = {}
    for grid_size in {t.grid for t in tests if t.uses_template}:
        tb = make_template_bytes(grid_size)
        template_bytes[grid_size] = tb
        p = OUTPUT_DIR / f"template_{grid_size}x{grid_size}.png"
        p.write_bytes(tb)
        print(f"  Template {grid_size}x{grid_size} -> {p.name}")

    subject_map = {s.id: s for s in SUBJECTS}
    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = [
        run_test(t, subject_map[t.subject_id], template_bytes, sem)
        for t in tests
    ]

    print(f"\nRunning {len(tasks)} generations (max {CONCURRENCY} concurrent)...\n")
    t0 = time.monotonic()
    results = list(await asyncio.gather(*tasks))
    wall = time.monotonic() - t0

    # Save LLM rewrites for reference
    rewrites_path = OUTPUT_DIR / "rewrites.md"
    with open(rewrites_path, "w", encoding="utf-8") as f:
        f.write("# LLM Rewrites\n\n")
        for r in results:
            if r.rewrite:
                f.write(f"## {r.test_id}\n\n```\n{r.rewrite}\n```\n\n")

    report = generate_report(results, tests)
    report_path = OUTPUT_DIR / "report.html"
    report_path.write_text(report, encoding="utf-8")

    ok = [r for r in results if not r.error]
    failed = [r for r in results if r.error]
    print(f"\n{'=' * 60}")
    print(f"DONE in {wall:.0f}s: {len(ok)} succeeded, {len(failed)} failed")
    print(f"Estimated cost: ~{len(ok) * 7}c")
    print(f"Report: {report_path}")
    print(f"Rewrites: {rewrites_path}")
    if failed:
        print("\nFailures:")
        for r in failed:
            print(f"  {r.test_id}: {r.error}")


if __name__ == "__main__":
    asyncio.run(main())
