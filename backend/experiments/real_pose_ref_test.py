#!/usr/bin/env python3
"""Test: real walk cycle as pose reference instead of stick figures.

Step 1: Generate a clean walk cycle sheet of a simple generic character
Step 2: Use that sheet as pose reference to generate 3 other characters

Usage:
    uv run python -m experiments.real_pose_ref_test
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

OUTPUT_DIR = SCRIPT_DIR / "output" / "real_pose_ref"
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gemini-3.1-flash-image-preview")
BG = "#1a1a1a"


# ── Characters ─────────────────────────────────────────────────────────

# Simple generic character to generate the reference walk cycle
REF_CHARACTER = (
    "A simple cartoon person with a round head, plain blue shirt, brown pants, "
    "and black shoes. No accessories, no hat, no backpack. Clean simple design. "
    "Side view facing right. Mixed media collage style paper cutout art, "
    "flat lighting, clean edges."
)

# Characters to test with the real pose reference
TEST_CHARACTERS = [
    {
        "id": "knight",
        "name": "knight",
        "appearance": (
            "A knight in full silver plate armor with a closed visor helmet, "
            "red cape flowing behind, brown leather belt with a sheathed sword, "
            "steel gauntlets and greaves. Side view facing right. "
            "Mixed media collage style paper cutout art, flat lighting, clean edges."
        ),
    },
    {
        "id": "goblin",
        "name": "goblin",
        "appearance": (
            "A small green-skinned goblin with large pointed ears, wearing a "
            "tattered brown leather vest, ragged shorts, and no shoes. Carrying "
            "a small wooden club. Yellow eyes, sharp teeth. Side view facing right. "
            "Mixed media collage style paper cutout art, flat lighting, clean edges."
        ),
    },
    {
        "id": "robot",
        "name": "robot",
        "appearance": (
            "A boxy retro robot with a rectangular silver body, round glowing "
            "blue eyes, accordion-style arms and legs, antenna on top, small "
            "panel buttons on chest. Side view facing right. "
            "Mixed media collage style paper cutout art, flat lighting, clean edges."
        ),
    },
]

WALK_CELL_DESCS = (
    "Cell 1 (CONTACT RIGHT): Right leg extended forward with heel near ground, "
    "left leg extended behind pushing off. Arms counterbalanced — left arm "
    "forward, right arm back. Body at lowest point of stride.\n"
    "Cell 2 (PASSING RIGHT): Weight on right leg directly under body, left leg "
    "swinging forward past the right leg. Both legs close together. Body at "
    "tallest point. Arms at sides.\n"
    "Cell 3 (CONTACT LEFT): Left leg extended forward with heel near ground, "
    "right leg extended behind pushing off. Arms counterbalanced — right arm "
    "forward, left arm back. Mirror of cell 1.\n"
    "Cell 4 (PASSING LEFT): Weight on left leg directly under body, right leg "
    "swinging forward. Both legs close together. Body at tallest point. "
    "Arms at sides. Loops back to cell 1."
)

DEFENSIVE_REQS = (
    "\n\nANIMATION REQUIREMENTS:\n"
    "- The character faces right in ALL FOUR cells.\n"
    "- Each cell shows a DISTINCTLY DIFFERENT leg position.\n"
    "- The four poses form a complete walk cycle loop.\n"
    "- The character's appearance, colors, and art style are IDENTICAL across "
    "all four cells. Only the limb positions change.\n"
    "- Full body visible from head to toe in every cell, centered."
)


# ── Template ───────────────────────────────────────────────────────────


def make_template_2x2() -> bytes:
    size, grid, cell = 1024, 2, 512
    img = Image.new("RGB", (size, size), BG)
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


def template_sys_instr(with_pose_ref: bool = False) -> str:
    base = (
        "Using the attached template image as an exact layout guide: "
        "generate a sprite sheet. "
        "The image is a 2x2 grid of 4 equal cells separated by red lines. "
        "Replace each numbered cell with the corresponding content, "
        "reading left-to-right, top-to-bottom.\n\n"
        "Rules:\n"
        "- KEEP the red grid lines exactly where they are\n"
        "- Each cell's content must be CENTERED and NOT cross into adjacent cells\n"
        f"- CRITICAL: fill ALL empty space with flat solid {BG}\n"
        "- Maintain consistent style, lighting, proportions across all 4 cells\n"
        "- Do NOT draw the numbered circles from the template\n"
        "- No text, no numbers, no labels, no watermarks anywhere"
    )
    if with_pose_ref:
        base += (
            "\n\nADDITIONAL: A second reference image shows a character performing "
            "the same walk cycle poses. Use it as a guide for the BODY POSITIONS "
            "and LIMB ANGLES in each cell — but draw a COMPLETELY DIFFERENT character "
            "as described in the prompt. Copy the poses, not the character design."
        )
    return base


# ── Gemini ─────────────────────────────────────────────────────────────

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


def _call_gemini(contents: list, system_instruction: str) -> bytes:
    from google.genai import types

    response = _get_client().models.generate_content(
        model=IMAGE_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(image_size="1K", aspect_ratio="1:1"),
            system_instruction=system_instruction,
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


# ── Bg removal ─────────────────────────────────────────────────────────

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


def slice_sheet_2x2(img: Image.Image) -> list[Image.Image]:
    w, h = img.size
    cw, ch = w // 2, h // 2
    margin = 4
    return [
        img.crop((col * cw + margin, row * ch + margin,
                  (col + 1) * cw - margin, (row + 1) * ch - margin))
        for row in range(2) for col in range(2)
    ]


async def process_sheet(raw_bytes: bytes, subdir: Path) -> list[str]:
    sheet_img = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
    frames = slice_sheet_2x2(sheet_img)
    paths = []
    for i, frame in enumerate(frames):
        buf = io.BytesIO()
        frame.save(buf, format="PNG")
        bg_removed = await asyncio.to_thread(_remove_bg, buf.getvalue())
        processed = Image.open(io.BytesIO(bg_removed)).convert("RGBA")
        processed = _crop_and_fit(processed)
        out_buf = io.BytesIO()
        processed.save(out_buf, format="PNG")
        frame_path = subdir / f"frame_{i+1}.png"
        frame_path.write_bytes(out_buf.getvalue())
        paths.append(f"{subdir.name}/frame_{i+1}.png")
    return paths


# ── Dashboard ──────────────────────────────────────────────────────────


def generate_dashboard(ref_sheet: str, ref_frames: list[str], results: list[dict]) -> str:
    data_json = json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "image_model": IMAGE_MODEL,
        "ref_sheet": ref_sheet,
        "ref_frames": ref_frames,
        "results": results,
    }, indent=2)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Real Pose Reference Test</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #1a1a2e; color: #e0e0e0;
    font-family: 'Segoe UI', system-ui, sans-serif; padding: 24px;
  }}
  h1 {{ font-size: 22px; margin-bottom: 4px; color: #fff; }}
  h2 {{ font-size: 16px; color: #9ecfff; margin-bottom: 8px; }}
  h3 {{ font-size: 14px; color: #c0d0e0; margin-bottom: 4px; }}
  .meta {{ font-size: 12px; color: #888; margin-bottom: 20px; }}
  .controls {{
    display: flex; gap: 16px; align-items: center;
    margin-bottom: 20px; padding: 10px 16px;
    background: #16213e; border: 1px solid #2a2a4a; border-radius: 8px;
  }}
  .controls label {{ font-size: 13px; color: #888; }}
  .controls input[type=range] {{ width: 120px; }}
  .controls .val {{ font-size: 13px; color: #fff; min-width: 30px; }}

  .ref-section {{
    background: #16213e; border: 1px solid #2a2a4a; border-radius: 12px;
    padding: 16px; margin-bottom: 24px;
  }}
  .ref-body {{ display: flex; gap: 16px; align-items: center; }}
  .ref-body img.sheet {{
    width: 200px; height: 200px; border: 1px solid #333; border-radius: 4px;
  }}

  .char-section {{
    background: #12192e; border: 1px solid #2a2a4a; border-radius: 12px;
    padding: 16px; margin-bottom: 20px;
  }}
  .variants {{ display: flex; gap: 16px; flex-wrap: wrap; }}
  .variant {{
    background: #16213e; border: 1px solid #2a2a4a; border-radius: 10px;
    padding: 14px; flex: 1; min-width: 380px;
  }}
  .variant-header {{
    display: flex; align-items: baseline; gap: 8px; margin-bottom: 8px;
  }}
  .variant-timing {{ font-size: 11px; color: #555; margin-left: auto; }}
  .variant-body {{ display: flex; gap: 12px; align-items: flex-start; }}

  .sheet-col {{ flex-shrink: 0; text-align: center; }}
  .sheet-col img {{
    width: 180px; height: 180px;
    border: 1px solid #333; border-radius: 4px; cursor: pointer;
  }}
  .sheet-col .label {{ font-size: 9px; color: #555; margin-top: 2px; }}

  .anim-col {{ display: flex; flex-direction: column; gap: 6px; align-items: center; }}
  .anim-preview {{ cursor: pointer; position: relative; }}
  .anim-preview canvas {{ border: 1px solid #333; border-radius: 4px; }}
  .anim-preview .po {{
    position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
    font-size: 20px; color: rgba(255,255,255,0.5); pointer-events: none; display: none;
  }}
  .anim-preview.paused .po {{ display: block; }}

  .checker {{
    background-image:
      linear-gradient(45deg, #252535 25%, transparent 25%),
      linear-gradient(-45deg, #252535 25%, transparent 25%),
      linear-gradient(45deg, transparent 75%, #252535 75%),
      linear-gradient(-45deg, transparent 75%, #252535 75%);
    background-size: 16px 16px;
    background-position: 0 0, 0 8px, 8px -8px, -8px 0;
    border: 1px solid #333; border-radius: 4px; display: inline-block;
  }}
  .frames-strip {{ display: flex; gap: 4px; flex-wrap: wrap; }}
  .frame-cell {{ cursor: pointer; }}
  .frame-cell img {{
    width: 64px; height: 64px;
    border: 2px solid transparent; border-radius: 3px;
  }}
  .frame-cell.active img {{ border-color: #5588cc; }}

  .error-banner {{
    background: #2a1520; border: 1px solid #4a2030;
    color: #f08080; padding: 8px; border-radius: 6px; font-size: 12px;
  }}
</style>
</head>
<body>
<h1>Real Pose Reference Test</h1>
<div class="meta">Model: <span id="m"></span> | <span id="t"></span></div>
<div class="controls">
  <label>FPS:</label>
  <input type="range" id="fps" min="1" max="8" value="4">
  <span class="val" id="fv">4</span>
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

// Reference section
const refDiv = document.createElement('div');
refDiv.className = 'ref-section';
let refFramesHtml = '';
D.ref_frames.forEach(f => {{
  refFramesHtml += `<div class="frame-cell"><div class="checker"><img src="${{f}}"></div></div>`;
}});
const refAid = 'ref';
refDiv.innerHTML = `
  <h2>Reference Walk Cycle (generated first, used as pose guide)</h2>
  <div class="ref-body">
    <a href="${{D.ref_sheet}}" target="_blank"><img class="sheet" src="${{D.ref_sheet}}"></a>
    <div class="anim-col">
      <div class="anim-preview" id="${{refAid}}-p">
        <div class="checker"><canvas id="${{refAid}}-c" width="120" height="120"></canvas></div>
        <div class="po">||</div>
      </div>
    </div>
    <div class="frames-strip">${{refFramesHtml}}</div>
  </div>`;
sc.appendChild(refDiv);
anims.push({{ id: refAid, frames: D.ref_frames, fi: 0, paused: false, images: [], loaded: false }});

// Group results by character
const groups = {{}};
D.results.forEach(r => {{
  if (!groups[r.id]) groups[r.id] = [];
  groups[r.id].push(r);
}});

Object.entries(groups).forEach(([charId, variants]) => {{
  const section = document.createElement('div');
  section.className = 'char-section';
  let varHtml = '';
  variants.forEach((v, vi) => {{
    const aid = `${{charId}}-${{vi}}`;
    if (v.error) {{
      varHtml += `<div class="variant"><h3>${{v.variant}}</h3><div class="error-banner">${{v.error}}</div></div>`;
      return;
    }}
    let fHtml = '';
    v.frames.forEach((f, fi) => {{
      fHtml += `<div class="frame-cell" data-a="${{aid}}" data-f="${{fi}}"><div class="checker"><img src="${{f}}"></div></div>`;
    }});
    varHtml += `
      <div class="variant">
        <div class="variant-header">
          <h3>${{v.variant}}</h3>
          <span class="variant-timing">${{v.timing_s}}s</span>
        </div>
        <div class="variant-body">
          <div class="sheet-col">
            <a href="${{v.sheet}}" target="_blank"><img src="${{v.sheet}}"></a>
            <div class="label">Raw sheet</div>
          </div>
          <div class="anim-col">
            <div class="anim-preview" id="${{aid}}-p">
              <div class="checker"><canvas id="${{aid}}-c" width="120" height="120"></canvas></div>
              <div class="po">||</div>
            </div>
          </div>
          <div class="frames-strip">${{fHtml}}</div>
        </div>
      </div>`;
    anims.push({{ id: aid, frames: v.frames, fi: 0, paused: false, images: [], loaded: false }});
  }});
  section.innerHTML = `<h2>${{variants[0].name}}</h2><div class="variants">${{varHtml}}</div>`;
  sc.appendChild(section);
}});

anims.forEach(st => {{
  st.images = st.frames.map(f => {{ const i = new window.Image(); i.src = f; return i; }});
  if (st.images.length > 0) st.images[0].onload = () => {{ st.loaded = true; }};
  const pp = document.getElementById(`${{st.id}}-p`);
  if (pp) pp.addEventListener('click', () => {{
    st.paused = !st.paused; pp.classList.toggle('paused', st.paused);
  }});
}});
document.querySelectorAll('.frame-cell').forEach(t => {{
  t.addEventListener('click', e => {{
    e.stopPropagation();
    const aid = t.dataset.a, fi = parseInt(t.dataset.f);
    const st = anims.find(a => a.id === aid);
    if (st) {{ st.fi = fi; st.paused = true;
      document.getElementById(`${{aid}}-p`).classList.add('paused'); draw(st); }}
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
  if (ts - last >= 1000/fps) {{ last = ts;
    anims.forEach(st => {{
      if (!st.paused && st.loaded && st.images.length > 0) {{
        st.fi = (st.fi + 1) % st.images.length; draw(st);
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
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    template_bytes = make_template_2x2()
    (OUTPUT_DIR / "template.png").write_bytes(template_bytes)

    print("Real Pose Reference Test")
    print(f"  Image model: {IMAGE_MODEL}")
    print(f"  Output: {OUTPUT_DIR}\n")

    t0 = time.monotonic()

    # Step 1: Generate reference walk cycle
    print("Step 1: Generating reference walk cycle (simple character)...")
    ref_prompt = (
        f"{REF_CHARACTER}\n\n"
        f"Walking in a 4-frame walk cycle loop.\n"
        f"{WALK_CELL_DESCS}\n"
        f"{DEFENSIVE_REQS}\n\n"
        f"Solid {BG} background in every cell."
    )
    ref_raw = await asyncio.to_thread(
        _call_gemini,
        [_make_part(template_bytes), ref_prompt],
        system_instruction=template_sys_instr(),
    )
    ref_subdir = OUTPUT_DIR / "reference"
    ref_subdir.mkdir(parents=True, exist_ok=True)
    (ref_subdir / "sheet.png").write_bytes(ref_raw)
    ref_frames = await process_sheet(ref_raw, ref_subdir)
    print(f"  Reference done ({time.monotonic() - t0:.1f}s)\n")

    # Step 2: Generate test characters with and without pose reference
    all_results = []

    for char in TEST_CHARACTERS:
        print(f"{'='*50}")
        print(f"  {char['name']}")

        char_prompt = (
            f"{char['appearance']}\n\n"
            f"Walking in a 4-frame walk cycle loop.\n"
            f"{WALK_CELL_DESCS}\n"
            f"{DEFENSIVE_REQS}\n\n"
            f"Solid {BG} background in every cell."
        )

        for use_ref in [False, True]:
            variant = "with_pose_ref" if use_ref else "template_only"
            subdir = OUTPUT_DIR / f"{char['id']}_{variant}"
            subdir.mkdir(parents=True, exist_ok=True)

            contents: list = [_make_part(template_bytes)]
            if use_ref:
                contents.append(_make_part(ref_raw))
            contents.append(char_prompt)

            sys_instr = template_sys_instr(with_pose_ref=use_ref)

            result = {
                "id": char["id"],
                "name": char["name"],
                "variant": variant,
                "sheet": "",
                "frames": [],
                "timing_s": 0.0,
                "error": None,
            }

            t1 = time.monotonic()
            try:
                print(f"    [{variant}] generating...")
                raw = await asyncio.to_thread(_call_gemini, contents, sys_instr)
                (subdir / "sheet.png").write_bytes(raw)
                result["sheet"] = f"{subdir.name}/sheet.png"
                print(f"    [{variant}] processing frames...")
                result["frames"] = await process_sheet(raw, subdir)
                print(f"    [{variant}] done")
            except Exception as e:
                result["error"] = f"{type(e).__name__}: {e}"
                print(f"    [{variant}] FAILED: {result['error']}")

            result["timing_s"] = round(time.monotonic() - t1, 2)
            all_results.append(result)

    wall = time.monotonic() - t0

    dashboard = generate_dashboard("reference/sheet.png", ref_frames, all_results)
    (OUTPUT_DIR / "dashboard.html").write_text(dashboard, encoding="utf-8")

    ok = sum(1 for r in all_results if not r["error"])
    print(f"\n{'='*60}")
    print(f"DONE in {wall:.0f}s — {ok}/{len(all_results)} succeeded")
    print(f"Dashboard: {OUTPUT_DIR / 'dashboard.html'}")


if __name__ == "__main__":
    asyncio.run(main())
