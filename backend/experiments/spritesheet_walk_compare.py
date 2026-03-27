#!/usr/bin/env python3
"""Spritesheet walk cycle comparison — single-sheet approaches.

Tests different single-sheet generation strategies for a walk cycle:
  A. IDENTICAL constraint (round 6/7 style, no template)
  B. LLM-rewritten choreography (round 3 style, no template)
  C. 4x4 template-guided with system instruction
  D. 2x2 template-guided with system instruction
  E. TEXT+IMAGE modality with IDENTICAL constraints

All produce a single spritesheet image per strategy.
Slices into frames + bg removal for animated preview.

Usage:
    uv run python -m experiments.spritesheet_walk_compare
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = SCRIPT_DIR / "output" / "spritesheet_walk"

IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gemini-3.1-flash-image-preview")
TEXT_MODEL = "gemini-3.1-flash-lite-preview"
CONCURRENCY = 2
BG = "#1a1a1a"

CHARACTER = "a human adventurer with a backpack and boots, mixed media collage style paper cutout, side view facing right"


# ── Template generation ────────────────────────────────────────────────


def make_template(grid: int, bg: str = BG) -> bytes:
    """Generate a numbered grid template image."""
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
            draw.ellipse(
                [cx - r, cy - r, cx + r, cy + r],
                fill="#fff", outline=line_color, width=2,
            )
            label = str(num)
            bbox = draw.textbbox((0, 0), label, font=font)
            tw = bbox[2] - bbox[0]
            draw.text(
                (cx - tw // 2, cy - bbox[1] // 2 - bbox[1]),
                label, fill="#000", font=font,
            )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def template_system_instruction(grid: int) -> str:
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
        f"- CRITICAL: fill ALL empty space with flat solid {BG}\n"
        f"- Maintain consistent style, lighting, proportions across all {n} cells\n"
        f"- Do NOT draw the numbered circles from the template\n"
        f"- No text, no numbers, no labels, no watermarks anywhere"
    )


# ── LLM choreography (for strategy B) ─────────────────────────────────

REWRITE_SYSTEM = """\
You are an animation director for a sprite sheet pipeline.
Given a character concept, return exactly two sections:

CHARACTER: vivid appearance description -- body type, shape, colors,
surface texture, silhouette, art style (mixed media collage paper cutout).

CHOREOGRAPHY: a 4-beat continuous walk cycle animation loop. Each beat = one
cell in a 2x2 grid (top-left, top-right, bottom-left, bottom-right).
Last beat loops seamlessly back to first.
Describe body position, weight distribution, limb placement per beat.

