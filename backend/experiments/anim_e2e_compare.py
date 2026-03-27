#!/usr/bin/env python3
"""End-to-end animation test: LLM prompt creator → image generation.

4 prompt strategies × 4 characters = 16 sprite sheets.
Each strategy generates cell descriptions via text LLM, then those
get assembled into the proven template prompt and sent to image gen.

Usage:
    uv run python -m experiments.anim_e2e_compare
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

OUTPUT_DIR = SCRIPT_DIR / "output" / "anim_e2e"
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gemini-3.1-flash-image-preview")
TEXT_MODEL = "gemini-3.1-flash-lite-preview"


# ── Characters ─────────────────────────────────────────────────────────

CHARACTERS = [
    {
        "id": "knight",
        "desc": "a knight in plate armor with a sword and red cape",
        "appearance": (
            "A knight in full silver plate armor with a closed visor helmet, "
            "red cape flowing behind, brown leather belt with a sheathed sword, "
            "steel gauntlets and greaves."
        ),
    },
    {
        "id": "slime",
        "desc": "a cheerful green slime blob with big eyes",
        "appearance": (
            "A cheerful bright green slime blob with a rounded dome shape, "
            "two large oval white eyes with black pupils near the top, "
            "a small open smile, slightly translucent body with a subtle shine."
        ),
    },
    {
        "id": "wolf",
        "desc": "a grey wolf",
        "appearance": (
            "A grey wolf with thick fur, pointed ears, a bushy tail, "
            "yellow eyes, dark grey back and lighter grey underbelly, "
            "four strong legs with dark paws."
        ),
    },
    {
        "id": "jellyfish",
        "desc": "a bioluminescent jellyfish floating in air",
        "appearance": (
            "A translucent bioluminescent jellyfish with a smooth bell-shaped "
            "dome glowing soft blue-purple, long trailing tentacles that fade "
            "to transparent at the tips, small glowing dots along the tentacles."
        ),
    },
]


# ── Prompt creator strategies (text LLM system prompts) ────────────────

STRATEGIES = [
    {
        "id": "A_minimal",
        "name": "Minimal",
        "system": (
            "Generate 4 animation frame descriptions for a 2x2 sprite sheet.\n"
            "The frames should form a looping animation cycle.\n"
            "Each description should describe the character's pose, not their appearance.\n\n"
            "Output JSON:\n"
            '{"animation_type": "short label", '
            '"animation_description": "one sentence explaining the motion", '
            '"cells": {"1": "...", "2": "...", "3": "...", "4": "..."}}'
        ),
    },
    {
        "id": "B_detailed",
        "name": "Detailed with context",
        "system": (
            "You generate animation frame descriptions for a 2D game sprite sheet.\n\n"
            "CONTEXT: A sprite sheet is a single image divided into a grid of cells. Each cell\n"
            "contains one frame of animation. A game engine displays these frames in rapid\n"
            "sequence to create movement — like a flipbook. The frames loop continuously,\n"
            "so the last frame must transition smoothly back to the first.\n\n"
            "YOUR TASK: Given a character description, determine the most natural movement\n"
            "for this type of creature, then describe 4 frames that capture one complete\n"
            "cycle of that movement. The character always faces right and moves toward the\n"
            "right edge of the frame.\n\n"
            "FRAME DESCRIPTION RULES:\n"
            "- Each description must be SELF-CONTAINED — it will be used independently to\n"
            "  generate an image. Do not reference other frames.\n"
            "- Describe the POSE: body shape, limb positions, height, compression/extension.\n"
            "- Do not describe color, texture, or art style — only the physical pose.\n"
            "- Use directional language relative to the image: \"toward the right edge\" means\n"
            "  forward, \"toward the left edge\" means backward.\n"
            "- Describe what makes each frame VISUALLY DISTINCT from the others.\n"
            "- Keep each description to 2-3 sentences.\n\n"
            "Output JSON only, no markdown:\n"
            '{"animation_type": "walk|bounce|slither|float|hop|crawl|etc", '
            '"animation_description": "explanation of the motion cycle", '
            '"cells": {"1": "...", "2": "...", "3": "...", "4": "..."}}'
        ),
    },
    {
        "id": "C_taxonomy",
        "name": "Movement taxonomy",
        "system": (
            "You generate animation frame descriptions for a 2D game sprite sheet.\n\n"
            "A sprite sheet is a grid of animation frames displayed in sequence to create\n"
            "movement. You are generating 4 frames that loop seamlessly. The character\n"
            "faces right and moves rightward.\n\n"
            "STEP 1 — Determine the movement type from the character's body plan:\n"
            "- BIPEDAL WALK: humanoids, birds on ground — alternating leg strides\n"
            "- QUADRUPED WALK: four-legged animals — diagonal leg pair alternation\n"
            "- BOUNCE: blobs, slimes, balls — squash flat on ground, stretch tall in air\n"
            "- SLITHER: snakes, worms — S-curve body shifts forward along the ground\n"
            "- FLOAT/BOB: ghosts, wisps, jellyfish — vertical oscillation, trailing elements\n"
            "- HOP: frogs, small birds — crouch, leap, airborne, land\n"
            "- CRAWL: spiders, insects, crabs — low body, many legs ripple in waves\n"
            "- WADDLE: penguins, mushroom creatures, short-legged — body rocks side to side\n\n"
            "STEP 2 — Describe 4 frames that capture one complete cycle.\n\n"
            "RULES:\n"
            "- Each frame description is SELF-CONTAINED — never reference other frames.\n"
            "- Describe the POSE only, not color or style.\n"
            "- Each frame must be VISUALLY DISTINCT.\n"
            "- Use \"toward the right edge\" for forward, \"toward the left edge\" for backward.\n"
            "- 2-3 sentences per frame.\n\n"
            "Output JSON only:\n"
            '{"animation_type": "type from list above", '
            '"animation_description": "one sentence explaining the cycle", '
            '"cells": {"1": "...", "2": "...", "3": "...", "4": "..."}}'
        ),
    },
    {
        "id": "D_img_aware_v2",
        "name": "Image-gen aware v2",
        "system": (
            "You write pose descriptions for an AI image generator that will produce a\n"
            "2x2 sprite sheet — 4 animation frames in a single image. All 4 descriptions\n"
            "are sent TOGETHER in one prompt, so you CAN reference relationships between\n"
            "cells (e.g. 'mirror of Cell 1 with opposite limbs').\n\n"

            "HOW THE IMAGE GENERATOR WORKS:\n"
            "- It is best at varying the overall SILHOUETTE SHAPE between cells\n"
            "- It struggles with 'left leg' vs 'right leg' in side view — these are\n"
            "  ambiguous. Instead use: 'the leading leg' (toward right edge), 'the\n"
            "  trailing leg' (toward left edge), 'the OTHER leg', or describe the\n"
            "  silhouette shape ('legs wide apart' vs 'legs close together')\n"
            "- It sometimes flips the character direction — explicitly state 'facing\n"
            "  right' and 'toward the right edge' in EVERY cell description\n"
            "- It sometimes makes all 4 cells look the same — you must describe what\n"
            "  is VISUALLY DIFFERENT about each cell's silhouette\n\n"

            "YOUR TASK:\n"
            "1. Determine the movement type from the character's body plan\n"
            "2. Write 4 pose descriptions that form a looping cycle\n"
            "3. Write a frame_pattern that summarizes the visual contrast between frames\n"
            "   (this gets inserted into the consistency rules the image generator sees)\n\n"

            "POSE DESCRIPTION RULES:\n"
            "- Describe the BODY HEIGHT in each frame (low/compressed vs tall/stretched)\n"
            "- Describe the SILHOUETTE WIDTH (wide/spread vs narrow/compact)\n"
            "- Use screen-space directions: 'toward the right edge' = forward,\n"
            "  'toward the left edge' = backward\n"
            "- NEVER say 'left leg' or 'right leg' — say 'leading leg', 'trailing leg',\n"
            "  'the OTHER leg', or describe the shape\n"
            "- State relationships: 'same wide stride as Cell 1 but the OTHER leg leads'\n"
            "- Mention follow-through elements (capes trailing, tentacles dragging, etc)\n"
            "- 2-3 sentences per cell\n"
            "- Do NOT describe color, texture, or art style — only the pose\n\n"

            "FRAME PATTERN EXAMPLES:\n"
            "- Walk: 'Cells 1 and 3 show wide strides (legs apart, body low). "
            "Cells 2 and 4 show compact passing poses (legs together, body tall).'\n"
            "- Bounce: 'Cells 1 and 3 show squashed flat shapes (wide, low). "
            "Cells 2 and 4 show stretched tall shapes (narrow, high).'\n"
            "- Float: 'The body rises and falls across cells. Trailing elements "
            "change angle with each position.'\n\n"

            "Output JSON only:\n"
            "{\n"
            '  "animation_type": "walk|bounce|slither|float|hop|crawl|etc",\n'
            '  "animation_description": "2-3 sentences explaining the full motion cycle,'
            " what drives it, and why it suits this character\",\n"
            '  "frame_pattern": "1-2 sentences describing the visual contrast pattern'
            ' between the 4 cells",\n'
            '  "cells": {"1": "...", "2": "...", "3": "...", "4": "..."}\n'
            "}"
        ),
    },
]


# ── Image generation system instruction (generalized from real_walk_ref_test) ──

IMAGE_SYS_INSTR = (
    "You are creating a sprite sheet for a 2D video game. A sprite sheet is "
    "a single image containing multiple frames of a character animation, "
    "arranged in a grid. Game engines display these frames in rapid sequence "
    "to create the illusion of movement — like a flipbook.\n\n"

    "You are generating a looping animation cycle. The animation repeats "
    "seamlessly — the last frame connects back to the first frame. "
    "The character faces toward the RIGHT side of the image in every frame.\n\n"

    "LAYOUT: The attached template image shows the exact grid layout to follow. "
    "It is a 2x2 grid with 4 equal cells separated by red lines, numbered 1-4. "
    "Cell 1 is top-left, Cell 2 is top-right, Cell 3 is bottom-left, Cell 4 is "
    "bottom-right. Replace each numbered cell with the corresponding animation "
    "frame as described in the prompt.\n\n"

    "RULES:\n"
    "- Keep the red grid lines in place to separate the cells\n"
    "- Center the character within each cell — do not let the character "
    "cross into adjacent cells\n"
    "- Fill all empty space around the character with a flat solid background color\n"
    "- The character must look identical across all 4 cells — same proportions, "
    "same colors, same art style. Only the pose changes between cells.\n"
    "- Do not draw the numbered circles from the template\n"
    "- Do not include any text, numbers, labels, or watermarks in the output"
)

def build_defensive_reqs(frame_pattern: str = "") -> str:
    pattern_line = ""
    if frame_pattern:
        pattern_line = f" {frame_pattern}"
    return (
        "\n\nCRITICAL CONSISTENCY RULES:\n"
        "- The character faces toward the RIGHT edge of the image in ALL FOUR cells. "
        "The character is moving to the right. No cell should show the character "
        "facing left or turning around.\n"
        "- Every cell must show a VISIBLY DIFFERENT pose from the others."
        f"{pattern_line} "
        "If two cells look the same, the animation will not work.\n"
        "- The character's face, body shape, clothing, colors, and art style must be "
        "IDENTICAL in all four cells. The only thing that changes between cells is "
        "the pose.\n"
        "- The character's full body must be visible from head to feet in every cell, "
        "centered within the cell boundaries."
    )


# ── Helpers ────────────────────────────────────────────────────────────

_client_instance = None


def _get_client():
    global _client_instance
    if _client_instance is None:
        from google import genai
        _client_instance = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    return _client_instance


def _ensure_png(data: bytes) -> bytes:
    if data[:4] == b"\x89PNG":
        return data
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_part(data: bytes):
    from google.genai import types
    return types.Part.from_bytes(data=data, mime_type="image/png")


def make_template_2x2() -> bytes:
    size, grid, cell = 1024, 2, 512
    img = Image.new("RGB", (size, size), "#1a1a1a")
    draw = ImageDraw.Draw(img)
    lc = "#ff0000"
    draw.line([(cell, 0), (cell, size - 1)], fill=lc, width=2)
    draw.line([(0, cell), (size - 1, cell)], fill=lc, width=2)
    draw.rectangle([0, 0, size - 1, size - 1], outline=lc, width=2)
    font = ImageFont.load_default(size=48)
    for row in range(grid):
        for col in range(grid):
            num = row * grid + col + 1
            cx, cy = col * cell + cell // 2, row * cell + cell // 2
            r = 40
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill="#fff", outline=lc, width=2)
            label = str(num)
            bbox = draw.textbbox((0, 0), label, font=font)
            tw = bbox[2] - bbox[0]
            draw.text((cx - tw // 2, cy - bbox[1] // 2 - bbox[1]), label, fill="#000", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── Text LLM: generate cell descriptions ───────────────────────────────


def generate_cells(system_prompt: str, character_desc: str) -> dict:
    from google.genai import types

    response = _get_client().models.generate_content(
        model=TEXT_MODEL,
        contents=f"Character: {character_desc}",
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.7,
            response_mime_type="application/json",
        ),
    )
    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3].strip()
    return json.loads(text)


# ── Image gen: assemble prompt and generate sheet ──────────────────────


def build_image_prompt(appearance: str, anim_data: dict) -> str:
    anim_type = anim_data.get("animation_type", "animation")
    anim_desc = anim_data.get("animation_description", "")
    cells = anim_data.get("cells", {})
    frame_pattern = anim_data.get("frame_pattern", "")

    defensive = build_defensive_reqs(frame_pattern)

    prompt = (
        f"CHARACTER: {appearance} The character is shown in side view, "
        f"facing right, moving toward the right edge of the image. "
        f"Mixed media collage style paper cutout art, flat lighting, clean edges.\n\n"

        f"ANIMATION: Generate a 4-frame {anim_type} cycle for this character. "
        f"{anim_desc}\n\n"

        f"THE FOUR FRAMES:\n"
        f"Cell 1: {cells.get('1', '')}\n\n"
        f"Cell 2: {cells.get('2', '')}\n\n"
        f"Cell 3: {cells.get('3', '')}\n\n"
        f"Cell 4: {cells.get('4', '')}\n"

        f"{defensive}\n\n"
        f"Flat solid background color in every cell."
    )
    return prompt


def generate_sheet(template_bytes: bytes, prompt: str) -> bytes:
    from google.genai import types

    response = _get_client().models.generate_content(
        model=IMAGE_MODEL,
        contents=[_make_part(template_bytes), prompt],
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(image_size="1K", aspect_ratio="1:1"),
            system_instruction=IMAGE_SYS_INSTR,
        ),
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


# ── Bg removal + frame processing ──────────────────────────────────────

_bg_cache: dict[str, object] = {}


def _remove_bg(image_bytes: bytes) -> bytes:
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
        t = transform(img).unsqueeze(0).to(device)  # type: ignore[union-attr]
        if device.type == "cuda":  # type: ignore[union-attr]
            t = t.half()
        with torch.no_grad():
            preds = model(t)[-1].sigmoid().cpu()  # type: ignore[union-attr]
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


async def process_sheet(raw_bytes: bytes, subdir: Path) -> list[str]:
    w, h = Image.open(io.BytesIO(raw_bytes)).size
    cw, ch = w // 2, h // 2
    margin = 4
    sheet_img = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
    paths = []
    for i, (row, col) in enumerate([(0, 0), (0, 1), (1, 0), (1, 1)]):
        frame = sheet_img.crop((
            col * cw + margin, row * ch + margin,
            (col + 1) * cw - margin, (row + 1) * ch - margin,
        ))
        buf = io.BytesIO()
        frame.save(buf, format="PNG")
        bg_removed = await asyncio.to_thread(_remove_bg, buf.getvalue())
        processed = Image.open(io.BytesIO(bg_removed)).convert("RGBA")
        processed = _crop_and_fit(processed)
        out_buf = io.BytesIO()
        processed.save(out_buf, format="PNG")
        frame_path = subdir / f"frame_{i + 1}.png"
        frame_path.write_bytes(out_buf.getvalue())
        paths.append(f"{subdir.name}/frame_{i + 1}.png")
    return paths


# ── Dashboard ──────────────────────────────────────────────────────────


def generate_dashboard(all_results: list[dict]) -> str:
    data_json = json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "image_model": IMAGE_MODEL,
        "text_model": TEXT_MODEL,
        "results": all_results,
    }, indent=2)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>End-to-End Animation Comparison</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #1a1a2e; color: #e0e0e0; font-family: 'Segoe UI', system-ui, sans-serif; padding: 24px; }}
  h1 {{ font-size: 22px; margin-bottom: 4px; color: #fff; }}
  h2 {{ font-size: 16px; color: #9ecfff; margin-bottom: 8px; }}
  h3 {{ font-size: 13px; color: #c0d0e0; margin-bottom: 4px; }}
  .meta {{ font-size: 12px; color: #888; margin-bottom: 20px; }}
  .controls {{ display: flex; gap: 16px; align-items: center; margin-bottom: 20px; padding: 10px 16px; background: #16213e; border: 1px solid #2a2a4a; border-radius: 8px; }}
  .controls label {{ font-size: 13px; color: #888; }}
  .controls input[type=range] {{ width: 120px; }}
  .controls .val {{ font-size: 13px; color: #fff; min-width: 30px; }}
  .char-section {{ background: #12192e; border: 1px solid #2a2a4a; border-radius: 12px; padding: 16px; margin-bottom: 20px; }}
  .variants {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 12px; }}
  .variant {{ background: #16213e; border: 1px solid #2a2a4a; border-radius: 10px; padding: 14px; }}
  .variant-header {{ display: flex; align-items: baseline; gap: 8px; margin-bottom: 4px; }}
  .variant-timing {{ font-size: 11px; color: #555; margin-left: auto; }}
  .anim-tag {{ display: inline-block; font-size: 10px; padding: 2px 6px; border-radius: 3px; background: #1b3a2a; color: #8fc; margin-bottom: 6px; }}
  .variant-body {{ display: flex; gap: 12px; align-items: flex-start; }}
  .sheet-col {{ flex-shrink: 0; text-align: center; }}
  .sheet-col img {{ width: 160px; height: 160px; border: 1px solid #333; border-radius: 4px; cursor: pointer; }}
  .sheet-col .label {{ font-size: 9px; color: #555; margin-top: 2px; }}
  .anim-col {{ display: flex; flex-direction: column; gap: 6px; align-items: center; }}
  .anim-preview {{ cursor: pointer; position: relative; }}
  .anim-preview canvas {{ border: 1px solid #333; border-radius: 4px; }}
  .anim-preview .po {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 20px; color: rgba(255,255,255,0.5); pointer-events: none; display: none; }}
  .anim-preview.paused .po {{ display: block; }}
  .checker {{ background-image: linear-gradient(45deg, #252535 25%, transparent 25%), linear-gradient(-45deg, #252535 25%, transparent 25%), linear-gradient(45deg, transparent 75%, #252535 75%), linear-gradient(-45deg, transparent 75%, #252535 75%); background-size: 16px 16px; background-position: 0 0, 0 8px, 8px -8px, -8px 0; border: 1px solid #333; border-radius: 4px; display: inline-block; }}
  .frames-strip {{ display: flex; gap: 4px; flex-wrap: wrap; }}
  .frame-cell {{ cursor: pointer; }}
  .frame-cell img {{ width: 56px; height: 56px; border: 2px solid transparent; border-radius: 3px; }}
  .frame-cell.active img {{ border-color: #5588cc; }}
  .cell-descs {{ margin-top: 6px; }}
  .cell-descs li {{ font-size: 10px; color: #999; margin-bottom: 4px; padding: 4px 6px; background: #0f1a2e; border-radius: 4px; line-height: 1.4; }}
  .cell-descs li strong {{ color: #7b8794; }}
  details {{ margin-top: 6px; }}
  summary {{ font-size: 11px; color: #666; cursor: pointer; }}
  .prompt-text {{ font-size: 9px; color: #666; margin: 4px 0; white-space: pre-wrap; word-break: break-word; padding: 6px; background: #0a0f1e; border-radius: 4px; max-height: 150px; overflow-y: auto; }}
  .error-banner {{ background: #2a1520; border: 1px solid #4a2030; color: #f08080; padding: 8px; border-radius: 6px; font-size: 12px; }}
</style>
</head>
<body>
<h1>End-to-End Animation Comparison</h1>
<div class="meta">Image: <span>{IMAGE_MODEL}</span> | Text: <span>{TEXT_MODEL}</span> | <span id="t"></span></div>
<div class="controls">
  <label>FPS:</label><input type="range" id="fps" min="1" max="8" value="4">
  <span class="val" id="fv">4</span>
</div>
<div id="sc"></div>
<script>
const D = {data_json};
let fps = 4;
const anims = [];
document.getElementById('t').textContent = new Date(D.generated_at).toLocaleString();
document.getElementById('fps').addEventListener('input', e => {{ fps = parseInt(e.target.value); document.getElementById('fv').textContent = fps; }});
const sc = document.getElementById('sc');
const groups = {{}};
D.results.forEach(r => {{ if (!groups[r.char_id]) groups[r.char_id] = {{desc: r.char_desc, results: []}}; groups[r.char_id].results.push(r); }});
Object.entries(groups).forEach(([charId, data]) => {{
  const section = document.createElement('div');
  section.className = 'char-section';
  let varHtml = '';
  data.results.forEach((v, vi) => {{
    const aid = `${{charId}}-${{vi}}`;
    if (v.error) {{
      varHtml += `<div class="variant"><div class="variant-header"><h3>${{v.strategy_name}}</h3></div><div class="error-banner">${{v.error}}</div></div>`;
      return;
    }}
    let fHtml = '';
    (v.frames || []).forEach((f, fi) => {{ fHtml += `<div class="frame-cell" data-a="${{aid}}" data-f="${{fi}}"><div class="checker"><img src="${{f}}" onerror="this.style.opacity=0.2"></div></div>`; }});
    let cellsHtml = '';
    if (v.cells) Object.entries(v.cells).forEach(([k, desc]) => {{ cellsHtml += `<li><strong>Cell ${{k}}:</strong> ${{desc}}</li>`; }});
    varHtml += `<div class="variant">
      <div class="variant-header"><h3>${{v.strategy_name}}</h3><span class="variant-timing">${{v.timing_s}}s</span></div>
      <span class="anim-tag">${{v.animation_type}}</span>
      <div class="variant-body">
        <div class="sheet-col"><a href="${{v.sheet}}" target="_blank"><img src="${{v.sheet}}"></a><div class="label">Raw sheet</div></div>
        <div class="anim-col"><div class="anim-preview" id="${{aid}}-p"><div class="checker"><canvas id="${{aid}}-c" width="120" height="120"></canvas></div><div class="po">||</div></div></div>
        <div class="frames-strip">${{fHtml}}</div>
      </div>
      <ul class="cell-descs">${{cellsHtml}}</ul>
      <details><summary>Full image prompt</summary><pre class="prompt-text">${{v.image_prompt || ''}}</pre></details>
    </div>`;
    anims.push({{ id: aid, frames: v.frames || [], fi: 0, paused: false, images: [], loaded: false }});
  }});
  section.innerHTML = `<h2>${{charId}} <span style="color:#888;font-size:13px">— ${{data.desc}}</span></h2><div class="variants">${{varHtml}}</div>`;
  sc.appendChild(section);
}});
anims.forEach(st => {{
  st.images = st.frames.map(f => {{ const i = new window.Image(); i.src = f; return i; }});
  if (st.images.length > 0) st.images[0].onload = () => {{ st.loaded = true; }};
  const pp = document.getElementById(`${{st.id}}-p`);
  if (pp) pp.addEventListener('click', () => {{ st.paused = !st.paused; pp.classList.toggle('paused', st.paused); }});
}});
document.querySelectorAll('.frame-cell').forEach(t => {{
  t.addEventListener('click', e => {{ e.stopPropagation(); const aid = t.dataset.a, fi = parseInt(t.dataset.f); const st = anims.find(a => a.id === aid); if (st) {{ st.fi = fi; st.paused = true; document.getElementById(`${{aid}}-p`).classList.add('paused'); draw(st); }} }});
}});
function draw(st) {{ const c = document.getElementById(`${{st.id}}-c`); if (!c) return; const ctx = c.getContext('2d'); ctx.clearRect(0, 0, c.width, c.height); const img = st.images[st.fi % st.images.length]; if (img && img.complete && img.naturalWidth > 0) ctx.drawImage(img, 0, 0, c.width, c.height); document.querySelectorAll(`[data-a="${{st.id}}"]`).forEach((t, i) => t.classList.toggle('active', i === st.fi % st.images.length)); }}
let last = 0;
function loop(ts) {{ if (ts - last >= 1000/fps) {{ last = ts; anims.forEach(st => {{ if (!st.paused && st.loaded && st.images.length > 0) {{ st.fi = (st.fi + 1) % st.images.length; draw(st); }} }}); }} requestAnimationFrame(loop); }}
requestAnimationFrame(loop);
setTimeout(() => anims.forEach(draw), 500);
</script>
</body>
</html>"""


