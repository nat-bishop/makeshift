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


# ── Prompt tiers ──────────────────────────────────────────────────────

PROMPTS = {
    "minimal": "A gentle walk cycle animation",
    "style_anchored": (
        "2D paper cutout sprite performing a gentle walk cycle, "
        "flat side view, no perspective change, no camera movement"
    ),
    "constrained": (
        "2D flat paper cutout game sprite walk cycle animation. "
        "Side view facing right. No rotation, no 3D perspective, no zoom, "
        "no camera movement. Character stays centered. Only limbs move."
    ),
}


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

    from app.images.pipeline import _crop_and_fit, get_generate_image, get_remove_bg

    prompt = SPRITE_PROMPT_TEMPLATE.format(appearance=appearance)
    print(f"  Generating sprite for {char_id}...")
    generate_image = get_generate_image()
    raw_bytes = await generate_image(prompt)
    remove_bg = get_remove_bg()
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


def load_pipeline():
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    import torch
    from diffusers import LTXImageToVideoPipeline

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
    _pipeline = LTXImageToVideoPipeline.from_single_file(
        MODEL_CKPT,
        text_encoder=text_encoder,
        tokenizer=tokenizer,
        torch_dtype=torch.bfloat16,
    )
    _pipeline.to("cuda")

    dt = time.monotonic() - t0
    print(f"  Model loaded in {dt:.1f}s — VRAM: {_vram_str()}")
    return _pipeline


def generate_video(
    image: Image.Image, prompt: str, num_frames: int = 9
) -> list[Image.Image]:
    """Run I2V inference. Returns list of PIL Images (num_frames total)."""
    pipe = load_pipeline()
    output = pipe(
        image=image,
        prompt=prompt,
        num_frames=num_frames,
        height=512,
        width=512,
        num_inference_steps=8,
        guidance_scale=1.0,
        output_type="pil",
    )
    return output.frames[0]


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
<div class="meta">Model: {MODEL_LABEL} | Frames: {num_frames} | <span id="t"></span></div>
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
      <div class="variant-header"><h3>${{v.prompt_tier}}</h3>
        <span class="variant-timing">${{v.i2v_time_s}}s i2v + ${{v.postprocess_time_s}}s post</span></div>
      <div class="variant-body">
        <div class="anim-col">
          <div class="anim-preview" id="${{aid}}-p">
            <div class="checker"><canvas id="${{aid}}-c" width="120" height="120"></canvas></div>
            <div class="po">||</div>
          </div>
        </div>
        <div class="frames-strip">${{fHtml}}</div>
      </div>
      <details class="raw-frames"><summary>Raw I2V output frames</summary>
        <div class="strip">${{rawHtml}}</div></details>
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

    # Generate video
    t0 = time.monotonic()
    frames = await asyncio.to_thread(generate_video, rgb_input, prompt, num_frames)
    i2v_time = time.monotonic() - t0
    print(f"I2V generation: {i2v_time:.1f}s — {len(frames)} frames — VRAM: {_vram_str()}")

    # Save raw frames
    for i, f in enumerate(frames):
        f.save(subdir / f"raw_frame_{i:02d}.png")

    # Post-process
    t1 = time.monotonic()
    processed = []
    for i, f in enumerate(frames):
        p = await process_frame(f)
        p.save(subdir / f"frame_{i:02d}.png")
        processed.append(p)
    post_time = time.monotonic() - t1
    print(f"Post-processing: {post_time:.1f}s")

    # Assemble outputs
    strip = assemble_strip(processed)
    strip.save(subdir / "strip.png")
    save_gif(processed, subdir / "preview.gif")

    print(f"\nOutput: {subdir}")
    print(f"  strip.png — horizontal spritesheet")
    print(f"  preview.gif — animated preview")
    print(f"  frame_*.png — individual processed frames")
    print(f"  raw_frame_*.png — raw I2V output")