Rules: no numbers, no mention of grids/pixels/frames/sprites.
Write as if directing a real actor through mocap.
Keep motions simple and natural -- this is a small game sprite."""


def _llm_rewrite_sync(subject: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client()
    response = client.models.generate_content(
        model=TEXT_MODEL,
        contents=f"Design the character and choreograph a walk cycle for: {subject}",
        config=types.GenerateContentConfig(
            system_instruction=REWRITE_SYSTEM,
            temperature=0.7,
        ),
    )
    return response.text


# ── Image generation ───────────────────────────────────────────────────


def _ensure_png(data: bytes) -> bytes:
    if data[:4] == b"\x89PNG":
        return data
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _call_gemini(
    contents: list,
    system_instruction: str | None = None,
    response_modalities: list[str] | None = None,
    size: str = "1K",
) -> bytes:
    from google import genai
    from google.genai import types

    client = genai.Client()
    config_kwargs: dict = {
        "response_modalities": response_modalities or ["IMAGE"],
        "image_config": types.ImageConfig(image_size=size, aspect_ratio="1:1"),
    }
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction

    response = client.models.generate_content(
        model=IMAGE_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(**config_kwargs),
    )
    if response.parts is None:
        reason = "unknown"
        if response.candidates and response.candidates[0].finish_reason:
            reason = str(response.candidates[0].finish_reason)
        raise ValueError(f"Blocked: {reason}")
    for part in response.parts:
        if part.inline_data is not None:
            return _ensure_png(part.inline_data.data)
    raise ValueError("No image in response")


def _make_part(data: bytes):
    from google.genai import types
    return types.Part.from_bytes(data=data, mime_type="image/png")


# ── Frame slicing + bg removal ─────────────────────────────────────────


def slice_sheet(img: Image.Image, grid: int) -> list[Image.Image]:
    """Slice a spritesheet into individual frames, cropping grid line margins."""
    w, h = img.size
    cell_w, cell_h = w // grid, h // grid
    margin = 4  # crop grid line artifacts
    frames = []
    for row in range(grid):
        for col in range(grid):
            x0 = col * cell_w + margin
            y0 = row * cell_h + margin
            x1 = (col + 1) * cell_w - margin
            y1 = (row + 1) * cell_h - margin
            frames.append(img.crop((x0, y0, x1, y1)))
    return frames


_bg_cache: dict[str, object] = {}


def _remove_bg_cached(image_bytes: bytes) -> bytes:
    try:
        import torch
        from torchvision import transforms
        from transformers import AutoModelForImageSegmentation

        if "model" not in _bg_cache:
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            model = AutoModelForImageSegmentation.from_pretrained(
                "ZhengPeng7/BiRefNet", trust_remote_code=True,
            )
            model.to(device).eval()
            if device.type == "cuda":
                model.half()
            transform = transforms.Compose([
                transforms.Resize((1024, 1024)),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ])
            _bg_cache["model"] = model
            _bg_cache["device"] = device
            _bg_cache["transform"] = transform
            print(f"  BiRefNet loaded on {device}")

        model, device, transform = _bg_cache["model"], _bg_cache["device"], _bg_cache["transform"]
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        orig_size = img.size
        input_tensor = transform(img).unsqueeze(0).to(device)  # type: ignore[union-attr]
        if device.type == "cuda":  # type: ignore[union-attr]
            input_tensor = input_tensor.half()
        with torch.no_grad():
            preds = model(input_tensor)[-1].sigmoid().cpu()  # type: ignore[union-attr]
        mask = transforms.ToPILImage()(preds[0].squeeze())
        mask = mask.resize(orig_size, Image.Resampling.LANCZOS)
        result = img.convert("RGBA")
        result.putalpha(mask)
        buf = io.BytesIO()
        result.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        from rembg import remove
        return remove(image_bytes, alpha_matting=True)


def _crop_and_fit(img: Image.Image, target: int = 512) -> Image.Image:
    bbox = img.getbbox()
    if bbox is None:
        return Image.new("RGBA", (target, target), (0, 0, 0, 0))
    cropped = img.crop(bbox)
    max_ext = int(target * 0.9)
    w, h = cropped.size
    scale = min(max_ext / w, max_ext / h)
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    resized = cropped.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (target, target), (0, 0, 0, 0))
    canvas.paste(resized, ((target - nw) // 2, (target - nh) // 2))
    return canvas


# ── Strategy definitions ───────────────────────────────────────────────


@dataclass
class Strategy:
    id: str
    name: str
    description: str
    grid: int  # 2 or 4


@dataclass
class StrategyResult:
    strategy: Strategy
    prompt: str = ""
    sheet_path: str = ""
    frame_paths: list[str] = field(default_factory=list)
    timing_s: float = 0.0
    error: str | None = None
    extra: str = ""  # LLM rewrite text, etc.


STRATEGIES = [
    Strategy(
        "A_identical_2x2",
        "IDENTICAL constraint (2x2)",
        "Per-frame descriptions with IDENTICAL/CRITICAL markers. No template. Round 6/7 style.",
        grid=2,
    ),
    Strategy(
        "B_llm_choreo_2x2",
        "LLM choreography (2x2)",
        "LLM rewrites into CHARACTER + CHOREOGRAPHY, wrapped in strict requirements. Round 3 style.",
        grid=2,
    ),
    Strategy(
        "C_template_4x4",
        "Template-guided (4x4)",
        "4x4 numbered template image + system instruction. 16 frames for smoother animation.",
        grid=4,
    ),
    Strategy(
        "D_template_2x2",
        "Template-guided (2x2)",
        "2x2 numbered template image + system instruction. 4 frames.",
        grid=2,
    ),
    Strategy(
        "E_textimg_identical",
        "TEXT+IMAGE modality (2x2)",
        "Same as A but with response_modalities=[TEXT, IMAGE] so model reasons before drawing.",
        grid=2,
    ),
]


# ── Strategy execution ─────────────────────────────────────────────────


IDENTICAL_PROMPT_2x2 = (
    f"2x2 grid sprite sheet with 4 animation frames of a walk cycle, "
    f"each frame centered in its quadrant. "
    f"{CHARACTER}. "
    f"Frame 1 (top-left): standing with legs in wide stride, one leg forward one leg back, arms counterbalanced. "
    f"Frame 2 (top-right): IDENTICAL character, legs passing through center close together, "
    f"body at tallest point, arms at sides. "
    f"Frame 3 (bottom-left): IDENTICAL character, legs in wide stride again but opposite leg now leading, "
    f"arms counterbalanced opposite to frame 1. "
    f"Frame 4 (bottom-right): IDENTICAL character, legs passing through center again, "
    f"mirror of frame 2. "
    f"CRITICAL: the ONLY difference between frames is leg and arm positions for walking. "
    f"Same character, same size, same head, same backpack, same boots, same style in every frame. "
    f"Solid {BG} background, no text, no labels."
)

STRICT_REQ_2x2 = """\
STRICT TECHNICAL REQUIREMENTS:

