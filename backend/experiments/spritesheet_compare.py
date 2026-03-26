#!/usr/bin/env python3
"""Sprite sheet generation comparison — tests multiple models, prompts, and subjects.

Tests 6 approaches x 3 subjects = 18 generations, with rate-limited concurrency.

Usage:
    cd backend && uv run python -m experiments.spritesheet_compare
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

OUTPUT_DIR = SCRIPT_DIR / "output"

# Rate limit: max concurrent requests per provider
FAL_CONCURRENCY = 2
GEMINI_CONCURRENCY = 2


# ── Data types ──────────────────────────────────────────────────────────


@dataclass
class Subject:
    id: str
    name: str
    base_form: str
    material: str
    color_primary: str
    color_secondary: str
    has_movement: bool
    bg_color: str = "#1a1a1a"


@dataclass
class Approach:
    id: str
    name: str
    provider: str  # "fal" or "gemini"
    endpoint: str
    grid: int
    uses_template: bool
    prompt_style: str
    cost_cents: float = 0


@dataclass
class Result:
    approach_id: str
    approach_name: str
    subject_id: str
    subject_name: str
    path: str | None = None
    elapsed: float = 0.0
    cost_cents: float = 0.0
    error: str | None = None
    prompt: str = ""
    grid: int = 2


# ── Test matrix ─────────────────────────────────────────────────────────

SUBJECTS = [
    Subject("cow", "green cow", "cow", "fur", "green", "white", False),
    Subject("dragon", "fire dragon", "dragon", "scales", "red", "orange", True),
    Subject("slime", "blue slime", "slime blob", "translucent gel", "blue", "cyan", False),
]

APPROACHES = [
    Approach(
        "flux-baseline",
        "Flux Pro v1.1 (baseline)",
        "fal",
        "fal-ai/flux-pro/v1.1",
        2,
        False,
        "current",
        5,
    ),
    Approach(
        "flux-detailed",
        "Flux Pro v1.1 (detailed frames)",
        "fal",
        "fal-ai/flux-pro/v1.1",
        2,
        False,
        "detailed",
        5,
    ),
    Approach(
        "flux2-template",
        "FLUX.2 Pro Edit + template",
        "fal",
        "fal-ai/flux-2-pro/edit",
        2,
        True,
        "template_edit",
        5,
    ),
    Approach(
        "nano-banana-template",
        "Nano Banana Pro + template (fal)",
        "fal",
        "fal-ai/nano-banana-pro",
        4,
        True,
        "nano_template",
        15,
    ),
    Approach(
        "gemini-template",
        "Gemini Flash + template (direct)",
        "gemini",
        "gemini-3.1-flash-image-preview",
        4,
        True,
        "skill",
        7,
    ),
    Approach(
        "gemini-text",
        "Gemini Flash text-only (direct)",
        "gemini",
        "gemini-3.1-flash-image-preview",
        2,
        False,
        "gemini_text",
        7,
    ),
]


# ── Template generation ─────────────────────────────────────────────────


def make_template_image(grid: int, bg_color: str = "#1a1a1a") -> Image.Image:
    """Generate a numbered grid template image (same approach as developing-godot skill)."""
    cell_size = 1024 // grid
    size = grid * cell_size
    line_color = "#ff0000"

    bg_rgb = tuple(int(bg_color.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    if all(abs(a - b) < 60 for a, b in zip(bg_rgb, (255, 0, 0))):
        line_color = "#0000ff"

    img = Image.new("RGB", (size, size), bg_color)
    draw = ImageDraw.Draw(img)

    for i in range(1, grid):
        pos = i * cell_size
        draw.line([(pos, 0), (pos, size - 1)], fill=line_color, width=2)
        draw.line([(0, pos), (size - 1, pos)], fill=line_color, width=2)
    draw.rectangle([0, 0, size - 1, size - 1], outline=line_color, width=2)

    font = ImageFont.load_default(size=28)
    circle_r = cell_size // 6
    for row in range(grid):
        for col in range(grid):
            num = row * grid + col + 1
            cx = col * cell_size + cell_size // 2
            cy = row * cell_size + cell_size // 2
            draw.ellipse(
                [cx - circle_r, cy - circle_r, cx + circle_r, cy + circle_r],
                fill="#ffffff",
                outline=line_color,
                width=2,
            )
            label = str(num)
            bbox = draw.textbbox((0, 0), label, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(
                (cx - tw // 2, cy - th // 2 - bbox[1]),
                label,
                fill="#000000",
                font=font,
            )

    return img


def make_template_bytes(grid: int, bg_color: str = "#1a1a1a") -> bytes:
    img = make_template_image(grid, bg_color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── Prompt builders ─────────────────────────────────────────────────────


def build_prompt(approach: Approach, subject: Subject) -> str:
    style = approach.prompt_style
    g = approach.grid
    frames = g * g

    if style == "current":
        if subject.has_movement:
            anim = (
                f"{frames}-frame walk cycle: "
                "frame 1 right foot forward, frame 2 passing, "
                "frame 3 left foot forward, frame 4 passing"
            )
        else:
            anim = (
                f"{frames}-frame idle animation: "
                "frame 1 neutral, frame 2 slight inhale, "
                "frame 3 neutral, frame 4 slight exhale with blink"
            )
        return ", ".join([
            f"{g}x{g} grid sprite sheet with {frames} animation frames",
            "each frame centered in its own quadrant",
            f"medium {subject.base_form} made of {subject.material}",
            f"{subject.color_primary} with {subject.color_secondary} accents",
            f"mixed media collage style paper cutout, {anim}",
            f"consistent character across all {frames} frames",
            f"solid {subject.bg_color} background in every quadrant, no text",
        ])

    elif style == "detailed":
        if subject.has_movement:
            frame_desc = (
                "Frame 1 (top-left): standing with right foot forward, weight on front leg. "
                "Frame 2 (top-right): mid-stride, feet close together, body slightly higher. "
                "Frame 3 (bottom-left): standing with left foot forward, weight on front leg. "
                "Frame 4 (bottom-right): mid-stride returning, feet close together."
            )
        else:
            frame_desc = (
                "Frame 1 (top-left): neutral standing pose, relaxed. "
                "Frame 2 (top-right): chest slightly expanded, subtle inhale. "
                "Frame 3 (bottom-left): back to neutral, identical to frame 1. "
                "Frame 4 (bottom-right): slight exhale, eyes half-closed."
            )
        return ", ".join([
            "2x2 grid sprite sheet with 4 animation frames",
            "CRITICAL: exactly 4 equal quadrants with clear boundaries",
            f"medium {subject.base_form} made of {subject.material}",
            f"{subject.color_primary} with {subject.color_secondary} accents",
            "mixed media collage style paper cutout, side view",
            frame_desc,
            "CRITICAL: identical character proportions and centering in every frame",
            f"solid {subject.bg_color} background in every quadrant, no text, no labels",
        ])

    elif style == "template_edit":
        action = "walking" if subject.has_movement else "breathing gently (idle animation)"
        return (
            f"Replace each numbered cell in this template with an animation frame of a "
            f"{subject.color_primary} {subject.base_form} {action}. "
            f"Mixed media collage paper cutout style. "
            f"{subject.color_primary} with {subject.color_secondary} accents. "
            f"Keep the grid layout exactly. Consistent character in every frame. "
            f"Fill background with solid {subject.bg_color}."
        )

    elif style == "nano_template":
        action = "walking" if subject.has_movement else "idle breathing animation"
        return (
            f"Using the attached template as a layout guide, generate a sprite sheet. "
            f"Replace each numbered cell with a frame of: "
            f"a {subject.color_primary} {subject.base_form} {action}, "
            f"mixed media collage paper cutout style, "
            f"{subject.color_primary} with {subject.color_secondary} accents. "
            f"Keep the red grid lines. Center content in each cell. "
            f"CRITICAL: fill ALL empty space with flat solid {subject.bg_color}. "
            f"Consistent proportions and style across all frames. "
            f"Do NOT draw the numbered circles from the template."
        )

    elif style == "skill":
        action = "walking" if subject.has_movement else "idle breathing"
        return (
            f"Animation: a {subject.color_primary} {subject.base_form} {action}, "
            f"mixed media collage paper cutout style, "
            f"{subject.color_primary} with {subject.color_secondary} accents"
        )

    elif style == "gemini_text":
        if subject.has_movement:
            anim = "4-frame walk cycle"
        else:
            anim = "4-frame idle breathing animation"
        return ", ".join([
            "2x2 grid sprite sheet with 4 animation frames",
            "each frame centered in its own quadrant",
            f"medium {subject.base_form} made of {subject.material}",
            f"{subject.color_primary} with {subject.color_secondary} accents",
            f"mixed media collage style paper cutout, {anim}",
            "consistent character across all 4 frames",
            f"solid {subject.bg_color} background in every quadrant, no text",
        ])

    raise ValueError(f"Unknown prompt style: {style}")


# ── Generators ──────────────────────────────────────────────────────────


async def generate_fal(
    approach: Approach,
    subject: Subject,
    template_urls: dict[int, str],
    sem: asyncio.Semaphore,
) -> Result:
    """Generate via a fal.ai endpoint."""
    import fal_client
    import httpx

    prompt = build_prompt(approach, subject)
    result = Result(
        approach_id=approach.id,
        approach_name=approach.name,
        subject_id=subject.id,
        subject_name=subject.name,
        prompt=prompt,
        cost_cents=approach.cost_cents,
        grid=approach.grid,
    )

    async with sem:
        t0 = time.monotonic()
        try:
            ep = approach.endpoint
            args: dict = {"prompt": prompt}

            if ep == "fal-ai/flux-pro/v1.1":
                args["width"] = 1024
                args["height"] = 1024
                args["num_images"] = 1

            elif ep == "fal-ai/flux-2-pro/edit":
                url = template_urls.get(approach.grid)
                if url:
                    args["image_urls"] = [url]
                args["output_format"] = "png"

            elif ep == "fal-ai/nano-banana-pro":
                if approach.uses_template:
                    url = template_urls.get(approach.grid)
                    if url:
                        args["image_urls"] = [url]
                args["resolution"] = "1K"
                args["aspect_ratio"] = "1:1"
                args["output_format"] = "png"

            tag = f"{approach.id} x {subject.id}"
            print(f"  [{tag}] -> {ep} ...")

            handler = await fal_client.submit_async(ep, arguments=args)
            fal_result = await handler.get()

            # Extract image URL — different endpoints use different keys
            images = fal_result.get("images") or []
            if not images:
                img_data = fal_result.get("image")
                if img_data:
                    images = [img_data]
            if not images:
                raise ValueError(f"No images in response keys: {list(fal_result.keys())}")

            image_url = images[0]["url"] if isinstance(images[0], dict) else images[0]

            async with httpx.AsyncClient() as client:
                resp = await client.get(image_url)
                resp.raise_for_status()
                img_bytes = resp.content

            out_path = OUTPUT_DIR / f"{approach.id}_{subject.id}.png"
            # Ensure PNG
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


async def generate_gemini(
    approach: Approach,
    subject: Subject,
    template_bytes_map: dict[int, bytes],
    sem: asyncio.Semaphore,
) -> Result:
    """Generate via Google Gemini directly (synchronous API, run in thread)."""
    prompt = build_prompt(approach, subject)
    result = Result(
        approach_id=approach.id,
        approach_name=approach.name,
        subject_id=subject.id,
        subject_name=subject.name,
        prompt=prompt,
        cost_cents=approach.cost_cents,
        grid=approach.grid,
    )

    async with sem:
        t0 = time.monotonic()
        try:
            tag = f"{approach.id} x {subject.id}"
            print(f"  [{tag}] -> {approach.endpoint} ...")

            img_bytes = await asyncio.to_thread(
                _gemini_generate_sync,
                approach,
                subject,
                prompt,
                template_bytes_map,
            )

            out_path = OUTPUT_DIR / f"{approach.id}_{subject.id}.png"
            # Ensure PNG
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


def _gemini_generate_sync(
    approach: Approach,
    subject: Subject,
    prompt: str,
    template_bytes_map: dict[int, bytes],
) -> bytes:
    """Synchronous Gemini call (run inside asyncio.to_thread)."""
    from google import genai
    from google.genai import types

    client = genai.Client()
    contents: list = []

    if approach.uses_template:
        tb = template_bytes_map.get(approach.grid)
        if tb:
            contents.append(types.Part.from_bytes(data=tb, mime_type="image/png"))

        system = (
            f"Using the attached template image as an exact layout guide: "
            f"generate a sprite sheet. "
            f"The image is a {approach.grid}x{approach.grid} grid "
            f"of {approach.grid ** 2} equal cells separated by red lines. "
            f"Replace each numbered cell with the corresponding content, "
            f"reading left-to-right, top-to-bottom "
            f"(cell 1 = first, cell {approach.grid ** 2} = last).\n\n"
            f"Rules:\n"
            f"- KEEP the red grid lines exactly where they are in the template\n"
            f"- Each cell's content must be CENTERED in its cell and "
            f"must NOT cross into adjacent cells\n"
            f"- CRITICAL: fill ALL empty space in every cell with flat solid "
            f"{subject.bg_color} — no gradients, no scenery, no patterns\n"
            f"- Maintain consistent style, lighting direction, "
            f"and proportions across all {approach.grid ** 2} cells\n"
            f"- CRITICAL: do NOT draw the numbered circles from the template — "
            f"replace them entirely with the actual content"
        )
        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            system_instruction=system,
            image_config=types.ImageConfig(image_size="1K", aspect_ratio="1:1"),
        )
    else:
        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(image_size="1K", aspect_ratio="1:1"),
        )

    contents.append(prompt)

    response = client.models.generate_content(
        model=approach.endpoint,
        contents=contents,
        config=config,
    )

    if response.parts is None:
        reason = "unknown"
        if response.candidates and response.candidates[0].finish_reason:
            reason = str(response.candidates[0].finish_reason)
        raise ValueError(f"Generation blocked: {reason}")

    for part in response.parts:
        if part.inline_data is not None:
            return part.inline_data.data

    raise ValueError("No image in Gemini response")


# ── HTML report ─────────────────────────────────────────────────────────


def generate_report(results: list[Result]) -> str:
    subjects = {s.id: s for s in SUBJECTS}
    approaches = {a.id: a for a in APPROACHES}
    approach_ids = [a.id for a in APPROACHES]
    subject_ids = [s.id for s in SUBJECTS]

    ok = [r for r in results if not r.error]
    total_cost = sum(r.cost_cents for r in ok)
    total_time = sum(r.elapsed for r in results)

    # Build grid rows
    rows_html = []
    for sid in subject_ids:
        cells = []
        for aid in approach_ids:
            r = next((r for r in results if r.approach_id == aid and r.subject_id == sid), None)
            if r and r.path and not r.error:
                fname = Path(r.path).name
                cells.append(
                    f'<td class="cell">'
                    f'<a href="{fname}" target="_blank">'
                    f'<img src="{fname}" alt="{aid} {sid}"></a>'
                    f'<div class="meta">{r.elapsed:.1f}s &middot; '
                    f'{r.cost_cents:.0f}&cent; &middot; {r.grid}x{r.grid}</div>'
                    f"</td>"
                )
            elif r and r.error:
                short = r.error[:100].replace("<", "&lt;")
                cells.append(
                    f'<td class="cell error">'
                    f'<div class="error-msg">FAILED<br><small>{short}</small></div>'
                    f"</td>"
                )
            else:
                cells.append('<td class="cell">&mdash;</td>')

        rows_html.append(
            f'<tr><th class="subject">{subjects[sid].name}</th>'
            f'{"".join(cells)}</tr>'
        )

    headers = "".join(f"<th>{approaches[a].name}</th>" for a in approach_ids)

    # Prompt detail rows
    prompt_rows = []
    for r in results:
        status = "OK" if not r.error else f'FAILED: {r.error[:80].replace("<", "&lt;")}'
        p = r.prompt.replace("<", "&lt;")[:200]
        prompt_rows.append(
            f"<tr><td>{r.approach_name}</td><td>{r.subject_name}</td>"
            f"<td><code>{p}{'...' if len(r.prompt) > 200 else ''}</code></td>"
            f"<td>{status}</td><td>{r.elapsed:.1f}s</td></tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Sprite Sheet Comparison</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 24px; background: #111; color: #ddd; }}
  h1 {{ color: #fff; margin-bottom: 4px; }}
  .summary {{ color: #999; margin-bottom: 24px; }}
  table {{ border-collapse: collapse; margin: 16px 0; }}
  th, td {{ border: 1px solid #333; padding: 8px; text-align: center; vertical-align: top; }}
  th {{ background: #1a1a1a; font-size: 12px; white-space: nowrap; }}
  .subject {{ text-align: right; padding-right: 16px; font-size: 15px; font-weight: 600; }}
  .cell {{ background: #0a0a0a; }}
  .cell img {{ max-width: 300px; max-height: 300px; display: block; margin: 4px auto;
               border: 1px solid #222; }}
  .cell .meta {{ font-size: 11px; color: #666; margin-top: 4px; }}
  .cell.error {{ background: #1a0808; }}
  .error-msg {{ color: #c44; font-size: 12px; padding: 40px 8px; }}
  h2 {{ color: #fff; margin-top: 48px; }}
  .prompts td {{ text-align: left; font-size: 12px; max-width: 420px; }}
  .prompts code {{ color: #8f8; word-break: break-all; font-size: 11px; }}
</style>
</head>
<body>
<h1>Sprite Sheet Generation &mdash; Comparison</h1>
<div class="summary">
  {len(ok)}/{len(results)} succeeded &middot;
  ~{total_cost:.0f}&cent; total &middot;
  {total_time:.0f}s wall time
</div>

<table>
  <tr><th>Subject</th>{headers}</tr>
  {"".join(rows_html)}
</table>

<h2>Prompts &amp; Details</h2>
<table class="prompts">
  <tr><th>Approach</th><th>Subject</th><th>Prompt</th><th>Status</th><th>Time</th></tr>
  {"".join(prompt_rows)}
</table>
</body>
</html>"""