async def run_comparison(num_frames: int, skip_sprite_gen: bool) -> None:
    """Full comparison: 4 characters x 3 prompt tiers."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SPRITE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    total = len(CHARACTERS) * len(PROMPTS)
    print("I2V Animation Experiment")
    print(f"  Model: {MODEL_LABEL}")
    print(f"  {len(CHARACTERS)} characters x {len(PROMPTS)} prompt tiers = {total} videos")
    print(f"  Frames per video: {num_frames}")
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

    # Step 3: Run comparisons
    for char in CHARACTERS:
        if char["id"] not in sprites:
            continue

        sprite = sprites[char["id"]]
        rgb_input = prepare_i2v_input(sprite)
        sprite_rel = f"sprites/{char['id']}.png"

        print(f"\n{'='*60}")
        print(f"  {char['id']} — {char['desc']}")
        print(f"{'='*60}")

        for tier_name, prompt in PROMPTS.items():
            result: dict = {
                "char_id": char["id"],
                "char_desc": char["desc"],
                "sprite_path": sprite_rel,
                "prompt_tier": tier_name,
                "prompt": prompt,
                "i2v_time_s": 0.0,
                "postprocess_time_s": 0.0,
                "frames": [],
                "raw_frames": [],
                "error": None,
            }
            subdir = OUTPUT_DIR / char["id"] / tier_name
            subdir.mkdir(parents=True, exist_ok=True)

            try:
                # Save input for reference
                rgb_input.save(subdir / "input.png")

                # Generate video
                print(f"  [{tier_name}] generating {num_frames} frames...")
                t0 = time.monotonic()
                frames = await asyncio.to_thread(generate_video, rgb_input, prompt, num_frames)
                result["i2v_time_s"] = round(time.monotonic() - t0, 2)
                print(f"    I2V: {result['i2v_time_s']}s — VRAM: {_vram_str()}")

                # Save raw frames
                for i, f in enumerate(frames):
                    raw_path = f"{char['id']}/{tier_name}/raw_frame_{i:02d}.png"
                    f.save(subdir / f"raw_frame_{i:02d}.png")
                    result["raw_frames"].append(raw_path)

                # Post-process: bg removal + crop
                print(f"  [{tier_name}] post-processing...")
                t1 = time.monotonic()
                processed = []
                for i, f in enumerate(frames):
                    p = await process_frame(f)
                    frame_path = f"{char['id']}/{tier_name}/frame_{i:02d}.png"
                    p.save(subdir / f"frame_{i:02d}.png")
                    result["frames"].append(frame_path)
                    processed.append(p)
                result["postprocess_time_s"] = round(time.monotonic() - t1, 2)

                # Assemble strip + GIF
                strip = assemble_strip(processed)
                strip.save(subdir / "strip.png")
                save_gif(processed, subdir / "preview.gif")

                print(
                    f"  [{tier_name}] done — "
                    f"{result['i2v_time_s']}s i2v + {result['postprocess_time_s']}s post"
                )

            except Exception as e:
                result["error"] = f"{type(e).__name__}: {e}"
                print(f"  [{tier_name}] FAILED: {result['error']}")

            all_results.append(result)

    # Step 4: Save results + dashboard
    wall = time.monotonic() - t_start
    results_path = OUTPUT_DIR / "results.json"
    results_path.write_text(json.dumps(all_results, indent=2), encoding="utf-8")

    dashboard = generate_dashboard(all_results, num_frames)
    dashboard_path = OUTPUT_DIR / "dashboard.html"
    dashboard_path.write_text(dashboard, encoding="utf-8")

    ok = sum(1 for r in all_results if not r["error"])
    print(f"\n{'='*60}")
    print(f"DONE in {wall:.0f}s — {ok}/{total} videos generated")
    print(f"Dashboard: {dashboard_path}")
    print(f"Results:   {results_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="I2V animation experiment")
    parser.add_argument("--sprite", type=str, help="Path to a single sprite PNG to animate")
    parser.add_argument("--prompt", type=str, default="A gentle walk cycle animation",
                        help="Motion prompt (single-sprite mode)")
    parser.add_argument("--frames", type=int, default=9,
                        help="Number of frames (must be 8n+1: 9, 17, 25). Default: 9")
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
        asyncio.run(run_comparison(args.frames, args.skip_sprite_gen))


if __name__ == "__main__":
    main()
