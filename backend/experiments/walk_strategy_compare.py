#!/usr/bin/env python3
"""Walk cycle strategy comparison — round 2.

Tests fundamentally different approaches to getting consistent animation
frames, not just different prompt wording.

One human character, walk cycle, 5 strategies that vary HOW the reference
image is used (or not used), all sharing the same base sprite.

Usage:
    cd backend && uv run python -m experiments.walk_strategy_compare
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

from PIL import Image

OUTPUT_DIR = SCRIPT_DIR / "output" / "walk_strategy2"

IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gemini-3.1-flash-image-preview")
TEXT_MODEL = "gemini-3.1-flash-lite-preview"
CONCURRENCY = 4
TEXTURE_SIZE = 512
FILL_FRACTION = 0.9

SUBJECT_NAME = "adventurer"
SUBJECT_DESC = "a human adventurer with a backpack and boots"

ART_PREFIX = (
    "mixed media collage style paper cutout, side view facing right,"
    " flat lighting, clean edges"
)
ART_SUFFIX = "single centered object, contrasting solid background color, no text"

# Same 4 walk frames for all strategies (LLM-generated style, which won last round)
WALK_FRAMES = [
    "walking, near leg extended forward, far leg pushing off behind, torso upright, backpack straps trailing",
    "walking, near leg planted beneath body, far leg swinging forward partially occluded by torso, slight body compression",
    "walking, legs close together passing, body at tallest, arms mid-swing",
    "walking, far leg leading forward, near leg trailing behind, torso upright, backpack bouncing slightly",
]


# ── Strategies ─────────────────────────────────────────────────────────

# Each strategy is a function that generates one frame given:
#   - frame motion description
#   - base sprite bytes (bg removed)
#   - base sprite raw bytes (with bg, pre-removal)
#   - detailed character appearance text
# Returns raw image bytes


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
) -> bytes:
    """Unified Gemini image generation call."""
    from google import genai
    from google.genai import types

    client = genai.Client()
    config_kwargs: dict = {
        "response_modalities": response_modalities or ["IMAGE"],
        "image_config": types.ImageConfig(image_size="512", aspect_ratio="1:1"),
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


def _make_image_part(image_bytes: bytes):
    from google.genai import types
    return types.Part.from_bytes(data=image_bytes, mime_type="image/png")


# Character appearance description for text-only strategies
APPEARANCE_DESC = (
    "a human adventurer, medium build, wearing a brown leather backpack "
    "with visible straps, sturdy brown boots, green tunic, short brown hair, "
    "mixed media collage paper cutout art style"
)


@dataclass
class Strategy:
    id: str
    name: str
    description: str
    generate: object  # callable, set below


def strat_A_edit_framing(
    motion: str,
    ref_bytes: bytes,
    raw_ref_bytes: bytes,
    appearance: str,
) -> bytes:
    """Tell the model to EDIT the existing image to change the pose."""
    prompt = (
        f"Edit this image to change the character's pose: {motion}. "
        f"Keep the exact same character appearance, colors, art style, and proportions. "
        f"Side view facing right. {ART_SUFFIX}."
    )
    return _call_gemini([_make_image_part(ref_bytes), prompt])


def strat_B_system_instruction(
    motion: str,
    ref_bytes: bytes,
    raw_ref_bytes: bytes,
    appearance: str,
) -> bytes:
    """Use system_instruction to anchor the reference, content is just the pose."""
    sys_instr = (
        "You generate pose variants of a character. The user will provide a reference "
        "image of the character and a pose description. Generate the SAME character "
        "(exact same appearance, colors, proportions, art style) in the requested pose. "
        "The character always faces right in side view."
    )
    prompt = f"{ART_PREFIX}, {SUBJECT_NAME}, {motion}, {ART_SUFFIX}"
    return _call_gemini(
        [_make_image_part(ref_bytes), prompt],
        system_instruction=sys_instr,
    )


def strat_C_ref_plus_description(
    motion: str,
    ref_bytes: bytes,
    raw_ref_bytes: bytes,
    appearance: str,
) -> bytes:
    """Pass both reference image AND text description of the character."""
    prompt = (
        f"The reference image shows: {appearance}. "
        f"Draw this exact same character in the following pose: {motion}. "
        f"{ART_PREFIX}, {ART_SUFFIX}."
    )
    return _call_gemini([_make_image_part(ref_bytes), prompt])


def strat_D_no_reference(
    motion: str,
    ref_bytes: bytes,
    raw_ref_bytes: bytes,
    appearance: str,
) -> bytes:
    """No reference image at all. Rely entirely on detailed text description."""
    prompt = (
        f"{ART_PREFIX}, {appearance}, {motion}, {ART_SUFFIX}"
    )
    return _call_gemini([prompt])


def strat_E_text_and_image_modality(
    motion: str,
    ref_bytes: bytes,
    raw_ref_bytes: bytes,
    appearance: str,
) -> bytes:
    """Use TEXT+IMAGE response modality so model can reason before generating."""
    prompt = (
        f"First analyze the reference image, then generate the same character "
        f"in this pose: {motion}. "
        f"Maintain exact appearance, colors, and art style. "
        f"{ART_PREFIX}, {ART_SUFFIX}."
    )
    return _call_gemini(
        [_make_image_part(ref_bytes), prompt],
        response_modalities=["TEXT", "IMAGE"],
    )


STRATEGIES = [
    Strategy("A_edit", "Edit framing",
             "\"Edit this image to change the pose\" — treats it as image modification, not creation",
             strat_A_edit_framing),
    Strategy("B_sysinstr", "System instruction anchor",
             "Reference relationship explained in system_instruction, separate from per-frame prompt",
             strat_B_system_instruction),
    Strategy("C_ref_desc", "Reference + appearance description",
             "Both the image AND a text description of the character — redundant anchoring",
             strat_C_ref_plus_description),
    Strategy("D_no_ref", "No reference image (text only)",
             "Skip the image entirely, describe appearance in detail in every prompt",
             strat_D_no_reference),
    Strategy("E_textimg", "TEXT+IMAGE modality",
             "response_modalities=[\"TEXT\",\"IMAGE\"] — model reasons about the character before drawing",
             strat_E_text_and_image_modality),
]


# ── Image gen / bg removal helpers ─────────────────────────────────────


def _crop_and_fit(img: Image.Image, target_size: int = TEXTURE_SIZE) -> Image.Image:
    bbox = img.getbbox()
    if bbox is None:
        return Image.new("RGBA", (target_size, target_size), (0, 0, 0, 0))
    cropped = img.crop(bbox)
    max_extent = int(target_size * FILL_FRACTION)
    w, h = cropped.size
    scale = min(max_extent / w, max_extent / h)
    new_w = max(1, round(w * scale))
    new_h = max(1, round(h * scale))
    resized = cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (target_size, target_size), (0, 0, 0, 0))
    paste_x = (target_size - new_w) // 2
    paste_y = (target_size - new_h) // 2
    canvas.paste(resized, (paste_x, paste_y))
    return canvas


def _generate_base_sync(prompt: str) -> bytes:
    return _call_gemini([prompt])


_bg_model_cache: dict[str, object] = {}


def _remove_bg_cached(image_bytes: bytes) -> bytes:
    try:
        import torch
        from torchvision import transforms
        from transformers import AutoModelForImageSegmentation

        if "model" not in _bg_model_cache:
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
            _bg_model_cache["model"] = model
            _bg_model_cache["device"] = device
            _bg_model_cache["transform"] = transform
            print(f"  BiRefNet loaded on {device}")

        model = _bg_model_cache["model"]
        device = _bg_model_cache["device"]
        transform = _bg_model_cache["transform"]

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


# ── Pipeline ───────────────────────────────────────────────────────────

_image_sem: asyncio.Semaphore | None = None
_bg_sem: asyncio.Semaphore | None = None


@dataclass
class FrameResult:
    frame_num: int
    motion_desc: str
    image_path: str
    error: str | None = None


@dataclass
class StrategyResult:
    strategy: Strategy
    frames: list[FrameResult] = field(default_factory=list)
    timing_s: float = 0.0


async def _gen_frame(
    strategy: Strategy,
    frame_num: int,
    motion: str,
    ref_bytes: bytes,
    raw_ref_bytes: bytes,
    appearance: str,
) -> FrameResult:
    assert _image_sem is not None
    assert _bg_sem is not None

    fname = f"{strategy.id}/walk_{frame_num}.png"
    result = FrameResult(frame_num=frame_num, motion_desc=motion, image_path=fname)
    try:
        async with _image_sem:
            raw = await asyncio.to_thread(
                strategy.generate, motion, ref_bytes, raw_ref_bytes, appearance,
            )
        async with _bg_sem:
            bg_removed = await asyncio.to_thread(_remove_bg_cached, raw)
        img = Image.open(io.BytesIO(bg_removed)).convert("RGBA")
        img = _crop_and_fit(img)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        out_path = OUTPUT_DIR / fname
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(buf.getvalue())
        print(f"    [{strategy.id}] frame {frame_num} done")
    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"
        print(f"    [{strategy.id}] frame {frame_num} FAILED: {result.error}")
    return result


async def run_strategy(
    strategy: Strategy,
    ref_bytes: bytes,
    raw_ref_bytes: bytes,
    appearance: str,
) -> StrategyResult:
    result = StrategyResult(strategy=strategy)
    print(f"\n  Strategy: {strategy.name}")
    print(f"  {strategy.description}")
    t0 = time.monotonic()

    tasks = [
        _gen_frame(strategy, i, motion, ref_bytes, raw_ref_bytes, appearance)
        for i, motion in enumerate(WALK_FRAMES, 1)
    ]
    frame_results = await asyncio.gather(*tasks)
    result.frames = list(frame_results)
    result.timing_s = round(time.monotonic() - t0, 2)

    ok = sum(1 for f in frame_results if not f.error)
    print(f"  [{strategy.id}] {ok}/{len(frame_results)} frames ({result.timing_s:.1f}s)")
    return result


# ── Dashboard ──────────────────────────────────────────────────────────


def generate_dashboard(
    base_image: str,
    base_prompt: str,
    results: list[StrategyResult],
) -> str:
    strategies_json = []
    for r in results:
        strategies_json.append({
            "id": r.strategy.id,
            "name": r.strategy.name,
            "description": r.strategy.description,
            "frames": [
                {"image": f.image_path, "motion": f.motion_desc, "error": f.error}
                for f in r.frames
            ],
            "timing_s": r.timing_s,
        })

    data_json = json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "image_model": IMAGE_MODEL,
        "subject": SUBJECT_NAME,
        "subject_desc": SUBJECT_DESC,
        "base_image": base_image,
        "base_prompt": base_prompt,
        "walk_frames": WALK_FRAMES,
        "strategies": strategies_json,
    }, indent=2)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Walk Strategy Comparison (Round 2)</title>
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

  .base-row {{
    display: flex; align-items: center; gap: 16px;
    margin-bottom: 20px; padding: 14px;
    background: #16213e; border: 1px solid #2a2a4a; border-radius: 10px;
  }}
  .base-row h3 {{
    font-size: 11px; color: #7b8794; text-transform: uppercase;
    letter-spacing: 1px; margin-bottom: 4px;
  }}
  .base-row .info {{ font-size: 12px; color: #888; }}

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
  .base-row img {{ width: 120px; height: 120px; display: block; }}

  .walk-frames-note {{
    font-size: 11px; color: #666; margin-bottom: 16px;
    padding: 10px; background: #0f1a2e; border-radius: 6px;
    line-height: 1.6;
  }}
  .walk-frames-note strong {{ color: #888; }}

  .strategy-card {{
    background: #16213e; border: 1px solid #2a2a4a; border-radius: 10px;
    padding: 16px; margin-bottom: 14px;
  }}
  .strategy-header {{
    display: flex; align-items: baseline; gap: 10px; margin-bottom: 2px;
  }}
  .strategy-desc {{ font-size: 11px; color: #777; margin-bottom: 10px; }}
  .strategy-timing {{ font-size: 11px; color: #555; margin-left: auto; }}

  .strategy-body {{
    display: flex; align-items: center; gap: 14px;
  }}
  .anim-preview {{
    flex-shrink: 0; cursor: pointer; position: relative;
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

  .frame-strip {{
    display: flex; gap: 8px; align-items: center;
  }}
  .frame-cell {{
    display: flex; flex-direction: column; align-items: center; gap: 2px;
    cursor: pointer;
  }}
  .frame-cell img {{
    width: 80px; height: 80px;
    border: 2px solid transparent; border-radius: 4px;
    transition: border-color 0.15s;
  }}
  .frame-cell img:hover {{ border-color: #5588cc; }}
  .frame-cell.active img {{
    border-color: #5588cc;
    box-shadow: 0 0 6px rgba(85,136,204,0.4);
  }}
  .frame-cell .num {{ font-size: 10px; color: #555; }}
  .frame-cell.error img {{ opacity: 0.2; border-color: #633; }}

  .error-text {{ font-size: 11px; color: #c44; margin-top: 6px; }}
</style>
</head>
<body>

<h1>Walk Strategy Comparison (Round 2)</h1>
<div class="meta">
  Subject: <span>{SUBJECT_NAME}</span> |
  Model: <span id="m"></span> |
  <span id="t"></span>
</div>

<div class="controls">
  <label>FPS:</label>
  <input type="range" id="fps" min="1" max="8" value="4">
  <span class="val" id="fv">4</span>
  <label style="margin-left:12px">Click preview to pause</label>
</div>

<div id="base-container"></div>
<div id="walk-note"></div>
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

document.getElementById('base-container').innerHTML = `
  <div class="base-row">
    <div class="checker"><img src="${{D.base_image}}" alt="base"></div>
    <div>
      <h3>Base Sprite (shared reference)</h3>
      <div class="info">${{D.subject_desc}}</div>
    </div>
  </div>`;

// Show shared walk frame descriptions
let noteHtml = '<div class="walk-frames-note"><strong>Same motion prompts for all strategies:</strong><br>';
D.walk_frames.forEach((f, i) => {{ noteHtml += `${{i+1}}. ${{f}}<br>`; }});
noteHtml += '</div>';
document.getElementById('walk-note').innerHTML = noteHtml;

const sc = document.getElementById('sc');

D.strategies.forEach((strat, si) => {{
  const card = document.createElement('div');
  card.className = 'strategy-card';
  const aid = `a${{si}}`;

  let stripHtml = '';
  strat.frames.forEach((f, fi) => {{
    const err = f.error ? ' error' : '';
    stripHtml += `
      <div class="frame-cell${{err}}" data-a="${{aid}}" data-f="${{fi}}">
        <div class="checker">
          <img src="${{f.error ? '' : f.image}}" alt="f${{fi+1}}"
               onerror="this.style.opacity=0.2">
        </div>
        <span class="num">${{fi+1}}</span>
      </div>`;
  }});

  const errors = strat.frames.filter(f => f.error);
  const errHtml = errors.length
    ? `<div class="error-text">${{errors.map(e => e.error).join('; ')}}</div>` : '';

  card.innerHTML = `
    <div class="strategy-header">
      <h2>${{strat.name}}</h2>
      <span class="strategy-timing">${{strat.timing_s}}s</span>
    </div>
    <div class="strategy-desc">${{strat.description}}</div>
    <div class="strategy-body">
      <div class="anim-preview" id="${{aid}}-p">
        <div class="checker">
          <canvas id="${{aid}}-c" width="120" height="120"></canvas>
        </div>
        <div class="pause-overlay">||</div>
      </div>
      <div class="frame-strip">${{stripHtml}}</div>
    </div>
    ${{errHtml}}`;
  sc.appendChild(card);

  const valid = strat.frames.filter(f => !f.error);
  const imgs = valid.map(f => {{
    const img = new window.Image(); img.src = f.image; return img;
  }});
  const st = {{ id: aid, fi: 0, paused: false, images: imgs, loaded: false }};
  if (imgs.length > 0) imgs[0].onload = () => {{ st.loaded = true; }};
  anims.push(st);

  document.getElementById(`${{aid}}-p`).addEventListener('click', () => {{
    st.paused = !st.paused;
    document.getElementById(`${{aid}}-p`).classList.toggle('paused', st.paused);
  }});
}});

document.querySelectorAll('.frame-cell').forEach(t => {{
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
    global _image_sem, _bg_sem
    _image_sem = asyncio.Semaphore(CONCURRENCY)
    _bg_sem = asyncio.Semaphore(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    total_images = 1 + len(STRATEGIES) * 4
    print("Walk Strategy Comparison (Round 2)")
    print(f"  {len(STRATEGIES)} strategies x 4 frames + 1 base = {total_images} images")
    print(f"  Subject: {SUBJECT_NAME} ({SUBJECT_DESC})")
    print(f"  Image model: {IMAGE_MODEL}")
    print(f"  Output: {OUTPUT_DIR}\n")

    t0 = time.monotonic()

    # Step 1: Generate base sprite
    print("Generating base sprite...")
    base_prompt = f"{ART_PREFIX}, {SUBJECT_NAME}, {SUBJECT_DESC}, {ART_SUFFIX}"
    async with _image_sem:
        raw_base = await asyncio.to_thread(_generate_base_sync, base_prompt)
    # Keep raw (with bg) for strategies that might want it
    raw_ref_bytes = raw_base
    async with _bg_sem:
        bg_removed = await asyncio.to_thread(_remove_bg_cached, raw_base)
    base_img = Image.open(io.BytesIO(bg_removed)).convert("RGBA")
    base_img = _crop_and_fit(base_img)
    buf = io.BytesIO()
    base_img.save(buf, format="PNG")
    ref_bytes = buf.getvalue()
    (OUTPUT_DIR / "base.png").write_bytes(ref_bytes)
    print(f"  Base done ({time.monotonic() - t0:.1f}s)\n")

    # Step 2: Run all strategies
    results: list[StrategyResult] = []
    for strategy in STRATEGIES:
        sr = await run_strategy(strategy, ref_bytes, raw_ref_bytes, APPEARANCE_DESC)
        results.append(sr)

    wall = time.monotonic() - t0

    # Dashboard
    dashboard = generate_dashboard("base.png", base_prompt, results)
    (OUTPUT_DIR / "dashboard.html").write_text(dashboard, encoding="utf-8")

    ok = sum(1 for r in results for f in r.frames if not f.error)
    total = sum(len(r.frames) for r in results)
    print(f"\n{'='*60}")
    print(f"DONE in {wall:.0f}s — {ok}/{total} frames")
    print(f"Dashboard: {OUTPUT_DIR / 'dashboard.html'}")


if __name__ == "__main__":
    asyncio.run(main())