# ── Main ────────────────────────────────────────────────────────────────


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    n = len(APPROACHES) * len(SUBJECTS)
    est_cost = sum(a.cost_cents for a in APPROACHES) * len(SUBJECTS)
    print(f"Sprite Sheet Comparison Experiment")
    print(f"  {len(APPROACHES)} approaches x {len(SUBJECTS)} subjects = {n} generations")
    print(f"  Estimated cost: ~{est_cost:.0f}c")
    print(f"  Output: {OUTPUT_DIR}\n")

    # Generate + save templates
    print("Preparing templates...")
    template_bytes: dict[int, bytes] = {}
    template_urls: dict[int, str] = {}

    grids_needed = {a.grid for a in APPROACHES if a.uses_template}
    for grid_size in sorted(grids_needed):
        tb = make_template_bytes(grid_size)
        template_bytes[grid_size] = tb
        tpath = OUTPUT_DIR / f"template_{grid_size}x{grid_size}.png"
        tpath.write_bytes(tb)
        print(f"  {grid_size}x{grid_size} template -> {tpath.name}")

    # Upload templates to fal for endpoints that need image_urls
    fal_template_needed = {
        a.grid for a in APPROACHES if a.provider == "fal" and a.uses_template
    }
    if fal_template_needed:
        import fal_client

        for grid_size in sorted(fal_template_needed):
            tpath = OUTPUT_DIR / f"template_{grid_size}x{grid_size}.png"
            print(f"  Uploading {grid_size}x{grid_size} template to fal storage...")
            url = await asyncio.to_thread(fal_client.upload_file, str(tpath))
            template_urls[grid_size] = url
            print(f"  -> {url[:80]}...")

    # Create semaphores for rate limiting
    fal_sem = asyncio.Semaphore(FAL_CONCURRENCY)
    gemini_sem = asyncio.Semaphore(GEMINI_CONCURRENCY)

    # Build all tasks
    tasks = []
    for approach in APPROACHES:
        for subject in SUBJECTS:
            if approach.provider == "fal":
                tasks.append(generate_fal(approach, subject, template_urls, fal_sem))
            else:
                tasks.append(generate_gemini(approach, subject, template_bytes, gemini_sem))

    print(
        f"\nRunning {len(tasks)} generations "
        f"(fal: <={FAL_CONCURRENCY} concurrent, gemini: <={GEMINI_CONCURRENCY} concurrent)...\n"
    )
    t_start = time.monotonic()
    results: list[Result] = list(await asyncio.gather(*tasks))
    wall_time = time.monotonic() - t_start

    # Generate report
    report_html = generate_report(results)
    report_path = OUTPUT_DIR / "report.html"
    report_path.write_text(report_html, encoding="utf-8")

    # Summary
    ok = [r for r in results if not r.error]
    failed = [r for r in results if r.error]
    total_cost = sum(r.cost_cents for r in ok)

    print(f"\n{'=' * 60}")
    print(f"DONE in {wall_time:.0f}s: {len(ok)} succeeded, {len(failed)} failed")
    print(f"Estimated cost: ~{total_cost:.0f}c")
    print(f"Report: {report_path}")

    if failed:
        print(f"\nFailures:")
        for r in failed:
            print(f"  {r.approach_id} x {r.subject_id}: {r.error}")

    print(f"\nOpen the report:  start {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
