#!/usr/bin/env python3
"""Image-to-Video animation experiment: static sprite -> I2V model -> frame extraction.

Tests whether video diffusion models can animate 2D game sprites while preserving
the flat paper-cutout art style. Compares prompt strategies across test characters.

Usage:
    # Full comparison (4 characters x 3 prompt tiers)
    cd backend && uv run python -m experiments.i2v_animation_test

    # Single sprite test
    cd backend && uv run python -m experiments.i2v_animation_test --sprite path.png --prompt "walk cycle"

    # Skip sprite generation (use cached sprites only)
    cd backend && uv run python -m experiments.i2v_animation_test --skip-sprite-gen

    # More frames (17 = 8*2+1)
    cd backend && uv run python -m experiments.i2v_animation_test --frames 17
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from PIL import Image

OUTPUT_DIR = SCRIPT_DIR / "output" / "i2v_test"
SPRITE_CACHE_DIR = OUTPUT_DIR / "sprites"
MODEL_CKPT = "https://huggingface.co/Lightricks/LTX-Video/blob/main/ltxv-2b-0.9.6-distilled-04-25.safetensors"
MODEL_LABEL = "ltxv-2b-0.9.6-distilled"


# ── Characters ─────────────────────────────────────────────────────────

CHARACTERS = [
    {
        "id": "knight",
        "desc": "a knight in plate armor with a red cape",
        "appearance": (
            "A knight in full silver plate armor with a closed visor helmet, "
            "red cape flowing behind, brown leather belt with a sheathed sword, "
            "steel gauntlets and greaves."
        ),
    },
    {
        "id": "wizard",
        "desc": "an old wizard with a staff and blue robes",
        "appearance": (
            "An old wizard with a long white beard, tall pointed blue hat, "
            "flowing dark blue robes with silver star patterns, holding a "
            "gnarled wooden staff with a glowing crystal on top, brown boots."
        ),
    },
    {
        "id": "skeleton",
        "desc": "an animated skeleton warrior",
        "appearance": (
            "An animated skeleton with yellowed bones, hollow eye sockets "
            "with faint glowing dots, a rusted iron helmet, tattered brown "
            "leather armor scraps, holding a chipped sword."
        ),
    },
    {
        "id": "robot",
        "desc": "a small friendly robot",
        "appearance": (
            "A small boxy robot with a rounded head, two large circular blue "
            "eyes on a screen face, stubby metal arms and legs with ball joints, "
            "antenna on top, silver and orange painted metal body."
        ),
    },
    {
        "id": "goblin",
        "desc": "a green goblin with a dagger",
        "appearance": (
            "A short green-skinned goblin with large pointed ears, beady yellow "
            "eyes, a wide sharp-toothed grin, wearing a ragged brown vest and "
            "torn shorts, bare feet, clutching a small rusty dagger."
        ),
    },
]


# ── Prompt strategies ────────────────────────────────────────────────

PROMPTS = {
    "game_style": (
        "2D game sprite walk cycle animation, side view facing right, "
        "character walking with visible leg movement, looping animation, "
        "flat perspective, no camera movement"
    ),
    "motion_focused": (
        "Walk cycle, legs stepping alternately in clear strides, "
        "arms swinging opposite to legs, body bobbing up and down, "
        "weight shifting between feet, side view"
    ),
    "char_aware": None,  # filled per-character at runtime
}

# Background colors to test
BG_COLORS: dict[str, tuple[int, int, int]] = {
    "white": (255, 255, 255),
    "green": (0, 255, 0),
    "dark": (40, 40, 40),
    "blue": (170, 200, 255),
}

# image_cond_noise_scale values to test
NOISE_SCALES = [0.025, 0.07, 0.15]

# Frame counts to test
FRAME_COUNTS = [33, 65, 97]  # 8*4+1, 8*8+1, 8*12+1
DEFAULT_FRAME_COUNT = 97

# Number of frames to extract for the sprite sheet
EXTRACT_FRAMES = 8


# ── Sprite generation ────────────────────────────────────────────────

SPRITE_PROMPT_TEMPLATE = (
    "mixed media collage style paper cutout, side view, facing right. "
    "{appearance} Flat lighting, clean edges, solid background."
)


async def generate_sprite(appearance: str, char_id: str) -> Image.Image:
    """Generate a test sprite using the configured image backend. Caches to disk."""
    cache_path = SPRITE_CACHE_DIR / f"{char_id}.png"
    if cache_path.exists():
        print(f"  Using cached sprite: {cache_path.name}")
        return Image.open(cache_path).convert("RGBA")

    from app.images.local_image import generate_image
    from app.images.pipeline import _crop_and_fit, remove_bg

    prompt = SPRITE_PROMPT_TEMPLATE.format(appearance=appearance)
    print(f"  Generating sprite for {char_id}...")
    raw_bytes = await generate_image(prompt)
    nobg_bytes = await remove_bg(raw_bytes)
    img = Image.open(io.BytesIO(nobg_bytes)).convert("RGBA")
    fitted = _crop_and_fit(img, 512)

    SPRITE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fitted.save(cache_path, format="PNG")
    print(f"  Saved sprite: {cache_path.name}")
    return fitted


def prepare_i2v_input(
    sprite: Image.Image, bg_color: tuple[int, int, int] = (255, 255, 255)
) -> Image.Image:
    """Composite RGBA sprite onto solid background for I2V input (needs RGB)."""
    bg = Image.new("RGB", sprite.size, bg_color)
    if sprite.mode == "RGBA":
        bg.paste(sprite, mask=sprite.split()[3])
    else:
        bg.paste(sprite)
    return bg


# ── I2V pipeline ─────────────────────────────────────────────────────

_pipeline = None


REFERENCE_PIPELINE = "Lightricks/LTX-Video-0.9.5"
NEGATIVE_PROMPT = "worst quality, inconsistent motion, blurry, jittery, distorted"
SEED = 42


def load_pipeline():
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    import torch
    from diffusers.pipelines.ltx import LTXConditionPipeline

    print(f"Loading I2V model: {MODEL_LABEL}")
    print(f"  VRAM before load: {_vram_str()}")
    t0 = time.monotonic()

    # The distilled checkpoint only contains transformer weights. Load
    # text encoder + tokenizer from the reference diffusers pipeline.
    from transformers import T5EncoderModel, T5Tokenizer

    print("  Loading text encoder from reference pipeline...")
    text_encoder = T5EncoderModel.from_pretrained(
        REFERENCE_PIPELINE, subfolder="text_encoder", torch_dtype=torch.bfloat16
    )
    tokenizer = T5Tokenizer.from_pretrained(REFERENCE_PIPELINE, subfolder="tokenizer")

    print("  Loading distilled transformer from checkpoint...")
    _pipeline = LTXConditionPipeline.from_single_file(
        MODEL_CKPT,
        text_encoder=text_encoder,
        tokenizer=tokenizer,
        torch_dtype=torch.bfloat16,
    )
    _pipeline.to("cuda")

    dt = time.monotonic() - t0
    print(f"  Model loaded in {dt:.1f}s — VRAM: {_vram_str()}")
    return _pipeline


def _wrap_image_as_video(image: Image.Image) -> list[Image.Image]:
    """Wrap a PIL image as a single-frame video for LTX conditioning."""
    from diffusers.utils import export_to_video, load_video
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        tmp_path = f.name
    export_to_video([image], tmp_path, fps=24)
    video = load_video(tmp_path)
    Path(tmp_path).unlink(missing_ok=True)
    return video


def generate_video(
    image: Image.Image,
    prompt: str,
    num_frames: int = 97,
    noise_scale: float = 0.025,
) -> list[Image.Image]:
    """Run I2V inference with proper conditioning. Returns list of PIL Images."""
    import torch
    from diffusers.pipelines.ltx.pipeline_ltx_condition import LTXVideoCondition

    pipe = load_pipeline()
    video = _wrap_image_as_video(image)

    conditions = [LTXVideoCondition(video=video, frame_index=0)]

    output = pipe(
        conditions=conditions,
        prompt=prompt,
        negative_prompt=NEGATIVE_PROMPT,
        num_frames=num_frames,
        height=512,
        width=512,
        num_inference_steps=8,
        guidance_scale=1.0,
        decode_timestep=0.05,
        decode_noise_scale=0.025,
        image_cond_noise_scale=noise_scale,
        generator=torch.Generator(device="cuda").manual_seed(SEED),
        output_type="pil",
    )
    return output.frames[0]


def pingpong(frames: list[Image.Image]) -> list[Image.Image]:
    """Create a ping-pong loop: forward + reversed (excluding endpoints to avoid stutter)."""
    if len(frames) <= 2:
        return frames
    return frames + frames[-2:0:-1]


def extract_frames(
    all_frames: list[Image.Image], n: int = EXTRACT_FRAMES
) -> tuple[list[Image.Image], list[int]]:
    """Evenly sample n frames from the full video. Returns (frames, indices)."""
    total = len(all_frames)
    if total <= n:
        return all_frames, list(range(total))
    # Evenly space, skip frame 0 (it's the conditioning image) and last (if loop)
    step = total / n
    indices = [int(i * step) for i in range(n)]
    return [all_frames[i] for i in indices], indices


# ── Background removal (inline, same as anim_e2e_compare.py) ─────────

_bg_cache: dict[str, object] = {}


def _remove_bg(image_bytes: bytes) -> bytes:
    import torch
    from torchvision import transforms
    from transformers import AutoModelForImageSegmentation

    if "model" not in _bg_cache:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = AutoModelForImageSegmentation.from_pretrained(
            "ZhengPeng7/BiRefNet_lite",
            trust_remote_code=True,
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
    t = transform(img).unsqueeze(0).to(device)
    if device.type == "cuda":
        t = t.half()
    with torch.no_grad():
        preds = model(t)[-1].sigmoid().cpu()
    mask = transforms.ToPILImage()(preds[0].squeeze())
    mask = mask.resize(orig_size, Image.Resampling.LANCZOS)
    result = img.convert("RGBA")
    result.putalpha(mask)
    buf = io.BytesIO()
    result.save(buf, format="PNG")
    return buf.getvalue()


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


async def process_frame(raw_frame: Image.Image) -> Image.Image:
    """Remove background and crop/fit a single video frame."""
    buf = io.BytesIO()
    raw_frame.save(buf, format="PNG")
    bg_removed = await asyncio.to_thread(_remove_bg, buf.getvalue())
    processed = Image.open(io.BytesIO(bg_removed)).convert("RGBA")
    return _crop_and_fit(processed)


# ── Output helpers ───────────────────────────────────────────────────


def assemble_strip(frames: list[Image.Image]) -> Image.Image:
    """Create a horizontal strip spritesheet from frames."""
    if not frames:
        return Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    w, h = frames[0].size
    strip = Image.new("RGBA", (w * len(frames), h), (0, 0, 0, 0))
    for i, frame in enumerate(frames):
        strip.paste(frame, (i * w, 0))
    return strip


def save_gif(frames: list[Image.Image], path: Path, fps: int = 4) -> None:
    """Save frames as animated GIF with dark background."""
    rgb_frames = []
    for f in frames:
        bg = Image.new("RGB", f.size, (30, 30, 50))
        if f.mode == "RGBA":
            bg.paste(f, mask=f.split()[3])
        else:
            bg.paste(f)
        rgb_frames.append(bg)
    rgb_frames[0].save(
        path,
        save_all=True,
        append_images=rgb_frames[1:],
        duration=1000 // fps,
        loop=0,
    )


def _vram_str() -> str:
    import torch

    if torch.cuda.is_available():
        used = torch.cuda.memory_allocated() / 1024**3
        reserved = torch.cuda.memory_reserved() / 1024**3
        total = torch.cuda.get_device_properties(0).total_memory / 1024**3
        return f"{used:.1f}GB used / {reserved:.1f}GB reserved / {total:.0f}GB total"
    return "N/A (no CUDA)"


# ── Dashboard ────────────────────────────────────────────────────────


def generate_dashboard(all_results: list[dict], num_frames: int) -> str:
    data_json = json.dumps(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": MODEL_LABEL,
            "num_frames": num_frames,
            "results": all_results,
        },
        indent=2,
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>I2V Animation Test</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #1a1a2e; color: #e0e0e0; font-family: 'Segoe UI', system-ui, sans-serif; padding: 24px; }}
  h1 {{ font-size: 22px; margin-bottom: 4px; color: #fff; }}
  h2 {{ font-size: 16px; color: #9ecfff; margin-bottom: 8px; }}
  h3 {{ font-size: 13px; color: #c0d0e0; margin-bottom: 4px; }}
  .meta {{ font-size: 12px; color: #888; margin-bottom: 20px; }}
  .controls {{ display: flex; gap: 16px; align-items: center; margin-bottom: 20px;
    padding: 10px 16px; background: #16213e; border: 1px solid #2a2a4a; border-radius: 8px; }}
  .controls label {{ font-size: 13px; color: #888; }}
  .controls input[type=range] {{ width: 120px; }}
  .controls .val {{ font-size: 13px; color: #fff; min-width: 30px; }}
  .char-section {{ background: #12192e; border: 1px solid #2a2a4a; border-radius: 12px;
    padding: 16px; margin-bottom: 20px; }}
  .char-header {{ display: flex; align-items: center; gap: 16px; margin-bottom: 12px; }}
  .char-header img {{ width: 80px; height: 80px; border: 1px solid #333; border-radius: 6px; }}
  .variants {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(500px, 1fr)); gap: 12px; }}
  .variant {{ background: #16213e; border: 1px solid #2a2a4a; border-radius: 10px; padding: 14px; }}
  .variant-header {{ display: flex; align-items: baseline; gap: 8px; margin-bottom: 8px; }}
  .variant-timing {{ font-size: 11px; color: #555; margin-left: auto; }}
  .variant-body {{ display: flex; gap: 12px; align-items: flex-start; }}
  .anim-col {{ display: flex; flex-direction: column; gap: 6px; align-items: center; }}
  .anim-preview {{ cursor: pointer; position: relative; }}
  .anim-preview canvas {{ border: 1px solid #333; border-radius: 4px; }}
  .anim-preview .po {{ position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
    font-size: 20px; color: rgba(255,255,255,0.5); pointer-events: none; display: none; }}
  .anim-preview.paused .po {{ display: block; }}
  .checker {{ background-image: linear-gradient(45deg, #252535 25%, transparent 25%),
    linear-gradient(-45deg, #252535 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, #252535 75%),
    linear-gradient(-45deg, transparent 75%, #252535 75%);
    background-size: 16px 16px; background-position: 0 0, 0 8px, 8px -8px, -8px 0;
    border: 1px solid #333; border-radius: 4px; display: inline-block; }}
  .frames-strip {{ display: flex; gap: 4px; flex-wrap: wrap; }}
  .frame-cell {{ cursor: pointer; }}
  .frame-cell img {{ width: 56px; height: 56px; border: 2px solid transparent; border-radius: 3px; }}
  .frame-cell.active img {{ border-color: #5588cc; }}
  .raw-frames {{ margin-top: 8px; }}
  .raw-frames summary {{ font-size: 11px; color: #666; cursor: pointer; }}
  .raw-frames .strip {{ display: flex; gap: 2px; flex-wrap: wrap; margin-top: 4px; }}
  .raw-frames img {{ width: 48px; height: 48px; border: 1px solid #333; border-radius: 3px; }}
  .prompt-text {{ font-size: 9px; color: #666; margin: 4px 0; white-space: pre-wrap;
    word-break: break-word; padding: 6px; background: #0a0f1e; border-radius: 4px; }}
  .error-banner {{ background: #2a1520; border: 1px solid #4a2030; color: #f08080;
    padding: 8px; border-radius: 6px; font-size: 12px; }}
</style>
</head>
<body>
<h1>I2V Animation Test</h1>
<div class="meta">Model: {MODEL_LABEL} | Extract: {EXTRACT_FRAMES} frames | <span id="t"></span></div>
<div class="controls">
  <label>FPS:</label><input type="range" id="fps" min="1" max="12" value="4">
  <span class="val" id="fv">4</span>
</div>
<div id="sc"></div>
<script>
const D = {data_json};
let fps = 4;
const anims = [];
document.getElementById('t').textContent = new Date(D.generated_at).toLocaleString();
document.getElementById('fps').addEventListener('input', e => {{
  fps = parseInt(e.target.value); document.getElementById('fv').textContent = fps;
}});
const sc = document.getElementById('sc');
const groups = {{}};
D.results.forEach(r => {{
  if (!groups[r.char_id]) groups[r.char_id] = {{desc: r.char_desc, sprite: r.sprite_path, results: []}};
  r._label = `${{r.prompt_tier}} / ${{r.num_frames}}f / ${{r.loop ? 'loop' : 'noloop'}}`;
  groups[r.char_id].results.push(r);
}});
Object.entries(groups).forEach(([charId, data]) => {{
  const section = document.createElement('div');
  section.className = 'char-section';
  let varHtml = '';
  data.results.forEach((v, vi) => {{
    const aid = `${{charId}}-${{vi}}`;
    if (v.error) {{
      varHtml += `<div class="variant"><div class="variant-header"><h3>${{v.prompt_tier}}</h3></div>
        <div class="error-banner">${{v.error}}</div></div>`;
      return;
    }}
    let fHtml = '';
    (v.frames || []).forEach((f, fi) => {{
      fHtml += `<div class="frame-cell" data-a="${{aid}}" data-f="${{fi}}">
        <div class="checker"><img src="${{f}}" onerror="this.style.opacity=0.2"></div></div>`;
    }});
    let rawHtml = '';
    (v.raw_frames || []).forEach(f => {{
      rawHtml += `<img src="${{f}}" onerror="this.style.opacity=0.2">`;
    }});
    varHtml += `<div class="variant">
      <div class="variant-header"><h3>${{v._label}}</h3>
        <span class="variant-timing">${{v.i2v_time_s}}s i2v + ${{v.postprocess_time_s}}s post</span></div>
      <div class="variant-body">
        <div class="input-col" style="flex-shrink:0;text-align:center">
          <img src="${{v.input_path || ''}}" style="width:100px;height:100px;border:1px solid #333;border-radius:4px" title="I2V input (RGB)">
          <div style="font-size:9px;color:#555;margin-top:2px">I2V input</div>
        </div>
        <div class="anim-col">
          <div style="text-align:center">
            <img src="${{v.raw_gif || ''}}" style="width:120px;height:120px;border:1px solid #333;border-radius:4px" title="Raw I2V output">
            <div style="font-size:9px;color:#555;margin-top:2px">Raw output</div>
          </div>
          <div style="text-align:center">
            <div class="anim-preview" id="${{aid}}-p">
              <div class="checker"><canvas id="${{aid}}-c" width="120" height="120"></canvas></div>
              <div class="po">||</div>
            </div>
            <div style="font-size:9px;color:#555;margin-top:2px">Processed</div>
          </div>
        </div>
        <div class="frames-strip">${{fHtml}}</div>
      </div>
      <div class="raw-frames" style="margin-top:8px">
        <div style="font-size:11px;color:#888;margin-bottom:4px">Raw I2V frames:</div>
        <div class="strip">${{rawHtml}}</div></div>
      <details><summary>Prompt</summary><pre class="prompt-text">${{v.prompt || ''}}</pre></details>
    </div>`;
    anims.push({{ id: aid, frames: v.frames || [], fi: 0, paused: false, images: [], loaded: false }});
  }});
  section.innerHTML = `<div class="char-header">
    <div class="checker"><img src="${{data.sprite}}" style="width:80px;height:80px"></div>
    <div><h2>${{charId}}</h2><span style="color:#888;font-size:13px">${{data.desc}}</span></div>
  </div><div class="variants">${{varHtml}}</div>`;
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
  if (img && img.complete && img.naturalWidth > 0) ctx.drawImage(img, 0, 0, c.width, c.height);
  document.querySelectorAll(`[data-a="${{st.id}}"]`).forEach((t, i) =>
    t.classList.toggle('active', i === st.fi % st.images.length));
}}
let last = 0;
function loop(ts) {{
  if (ts - last >= 1000/fps) {{
    last = ts;
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


# ── Main ─────────────────────────────────────────────────────────────


async def run_single(sprite_path: str, prompt: str, num_frames: int) -> None:
    """Single-sprite mode: test one image with one prompt."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    subdir = OUTPUT_DIR / "single"
    subdir.mkdir(parents=True, exist_ok=True)

    sprite = Image.open(sprite_path).convert("RGBA")
    rgb_input = prepare_i2v_input(sprite)
    rgb_input.save(subdir / "input.png")

    print(f"Input: {sprite_path} ({sprite.size[0]}x{sprite.size[1]})")
    print(f"Prompt: {prompt}")
    print(f"Frames: {num_frames}")

    for loop in [False, True]:
        tag = "loop" if loop else "noloop"
        print(f"\n--- {tag} ---")
        t0 = time.monotonic()
        all_frames = await asyncio.to_thread(generate_video, rgb_input, prompt, num_frames, loop)
        i2v_time = time.monotonic() - t0
        print(f"I2V: {i2v_time:.1f}s — {len(all_frames)} frames")

        # Save raw GIF
        save_gif(all_frames, subdir / f"raw_{tag}.gif", fps=12)

        # Extract 8 frames + bg removal
        sampled, indices = extract_frames(all_frames)
        t1 = time.monotonic()
        processed = []
        for i, f in enumerate(sampled):
            p = await process_frame(f)
            p.save(subdir / f"{tag}_frame_{i}.png")
            processed.append(p)
        print(f"Post-process ({len(sampled)} frames): {time.monotonic() - t1:.1f}s")

        strip = assemble_strip(processed)
        strip.save(subdir / f"{tag}_strip.png")
        save_gif(processed, subdir / f"{tag}_preview.gif")
        print(f"Extracted frames at indices: {indices}")

    print(f"\nOutput: {subdir}")