FORMAT: A single image containing a two-by-two grid of equally sized cells.
Every cell must be the exact same dimensions, perfectly aligned, with no gaps or overlap.

FORBIDDEN: Absolutely no text, no numbers, no letters, no digits, no labels,
no watermarks, no signatures, no UI elements anywhere in the image.

CONSISTENCY: The exact same single character must appear in every cell.
Same proportions, same art style, same level of detail, same camera angle throughout.
Side view facing right. Full body visible head to toe in every cell.
Strong clean silhouette against a plain solid flat-color background ({bg}).

ANIMATION FLOW: The cells read left-to-right, top-to-bottom, like reading a page.
Each cell shows the next moment in the movement. The very last cell loops back
seamlessly to the very first cell.

MOTION QUALITY: Show real weight and physics. Arms counterbalance legs.
Never repeat the same pose twice in a row.

CHARACTER AND ANIMATION DIRECTION:
{choreography}"""

TEMPLATE_WALK_2x2 = (
    f"{CHARACTER}, walking in a 4-frame walk cycle loop. "
    f"Cell 1: stride pose, one leg forward one back, arms counterbalanced. "
    f"Cell 2: passing pose, legs close together, body upright. "
    f"Cell 3: stride pose opposite leg leading, arms swapped. "
    f"Cell 4: passing pose again, completing the loop. "
    f"Same character in every cell. Full body, head to toe. "
    f"Solid {BG} background."
)

TEMPLATE_WALK_4x4 = (
    f"{CHARACTER}, walking in a 16-frame walk cycle loop. "
    f"Cells 1-4 (row 1): right stride contact through to passing pose. "
    f"Cells 5-8 (row 2): passing pose through to left stride contact. "
    f"Cells 9-12 (row 3): left stride contact through to passing pose. "
    f"Cells 13-16 (row 4): passing pose back to right stride contact, completing the loop. "
    f"Same character in every cell. Smooth gradual transitions between poses. "
    f"Full body, head to toe. Solid {BG} background."
)


_sem: asyncio.Semaphore | None = None


async def run_strategy(strategy: Strategy) -> StrategyResult:
    assert _sem is not None
    result = StrategyResult(strategy=strategy)
    print(f"\n  [{strategy.id}] {strategy.name}")
    print(f"  {strategy.description}")
    t0 = time.monotonic()

    try:
        if strategy.id == "A_identical_2x2":
            result.prompt = IDENTICAL_PROMPT_2x2
            async with _sem:
                raw = await asyncio.to_thread(_call_gemini, [IDENTICAL_PROMPT_2x2])

        elif strategy.id == "B_llm_choreo_2x2":
            print("    LLM rewriting choreography...")
            rewrite = await asyncio.to_thread(
                _llm_rewrite_sync,
                "a human adventurer with a backpack and boots, walking",
            )
            result.extra = rewrite
            print(f"    Rewrite: {rewrite[:200]}...")
            full_prompt = STRICT_REQ_2x2.format(bg=BG, choreography=rewrite)
            result.prompt = full_prompt
            async with _sem:
                raw = await asyncio.to_thread(_call_gemini, [full_prompt])

        elif strategy.id == "C_template_4x4":
            template_bytes = make_template(4)
            result.prompt = TEMPLATE_WALK_4x4
            sys_instr = template_system_instruction(4)
            async with _sem:
                raw = await asyncio.to_thread(
                    _call_gemini,
                    [_make_part(template_bytes), TEMPLATE_WALK_4x4],
                    system_instruction=sys_instr,
                )

        elif strategy.id == "D_template_2x2":
            template_bytes = make_template(2)
            result.prompt = TEMPLATE_WALK_2x2
            sys_instr = template_system_instruction(2)
            async with _sem:
                raw = await asyncio.to_thread(
                    _call_gemini,
                    [_make_part(template_bytes), TEMPLATE_WALK_2x2],
                    system_instruction=sys_instr,
                )

        elif strategy.id == "E_textimg_identical":
            result.prompt = IDENTICAL_PROMPT_2x2
            async with _sem:
                raw = await asyncio.to_thread(
                    _call_gemini,
                    [IDENTICAL_PROMPT_2x2],
                    response_modalities=["TEXT", "IMAGE"],
                )

        else:
            raise ValueError(f"Unknown strategy: {strategy.id}")

        # Save raw sheet
        subdir = OUTPUT_DIR / strategy.id
        subdir.mkdir(parents=True, exist_ok=True)
        sheet_path = subdir / "sheet.png"
        sheet_path.write_bytes(raw)
        result.sheet_path = f"{strategy.id}/sheet.png"
        print(f"    Sheet saved")

        # Slice into frames and process each
        sheet_img = Image.open(io.BytesIO(raw)).convert("RGBA")
        frames = slice_sheet(sheet_img, strategy.grid)
        print(f"    Sliced into {len(frames)} frames, removing backgrounds...")

        for i, frame in enumerate(frames):
            buf = io.BytesIO()
            frame.save(buf, format="PNG")
            frame_bytes = buf.getvalue()

            bg_removed = await asyncio.to_thread(_remove_bg_cached, frame_bytes)
            processed = Image.open(io.BytesIO(bg_removed)).convert("RGBA")
            processed = _crop_and_fit(processed)

            out_buf = io.BytesIO()
            processed.save(out_buf, format="PNG")
            frame_path = subdir / f"frame_{i+1:02d}.png"
            frame_path.write_bytes(out_buf.getvalue())
            result.frame_paths.append(f"{strategy.id}/frame_{i+1:02d}.png")

        result.timing_s = round(time.monotonic() - t0, 2)
        print(f"    Done ({result.timing_s:.1f}s, {len(frames)} frames)")

    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"
        result.timing_s = round(time.monotonic() - t0, 2)
        print(f"    FAILED: {result.error}")

    return result


# ── Dashboard ──────────────────────────────────────────────────────────


def generate_dashboard(results: list[StrategyResult]) -> str:
    strats_json = []
    for r in results:
        strats_json.append({
            "id": r.strategy.id,
            "name": r.strategy.name,
            "description": r.strategy.description,
            "grid": r.strategy.grid,
            "sheet": r.sheet_path,
            "frames": r.frame_paths,
            "timing_s": r.timing_s,
            "error": r.error,
            "prompt": r.prompt[:500],
            "extra": r.extra[:500] if r.extra else "",
        })

    data_json = json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "image_model": IMAGE_MODEL,
        "character": CHARACTER,
        "strategies": strats_json,
    }, indent=2)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Spritesheet Walk Comparison</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #1a1a2e; color: #e0e0e0;
    font-family: 'Segoe UI', system-ui, sans-serif; padding: 24px;
  }}
  h1 {{ font-size: 22px; margin-bottom: 4px; color: #fff; }}
  h2 {{ font-size: 15px; color: #9ecfff; margin-bottom: 2px; }}
  .meta {{ font-size: 12px; color: #888; margin-bottom: 20px; }}
  .meta span {{ color: #aaa; }}

  .controls {{
    display: flex; gap: 16px; align-items: center;
    margin-bottom: 20px; padding: 10px 16px;
    background: #16213e; border: 1px solid #2a2a4a; border-radius: 8px;
  }}
  .controls label {{ font-size: 13px; color: #888; }}
  .controls input[type=range] {{ width: 120px; }}
  .controls .val {{ font-size: 13px; color: #fff; min-width: 30px; }}

  .strategy-card {{
    background: #16213e; border: 1px solid #2a2a4a; border-radius: 10px;
    padding: 16px; margin-bottom: 16px;
  }}
  .strategy-header {{
    display: flex; align-items: baseline; gap: 10px; margin-bottom: 2px;
  }}
  .strategy-desc {{ font-size: 11px; color: #777; margin-bottom: 10px; }}
  .strategy-timing {{ font-size: 11px; color: #555; margin-left: auto; }}

  .strategy-body {{
    display: flex; gap: 16px; align-items: flex-start;
  }}

  .sheet-col {{ flex-shrink: 0; text-align: center; }}
  .sheet-col img {{
    width: 200px; height: 200px;
    border: 1px solid #333; border-radius: 4px;
    cursor: pointer;
  }}
  .sheet-col .label {{
    font-size: 10px; color: #555; margin-top: 4px;
  }}

  .anim-col {{
    display: flex; flex-direction: column; gap: 8px; align-items: center;
  }}
  .anim-preview {{
    cursor: pointer; position: relative;
  }}
  .anim-preview canvas {{
    border: 1px solid #333; border-radius: 4px;
  }}
  .anim-preview .pause-overlay {{
    position: absolute; top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    font-size: 24px; color: rgba(255,255,255,0.5);
    pointer-events: none; display: none;
  }}
  .anim-preview.paused .pause-overlay {{ display: block; }}
  .anim-label {{ font-size: 10px; color: #555; }}

  .checker {{
    background-image:
      linear-gradient(45deg, #252535 25%, transparent 25%),
      linear-gradient(-45deg, #252535 25%, transparent 25%),
      linear-gradient(45deg, transparent 75%, #252535 75%),
      linear-gradient(-45deg, transparent 75%, #252535 75%);
    background-size: 16px 16px;
    background-position: 0 0, 0 8px, 8px -8px, -8px 0;
    border: 1px solid #333; border-radius: 4px;
    display: inline-block;
  }}

  .frames-strip {{
    display: flex; gap: 4px; flex-wrap: wrap; align-items: center;
  }}
  .frame-thumb {{
    cursor: pointer;
  }}
  .frame-thumb img {{
    width: 56px; height: 56px;
    border: 2px solid transparent; border-radius: 3px;
    transition: border-color 0.15s;
  }}
  .frame-thumb img:hover {{ border-color: #5588cc; }}
  .frame-thumb.active img {{
    border-color: #5588cc;
    box-shadow: 0 0 6px rgba(85,136,204,0.4);
  }}

  details {{ margin-top: 8px; }}
  summary {{ font-size: 11px; color: #666; cursor: pointer; }}
  .prompt-text {{
    font-size: 10px; color: #777; margin: 6px 0;
    white-space: pre-wrap; word-break: break-word;
    padding: 8px; background: #0a0f1e; border-radius: 4px;
    max-height: 200px; overflow-y: auto;
  }}

  .error-banner {{
    background: #2a1520; border: 1px solid #4a2030;
    color: #f08080; padding: 8px 12px; border-radius: 6px;
    font-size: 12px;
  }}
</style>
</head>
<body>

<h1>Spritesheet Walk Comparison</h1>
<div class="meta">
  Character: <span>{CHARACTER[:60]}...</span> |
  Model: <span id="m"></span> |
  <span id="t"></span>
</div>

<div class="controls">
  <label>FPS:</label>
  <input type="range" id="fps" min="1" max="12" value="4">
  <span class="val" id="fv">4</span>
  <label style="margin-left:12px">Click animation to pause</label>
</div>

<div id="sc"></div>

<script>
const D = {data_json};
let fps = 4;
const anims = [];

document.getElementById('m').textContent = D.image_model;
document.getElementById('t').textContent = new Date(D.generated_at).toLocaleString();
document.getElementById('fps').addEventListener('input', e => {{
  fps = parseInt(e.target.value);
  document.getElementById('fv').textContent = fps;
}});

const sc = document.getElementById('sc');

D.strategies.forEach((strat, si) => {{
  const card = document.createElement('div');
  card.className = 'strategy-card';
  const aid = `a${{si}}`;

  if (strat.error) {{
    card.innerHTML = `
      <div class="strategy-header">
        <h2>${{strat.name}}</h2>
        <span class="strategy-timing">${{strat.timing_s}}s</span>
      </div>
      <div class="strategy-desc">${{strat.description}}</div>
      <div class="error-banner">${{strat.error}}</div>`;
    sc.appendChild(card);
    return;
  }}

  let thumbsHtml = '';
  strat.frames.forEach((f, fi) => {{
    thumbsHtml += `
      <div class="frame-thumb" data-a="${{aid}}" data-f="${{fi}}">
        <div class="checker">
          <img src="${{f}}" alt="f${{fi+1}}" onerror="this.style.opacity=0.2">
        </div>
      </div>`;
  }});

  let extraHtml = '';
  if (strat.extra) {{
    extraHtml = `
      <details><summary>LLM Rewrite</summary>
        <div class="prompt-text">${{strat.extra}}</div>
      </details>`;
  }}

  card.innerHTML = `
    <div class="strategy-header">
      <h2>${{strat.name}}</h2>
      <span class="strategy-timing">${{strat.timing_s}}s | ${{strat.grid}}x${{strat.grid}} (${{strat.frames.length}} frames)</span>
    </div>
    <div class="strategy-desc">${{strat.description}}</div>
    <div class="strategy-body">
      <div class="sheet-col">
        <a href="${{strat.sheet}}" target="_blank">
          <img src="${{strat.sheet}}" alt="sheet">
        </a>
        <div class="label">Raw sheet (click to enlarge)</div>
      </div>
      <div class="anim-col">
        <div class="anim-preview" id="${{aid}}-p">
          <div class="checker">
            <canvas id="${{aid}}-c" width="128" height="128"></canvas>
          </div>
          <div class="pause-overlay">||</div>
        </div>
        <div class="anim-label">Animated preview</div>
      </div>
      <div class="frames-strip">${{thumbsHtml}}</div>
    </div>
    <details><summary>Prompt</summary>
      <div class="prompt-text">${{strat.prompt}}</div>
    </details>
    ${{extraHtml}}`;
  sc.appendChild(card);

  const imgs = strat.frames.map(f => {{
    const img = new window.Image(); img.src = f; return img;
  }});
  const st = {{ id: aid, fi: 0, paused: false, images: imgs, loaded: false }};
  if (imgs.length > 0) imgs[0].onload = () => {{ st.loaded = true; }};
  anims.push(st);

  document.getElementById(`${{aid}}-p`).addEventListener('click', () => {{
    st.paused = !st.paused;
    document.getElementById(`${{aid}}-p`).classList.toggle('paused', st.paused);
  }});
}});

document.querySelectorAll('.frame-thumb').forEach(t => {{
  t.addEventListener('click', e => {{
    e.stopPropagation();
    const aid = t.dataset.a, fi = parseInt(t.dataset.f);
    const st = anims.find(a => a.id === aid);
    if (st) {{
      st.fi = fi; st.paused = true;
      document.getElementById(`${{aid}}-p`).classList.add('paused');
      draw(st);
    }}
  }});
}});

function draw(st) {{
  const c = document.getElementById(`${{st.id}}-c`);
  if (!c) return;
  const ctx = c.getContext('2d');
  ctx.clearRect(0, 0, c.width, c.height);
  const img = st.images[st.fi % st.images.length];
  if (img && img.complete && img.naturalWidth > 0)
    ctx.drawImage(img, 0, 0, c.width, c.height);
  document.querySelectorAll(`[data-a="${{st.id}}"]`).forEach((t, i) =>
    t.classList.toggle('active', i === st.fi % st.images.length));
}}

let last = 0;
function loop(ts) {{
  if (ts - last >= 1000/fps) {{
    last = ts;
    anims.forEach(st => {{
      if (!st.paused && st.loaded && st.images.length > 0) {{
        st.fi = (st.fi + 1) % st.images.length;
        draw(st);
      }}
    }});
  }}
  requestAnimationFrame(loop);
}}
requestAnimationFrame(loop);
setTimeout(() => anims.forEach(draw), 500);
</script>
</body>
</html>"""