# ── Main ───────────────────────────────────────────────────────────────


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    template_bytes = make_template_2x2()
    (OUTPUT_DIR / "template.png").write_bytes(template_bytes)

    total = len(STRATEGIES) * len(CHARACTERS)
    print(f"End-to-End Animation Comparison")
    print(f"  {len(STRATEGIES)} strategies x {len(CHARACTERS)} characters = {total} sheets")
    print(f"  Image model: {IMAGE_MODEL}")
    print(f"  Text model: {TEXT_MODEL}")
    print(f"  Output: {OUTPUT_DIR}\n")

    t0 = time.monotonic()
    all_results: list[dict] = []

    for char in CHARACTERS:
        print(f"\n{'='*50}")
        print(f"  {char['id']} — {char['desc']}")
        print(f"{'='*50}")

        for strat in STRATEGIES:
            result = {
                "char_id": char["id"],
                "char_desc": char["desc"],
                "strategy_id": strat["id"],
                "strategy_name": strat["name"],
                "animation_type": "",
                "animation_description": "",
                "cells": {},
                "image_prompt": "",
                "sheet": "",
                "frames": [],
                "timing_s": 0.0,
                "error": None,
            }
            t1 = time.monotonic()
            subdir = OUTPUT_DIR / f"{char['id']}_{strat['id']}"
            subdir.mkdir(parents=True, exist_ok=True)

            try:
                # Step 1: Text LLM generates cell descriptions
                print(f"  [{strat['id']}] generating cell descriptions...")
                anim_data = await asyncio.to_thread(
                    generate_cells, strat["system"], char["desc"],
                )
                result["animation_type"] = anim_data.get("animation_type", "unknown")
                result["animation_description"] = anim_data.get("animation_description", "")
                result["cells"] = anim_data.get("cells", {})
                print(f"    type: {result['animation_type']}")

                # Step 2: Assemble image prompt
                image_prompt = build_image_prompt(char["appearance"], anim_data)
                result["image_prompt"] = image_prompt

                # Step 3: Generate sprite sheet
                print(f"  [{strat['id']}] generating sheet...")
                raw = await asyncio.to_thread(generate_sheet, template_bytes, image_prompt)
                (subdir / "sheet.png").write_bytes(raw)
                result["sheet"] = f"{subdir.name}/sheet.png"

                # Step 4: Slice + bg remove
                print(f"  [{strat['id']}] processing frames...")
                result["frames"] = await process_sheet(raw, subdir)
                print(f"  [{strat['id']}] done")

            except Exception as e:
                result["error"] = f"{type(e).__name__}: {e}"
                print(f"  [{strat['id']}] FAILED: {result['error']}")

            result["timing_s"] = round(time.monotonic() - t1, 2)
            all_results.append(result)

    wall = time.monotonic() - t0

    # Save
    results_path = OUTPUT_DIR / "results.json"
    results_path.write_text(json.dumps(all_results, indent=2), encoding="utf-8")
    dashboard = generate_dashboard(all_results)
    (OUTPUT_DIR / "dashboard.html").write_text(dashboard, encoding="utf-8")

    ok = sum(1 for r in all_results if not r["error"])
    print(f"\n{'='*60}")
    print(f"DONE in {wall:.0f}s — {ok}/{total} sheets")
    print(f"Dashboard: {OUTPUT_DIR / 'dashboard.html'}")


if __name__ == "__main__":
    asyncio.run(main())