async def run_comparison(skip_sprite_gen: bool) -> None:
    """Full comparison: humanoid walk cycles across backgrounds, noise scales, prompts."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SPRITE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Character-aware prompts
    char_prompts = {
        "knight": "A knight in armor walking, legs stepping, cape swinging, side view walk cycle",
        "skeleton": "An animated skeleton walking, bony legs stepping, arms swinging sword, side view walk cycle",
        "robot": "A small robot walking, mechanical legs stepping, arms swinging, antenna bobbing, side view walk cycle",
    }

    # Focus on the 3 best characters from round 1
    chars_to_test = [c for c in CHARACTERS if c["id"] in ("knight", "skeleton", "robot")]

    experiments: list[dict] = []

    # Test 1: Background color (3 chars × 4 backgrounds, game_style prompt, default noise)
    for char in chars_to_test:
        for bg_name, bg_color in BG_COLORS.items():
            experiments.append({
                "char": char, "prompt_name": "game_style", "prompt": PROMPTS["game_style"],
                "num_frames": DEFAULT_FRAME_COUNT, "noise_scale": 0.025,
                "bg_name": bg_name, "bg_color": bg_color,
            })

    # Test 2: Noise scale (3 chars × 3 noise scales, game_style, white bg)
    for char in chars_to_test:
        for ns in NOISE_SCALES:
            if ns == 0.025:
                continue  # already in test 1 (white bg)
            experiments.append({
                "char": char, "prompt_name": "game_style", "prompt": PROMPTS["game_style"],
                "num_frames": DEFAULT_FRAME_COUNT, "noise_scale": ns,
                "bg_name": "white", "bg_color": (255, 255, 255),
            })

    # Test 3: Prompt strategy (3 chars × 3 prompts, white bg, default noise)
    for char in chars_to_test:
        for pname, prompt in PROMPTS.items():
            if pname == "game_style":
                continue  # already in test 1
            actual_prompt = char_prompts.get(char["id"], prompt) if pname == "char_aware" else prompt
            experiments.append({
                "char": char, "prompt_name": pname, "prompt": actual_prompt,
                "num_frames": DEFAULT_FRAME_COUNT, "noise_scale": 0.025,
                "bg_name": "white", "bg_color": (255, 255, 255),
            })

    total = len(experiments)
    print("I2V Walk Cycle Experiment v2")
    print(f"  Model: {MODEL_LABEL}")
    print(f"  {total} experiments total")
    print(f"  Characters: {', '.join(c['id'] for c in chars_to_test)}")
    print(f"  Backgrounds: {', '.join(BG_COLORS.keys())}")
    print(f"  Noise scales: {NOISE_SCALES}")
    print(f"  Prompts: {', '.join(PROMPTS.keys())}")
    print(f"  Extract {EXTRACT_FRAMES} frames + ping-pong per video")
    print(f"  Output: {OUTPUT_DIR}\n")

    t_start = time.monotonic()
    all_results: list[dict] = []

    # Step 1: Generate or load sprites
    sprites: dict[str, Image.Image] = {}
    for char in CHARACTERS:
        if skip_sprite_gen:
            cache_path = SPRITE_CACHE_DIR / f"{char['id']}.png"
            if cache_path.exists():
                sprites[char["id"]] = Image.open(cache_path).convert("RGBA")
                print(f"  Loaded cached sprite: {char['id']}")
            else:
                print(f"  WARNING: No cached sprite for {char['id']}, skipping")
        else:
            try:
                sprites[char["id"]] = await generate_sprite(char["appearance"], char["id"])
            except Exception as e:
                print(f"  FAILED to generate sprite for {char['id']}: {e}")

    if not sprites:
        print("\nNo sprites available. Generate them first or provide --sprite.")
        return

    # Step 2: Load I2V model
    print(f"\n{'='*60}")
    print("Loading I2V model...")
    load_pipeline()

    # Step 3: Run experiments
    for exp_i, exp in enumerate(experiments):
        char = exp["char"]
        if char["id"] not in sprites:
            continue

        sprite = sprites[char["id"]]
        bg_color = exp.get("bg_color", (255, 255, 255))
        bg_name = exp.get("bg_name", "white")
        rgb_input = prepare_i2v_input(sprite, bg_color)
        sprite_rel = f"sprites/{char['id']}.png"
        num_frames = exp["num_frames"]
        prompt_name = exp["prompt_name"]
        prompt = exp["prompt"]
        noise_scale = exp.get("noise_scale", 0.025)

        variant_id = f"{char['id']}_{prompt_name}_{bg_name}_ns{noise_scale}"
        subdir = OUTPUT_DIR / variant_id
        subdir.mkdir(parents=True, exist_ok=True)

        result: dict = {
            "char_id": char["id"],
            "char_desc": char["desc"],
            "sprite_path": sprite_rel,
            "input_path": f"{variant_id}/input.png",
            "prompt_tier": f"{prompt_name} / {bg_name} / ns={noise_scale}",
            "prompt": prompt,
            "num_frames": num_frames,
            "bg_name": bg_name,
            "noise_scale": noise_scale,
            "variant_id": variant_id,
            "i2v_time_s": 0.0,
            "postprocess_time_s": 0.0,
            "total_generated": 0,
            "extracted_indices": [],
            "frames": [],
            "raw_gif": "",
            "error": None,
        }

        print(f"\n[{exp_i+1}/{total}] {variant_id}")

        try:
            rgb_input.save(subdir / "input.png")

            # Generate video
            t0 = time.monotonic()
            all_frames = await asyncio.to_thread(
                generate_video, rgb_input, prompt, num_frames, noise_scale
            )
            result["i2v_time_s"] = round(time.monotonic() - t0, 2)
            result["total_generated"] = len(all_frames)
            print(f"  I2V: {result['i2v_time_s']}s — {len(all_frames)} frames — VRAM: {_vram_str()}")

            # Save raw GIF of ALL frames
            save_gif(all_frames, subdir / "raw_preview.gif", fps=12)
            result["raw_gif"] = f"{variant_id}/raw_preview.gif"

            # Extract 8 evenly-spaced frames
            sampled, indices = extract_frames(all_frames, EXTRACT_FRAMES)
            result["extracted_indices"] = indices

            # Bg removal + crop on extracted frames only
            t1 = time.monotonic()
            processed = []
            for i, f in enumerate(sampled):
                p = await process_frame(f)
                frame_path = f"{variant_id}/frame_{i:02d}.png"
                p.save(subdir / f"frame_{i:02d}.png")
                result["frames"].append(frame_path)
                processed.append(p)
            result["postprocess_time_s"] = round(time.monotonic() - t1, 2)

            # Save sprite sheet strip + processed GIF
            strip = assemble_strip(processed)
            strip.save(subdir / "strip.png")
            save_gif(processed, subdir / "preview.gif")

            # Ping-pong loop version
            pp_frames = pingpong(processed)
            save_gif(pp_frames, subdir / "pingpong.gif")

            print(
                f"  Extracted {len(sampled)} frames at {indices} — "
                f"post: {result['postprocess_time_s']}s"
            )

        except Exception as e:
            result["error"] = f"{type(e).__name__}: {e}"
            print(f"  FAILED: {result['error']}")

        all_results.append(result)

    # Step 4: Save results + dashboard
    wall = time.monotonic() - t_start
    results_path = OUTPUT_DIR / "results.json"
    results_path.write_text(json.dumps(all_results, indent=2), encoding="utf-8")

    dashboard = generate_dashboard(all_results, DEFAULT_FRAME_COUNT)
    dashboard_path = OUTPUT_DIR / "dashboard.html"
    dashboard_path.write_text(dashboard, encoding="utf-8")

    ok = sum(1 for r in all_results if not r["error"])
    print(f"\n{'='*60}")
    print(f"DONE in {wall:.0f}s — {ok}/{total} experiments")
    print(f"Dashboard: {dashboard_path}")
    print(f"Results:   {results_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="I2V animation experiment")
    parser.add_argument("--sprite", type=str, help="Path to a single sprite PNG to animate")
    parser.add_argument("--prompt", type=str, default="walking forward",
                        help="Motion prompt (single-sprite mode)")
    parser.add_argument("--frames", type=int, default=DEFAULT_FRAME_COUNT,
                        help=f"Number of frames (must be 8n+1). Default: {DEFAULT_FRAME_COUNT}")
    parser.add_argument("--skip-sprite-gen", action="store_true",
                        help="Skip sprite generation, use cached sprites only")
    args = parser.parse_args()

    # Validate frame count
    if (args.frames - 1) % 8 != 0:
        valid = [8 * n + 1 for n in range(1, 6)]
        parser.error(f"--frames must be 8n+1 (e.g. {valid}), got {args.frames}")

    if args.sprite:
        asyncio.run(run_single(args.sprite, args.prompt, args.frames))
    else:
        asyncio.run(run_comparison(args.skip_sprite_gen))


if __name__ == "__main__":
    main()