# ── Main ───────────────────────────────────────────────────────────────


async def main() -> None:
    global _sem
    _sem = asyncio.Semaphore(CONCURRENCY)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Save templates for reference
    for g in (2, 4):
        tb = make_template(g)
        (OUTPUT_DIR / f"template_{g}x{g}.png").write_bytes(tb)

    print("Spritesheet Walk Comparison")
    print(f"  {len(STRATEGIES)} strategies")
    print(f"  Character: {CHARACTER[:60]}...")
    print(f"  Image model: {IMAGE_MODEL}")
    print(f"  Output: {OUTPUT_DIR}\n")

    t0 = time.monotonic()

    results: list[StrategyResult] = []
    for strategy in STRATEGIES:
        sr = await run_strategy(strategy)
        results.append(sr)

    wall = time.monotonic() - t0

    dashboard = generate_dashboard(results)
    (OUTPUT_DIR / "dashboard.html").write_text(dashboard, encoding="utf-8")

    ok = sum(1 for r in results if not r.error)
    print(f"\n{'='*60}")
    print(f"DONE in {wall:.0f}s — {ok}/{len(results)} strategies succeeded")
    print(f"Dashboard: {OUTPUT_DIR / 'dashboard.html'}")


if __name__ == "__main__":
    asyncio.run(main())
