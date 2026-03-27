#!/usr/bin/env python3
"""Animation reference-image experiment.

Tests whether Gemini can generate consistent animation frames when given
the base sprite as a reference image. Generates idle + walk animations
(4 frames each) for diverse character morphologies.

Two-step approach:
  1. Generate base sprite (text-to-image, same as production pipeline)
  2. LLM generates frame motion descriptions (separate lightweight call)
  3. Generate animation frames (reference image + motion prompt, 8 per subject)

Outputs a dashboard.html for interactive visual comparison.

Usage:
    cd backend && uv run python -m experiments.animation_ref_experiment
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

OUTPUT_DIR = SCRIPT_DIR / "output" / "animation_ref"

IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gemini-3.1-flash-image-preview")
TEXT_MODEL = "gemini-3.1-flash-lite-preview"
CONCURRENCY = 4
TEXTURE_SIZE = 512
FILL_FRACTION = 0.9


# ── Subjects ───────────────────────────────────────────────────────────


@dataclass
class Subject:
    id: str
    name: str
    description: str


SUBJECTS = [
    Subject("goblin", "goblin warrior", "a small green goblin warrior"),
    Subject("fairy", "fairy", "a blue fairy with dragonfly wings"),
    Subject("slime", "pink slime", "a cheerful pink slime"),
    Subject("centipede", "centipede", "a purple segmented centipede"),
    Subject("orb", "crystal orb", "a glowing crystal orb with tendrils"),
    Subject("toysoldier", "toy soldier", "a wooden wind-up toy soldier"),
]


# ── Animation prompt agent ─────────────────────────────────────────────

ANIMATION_SYSTEM_PROMPT = """\
You generate motion frame descriptions for 4-frame sprite animations.
Given a character description, generate frame prompts that describe
ONLY the motion state -- not the character's appearance (that is handled
by a reference image).

CRITICAL RULES:
- Each frame description must be FULLY SELF-CONTAINED. Do not reference
  other frames ("returns to", "back to neutral", "continues from").
  Each description is sent to an image generator INDEPENDENTLY.
- The character ALWAYS faces right in side view.
- Describe the ABSOLUTE pose, not relative change from another frame.
- Describe position/deformation of body parts, not color or style.
- Keep each frame description under 20 words.
- Focus on the PRIMARY moving element for this character type.

LIMB VOCABULARY (side-view characters):
- NEVER use "left leg", "right leg", "left arm", "right arm". These are
  ambiguous in side view (character's perspective vs viewer's) and the
  image model cannot resolve them.
- Use DEPTH-BASED terms:
  "near leg" = closer to camera, fully visible, drawn in front
  "far leg"  = further from camera, partially occluded by body
  "near arm" / "far arm" = same logic
- Use SCREEN-SPACE direction:
  "toward right edge of frame" = forward (direction of travel)
  "toward left edge of frame"  = backward
- Describe OCCLUSION explicitly. In side view, the far leg is naturally
  partially hidden behind the body:
  "far leg partially occluded by torso, only lower portion visible"
- Describe the overall SILHOUETTE SHAPE when useful:
  "triangular leg spread, one leg forward one back"
  "legs close together beneath body"

POSE VOCABULARY:
- Squash/stretch: body compression or elongation. A landing pose is
  squashed (wider, shorter). A jump peak is stretched (taller, narrower).
  Use for soft bodies, fabric, hair, any non-rigid form.
- Follow-through: secondary elements trail behind the main motion.
  A cape drags behind a walking figure. Tentacles trail below a rising
  float. Mention these trailing elements.
- Secondary action: one small supporting detail that sells the pose.
  A tail curling, antennae twitching, a scarf dangling. Add ONE per frame.

MOTION SCALE:
- IDLE: EXTREMELY SUBTLE. Barely perceptible shifts. Think 1-2 pixel
  differences at game scale. Examples: "standing straight, chest
  slightly fuller, tail relaxed", "standing upright, chest neutral,
  tail curled slightly". NO tilting, NO bending, NO visible limb
  movement for idle. Squash/stretch should be near-invisible.
- WALK: Moderate but natural. Use near/far leg depth language.
  Body compresses slightly on contact poses, stretches on passing poses.
  Keep torso mostly upright. No exaggerated lunges.

Character types and their primary motion elements:
- Legged creatures: near/far leg positions, stride silhouette, weight
- Flying creatures: wing angle, hover height, body stretch at peak
- Slimes/blobs: squash on ground contact, stretch at bounce peak
- Snakes/worms: S-curve body shape, coil compression/extension
- Floating/hovering: vertical position, trailing appendages
- Abstract (eyeball, orb): size pulse, tilt angle
- Mechanical/rigid: joint angles, crank position

Generate two animations:
1. IDLE: almost-imperceptible breathing/hovering loop
2. WALK: primary locomotion cycle

Respond ONLY with valid JSON, no markdown fences:
{
  "idle": ["frame1", "frame2", "frame3", "frame4"],
  "walk": ["frame1", "frame2", "frame3", "frame4"]
}"""


def _generate_animation_prompts_sync(description: str) -> dict[str, list[str]]:
    """Use Gemini text model to generate frame descriptions."""
    from google import genai
    from google.genai import types

    client = genai.Client()
    response = client.models.generate_content(
        model=TEXT_MODEL,
        contents=f"Character: {description}",
        config=types.GenerateContentConfig(
            system_instruction=ANIMATION_SYSTEM_PROMPT,
            temperature=0.7,
            response_mime_type="application/json",
        ),
    )
    text = response.text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3].strip()
    return json.loads(text)


# ── Image generation ───────────────────────────────────────────────────


def _build_base_prompt(name: str, description: str) -> str:
    """Build sprite prompt matching production pipeline."""
    parts = [
        "mixed media collage style paper cutout, side view facing right,"
        " flat lighting, clean edges",
        f"{name}, {description}",
        "single centered object, contrasting solid background color, no text",
    ]
    return ", ".join(parts)


def _build_frame_prompt(name: str, motion_description: str) -> str:
    """Build animation frame prompt. Appearance comes from reference image."""
    parts = [
        "mixed media collage style paper cutout, side view facing right,"
        " flat lighting, clean edges",
        f"{name}, {motion_description}",
        "single centered object, contrasting solid background color, no text",
    ]
    return ", ".join(parts)


def _ensure_png(data: bytes) -> bytes:
    """Convert to PNG if Gemini returned JPEG."""
    if data[:4] == b"\x89PNG":
        return data
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _crop_and_fit(img: Image.Image, target_size: int = TEXTURE_SIZE) -> Image.Image:
    """Crop to opaque content and fit within target_size."""
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


def _generate_base_image_sync(prompt: str) -> bytes:
    """Generate a base sprite via Gemini (text-to-image, no reference)."""
    from google import genai
    from google.genai import types

    client = genai.Client()
    response = client.models.generate_content(
        model=IMAGE_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(image_size="512", aspect_ratio="1:1"),
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


def _generate_frame_image_sync(prompt: str, reference_bytes: bytes) -> bytes:
    """Generate an animation frame using reference image + motion prompt."""
    from google import genai
    from google.genai import types

    client = genai.Client()
    contents = [
        types.Part.from_bytes(data=reference_bytes, mime_type="image/png"),
        prompt,
    ]
    response = client.models.generate_content(
        model=IMAGE_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(image_size="512", aspect_ratio="1:1"),
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


# ── Background removal ─────────────────────────────────────────────────


def _remove_bg_sync(image_bytes: bytes) -> bytes:
    """Remove background using BiRefNet (GPU) or rembg fallback."""
    try:
        import torch
        from torchvision import transforms
        from transformers import AutoModelForImageSegmentation

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

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        orig_size = img.size
        input_tensor = transform(img).unsqueeze(0).to(device)
        if device.type == "cuda":
            input_tensor = input_tensor.half()
        with torch.no_grad():
            preds = model(input_tensor)[-1].sigmoid().cpu()
        mask = transforms.ToPILImage()(preds[0].squeeze())
        mask = mask.resize(orig_size, Image.Resampling.LANCZOS)
        result = img.convert("RGBA")
        result.putalpha(mask)
        buf = io.BytesIO()
        result.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        # Fallback: rembg
        from rembg import remove
        return remove(image_bytes, alpha_matting=True)


# Cache the bg removal model to avoid reloading per frame
_bg_model_cache: dict[str, object] = {}


def _remove_bg_cached(image_bytes: bytes) -> bytes:
    """Remove background, caching the model across calls."""
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


# ── Pipeline per subject ───────────────────────────────────────────────

# Semaphores for resource management
_image_sem: asyncio.Semaphore | None = None
_bg_sem: asyncio.Semaphore | None = None


@dataclass
class FrameResult:
    anim_type: str  # "idle" or "walk"
    frame_num: int  # 1-4
    motion_desc: str
    full_prompt: str
    image_path: str
    error: str | None = None


@dataclass
class SubjectResult:
    subject: Subject
    base_prompt: str
    base_image: str
    animation_prompts: dict[str, list[str]]
    frames: list[FrameResult] = field(default_factory=list)
    timing: dict[str, float] = field(default_factory=dict)
    error: str | None = None


async def _generate_and_process_frame(
    subject: Subject,
    anim_type: str,
    frame_num: int,
    motion_desc: str,
    reference_bytes: bytes,
    output_dir: Path,
) -> FrameResult:
    """Generate a single animation frame with reference image."""
    assert _image_sem is not None
    assert _bg_sem is not None

    full_prompt = _build_frame_prompt(subject.name, motion_desc)
    fname = f"{anim_type}_{frame_num}.png"
    result = FrameResult(
        anim_type=anim_type,
        frame_num=frame_num,
        motion_desc=motion_desc,
        full_prompt=full_prompt,
        image_path=f"{subject.id}/{fname}",
    )
    try:
        async with _image_sem:
            raw_bytes = await asyncio.to_thread(
                _generate_frame_image_sync, full_prompt, reference_bytes,
            )
        async with _bg_sem:
            bg_removed = await asyncio.to_thread(_remove_bg_cached, raw_bytes)
        img = Image.open(io.BytesIO(bg_removed)).convert("RGBA")
        img = _crop_and_fit(img)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        (output_dir / fname).write_bytes(buf.getvalue())
        print(f"    [{subject.id}] {anim_type} frame {frame_num} done")
    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"
        print(f"    [{subject.id}] {anim_type} frame {frame_num} FAILED: {result.error}")
    return result


async def process_subject(subject: Subject) -> SubjectResult:
    """Full pipeline for one subject: base sprite + animation frames."""
    assert _image_sem is not None
    assert _bg_sem is not None

    subdir = OUTPUT_DIR / subject.id
    subdir.mkdir(parents=True, exist_ok=True)

    base_prompt = _build_base_prompt(subject.name, subject.description)
    result = SubjectResult(
        subject=subject,
        base_prompt=base_prompt,
        base_image=f"{subject.id}/base.png",
        animation_prompts={},
    )

    # Step 1: Generate base sprite
    print(f"  [{subject.id}] generating base sprite...")
    t0 = time.monotonic()
    try:
        async with _image_sem:
            raw_bytes = await asyncio.to_thread(_generate_base_image_sync, base_prompt)
        async with _bg_sem:
            bg_removed = await asyncio.to_thread(_remove_bg_cached, raw_bytes)
        base_img = Image.open(io.BytesIO(bg_removed)).convert("RGBA")
        base_img = _crop_and_fit(base_img)
        buf = io.BytesIO()
        base_img.save(buf, format="PNG")
        base_bytes = buf.getvalue()
        (subdir / "base.png").write_bytes(base_bytes)
    except Exception as e:
        result.error = f"Base sprite failed: {type(e).__name__}: {e}"
        result.timing["base_s"] = round(time.monotonic() - t0, 2)
        print(f"  [{subject.id}] BASE FAILED: {result.error}")
        return result
    result.timing["base_s"] = round(time.monotonic() - t0, 2)
    print(f"  [{subject.id}] base done ({result.timing['base_s']:.1f}s)")

    # Step 2: Generate animation prompts (parallel with nothing, but timed separately)
    print(f"  [{subject.id}] generating animation prompts...")
    t1 = time.monotonic()
    try:
        anim_prompts = await asyncio.to_thread(
            _generate_animation_prompts_sync, subject.description,
        )
        result.animation_prompts = anim_prompts
    except Exception as e:
        result.error = f"Animation prompts failed: {type(e).__name__}: {e}"
        result.timing["prompts_s"] = round(time.monotonic() - t1, 2)
        print(f"  [{subject.id}] PROMPTS FAILED: {result.error}")
        return result
    result.timing["prompts_s"] = round(time.monotonic() - t1, 2)
    print(f"  [{subject.id}] prompts done ({result.timing['prompts_s']:.1f}s)")
    for anim_type, frames in anim_prompts.items():
        for i, desc in enumerate(frames, 1):
            print(f"    {anim_type} {i}: {desc}")

    # Step 3: Generate all animation frames in parallel
    # Use the processed base sprite (with bg removed) as reference
    print(f"  [{subject.id}] generating {len(anim_prompts)} x 4 animation frames...")
    t2 = time.monotonic()
    tasks = []
    for anim_type, frame_descs in anim_prompts.items():
        for i, desc in enumerate(frame_descs[:4], 1):
            tasks.append(
                _generate_and_process_frame(
                    subject, anim_type, i, desc, base_bytes, subdir,
                )
            )

    frame_results = await asyncio.gather(*tasks)
    result.frames = list(frame_results)
    result.timing["frames_s"] = round(time.monotonic() - t2, 2)
    ok = sum(1 for f in frame_results if not f.error)
    total = len(frame_results)
    print(f"  [{subject.id}] frames done: {ok}/{total} ({result.timing['frames_s']:.1f}s)")

    return result


# ── Dashboard HTML ─────────────────────────────────────────────────────


def generate_dashboard(results: list[SubjectResult]) -> str:
    """Generate an interactive HTML dashboard for viewing results."""
    # Build subjects JSON for the dashboard
    subjects_json = []
    for r in results:
        frames_by_type: dict[str, list[dict]] = {}
        for f in r.frames:
            frames_by_type.setdefault(f.anim_type, []).append({
                "image": f.image_path,
                "prompt": f.full_prompt,
                "motion": f.motion_desc,
                "error": f.error,
            })
        subjects_json.append({
            "id": r.subject.id,
            "name": r.subject.name,
            "description": r.subject.description,
            "base_prompt": r.base_prompt,
            "base_image": r.base_image,
            "animation_prompts": r.animation_prompts,
            "frames": frames_by_type,
            "timing": r.timing,
            "error": r.error,
        })

    data_json = json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "image_model": IMAGE_MODEL,
        "text_model": TEXT_MODEL,
        "subjects": subjects_json,
    }, indent=2)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Animation Reference Experiment</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #1a1a2e;
    color: #e0e0e0;
    font-family: 'Segoe UI', system-ui, sans-serif;
    padding: 24px;
  }}
  h1 {{ font-size: 24px; margin-bottom: 8px; color: #fff; }}
  .meta {{ font-size: 13px; color: #888; margin-bottom: 24px; }}
  .meta span {{ color: #aaa; }}

  .global-controls {{
    display: flex; gap: 16px; align-items: center;
    margin-bottom: 24px; padding: 12px 16px;
    background: #16213e; border: 1px solid #2a2a4a; border-radius: 8px;
  }}
  .global-controls label {{ font-size: 13px; color: #888; }}
  .global-controls input[type=range] {{ width: 100px; }}
  .global-controls .fps-val {{ font-size: 13px; color: #fff; min-width: 36px; }}

  .subject-card {{
    background: #16213e;
    border: 1px solid #2a2a4a;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 24px;
  }}
  .subject-header {{
    display: flex; align-items: center; gap: 12px; margin-bottom: 16px;
  }}
  .subject-header h2 {{ font-size: 18px; color: #9ecfff; }}
  .subject-header .desc {{ font-size: 13px; color: #888; }}
  .subject-header .timing {{
    margin-left: auto; font-size: 12px; color: #666;
  }}

  .subject-body {{
    display: flex; gap: 24px; align-items: flex-start;
  }}

  .base-section {{
    flex-shrink: 0; text-align: center;
  }}
  .base-section h3 {{
    font-size: 12px; color: #7b8794; text-transform: uppercase;
    letter-spacing: 1px; margin-bottom: 8px;
  }}
  .checker-bg {{
    background-image:
      linear-gradient(45deg, #252535 25%, transparent 25%),
      linear-gradient(-45deg, #252535 25%, transparent 25%),
      linear-gradient(45deg, transparent 75%, #252535 75%),
      linear-gradient(-45deg, transparent 75%, #252535 75%);
    background-size: 16px 16px;
    background-position: 0 0, 0 8px, 8px -8px, -8px 0px;
    border: 1px solid #333; border-radius: 4px;
    display: inline-block;
  }}
  .base-section img {{
    width: 128px; height: 128px;
    image-rendering: auto;
    display: block;
  }}

  .anims-section {{ flex: 1; }}

  .anim-row {{
    display: flex; align-items: center; gap: 16px;
    margin-bottom: 16px; padding: 12px;
    background: #0f1a2e; border: 1px solid #2a2a4a; border-radius: 8px;
  }}
  .anim-label {{
    font-size: 13px; font-weight: 600; color: #c0d0e0;
    width: 50px; flex-shrink: 0; text-transform: uppercase;
  }}

  .anim-preview {{
    flex-shrink: 0; cursor: pointer; position: relative;
  }}
  .anim-preview canvas {{
    border: 1px solid #333; border-radius: 4px;
    image-rendering: auto;
  }}
  .anim-preview .pause-icon {{
    position: absolute; top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    font-size: 24px; color: rgba(255,255,255,0.7);
    pointer-events: none; display: none;
  }}
  .anim-preview.paused .pause-icon {{ display: block; }}

  .frame-strip {{
    display: flex; gap: 6px; flex-wrap: wrap; align-items: center;
  }}
  .frame-thumb {{
    display: flex; flex-direction: column; align-items: center; gap: 2px;
    cursor: pointer;
  }}
  .frame-thumb img {{
    width: 64px; height: 64px;
    image-rendering: auto;
    border: 2px solid transparent; border-radius: 4px;
    transition: border-color 0.15s;
  }}
  .frame-thumb img:hover {{ border-color: #5588cc; }}
  .frame-thumb.active img {{
    border-color: #5588cc;
    box-shadow: 0 0 6px rgba(85, 136, 204, 0.4);
  }}
  .frame-thumb .frame-label {{
    font-size: 10px; color: #666;
  }}
  .frame-thumb.error img {{
    border-color: #633;
    opacity: 0.4;
  }}

  .prompt-panel {{
    margin-top: 12px;
  }}
  .prompt-panel summary {{
    font-size: 12px; color: #888; cursor: pointer;
    padding: 4px 0;
  }}
  .prompt-panel summary:hover {{ color: #aaa; }}
  .prompt-content {{
    margin-top: 8px; padding: 12px;
    background: #0a0f1e; border: 1px solid #1a1a3a; border-radius: 6px;
    font-size: 11px; line-height: 1.6; color: #999;
  }}
  .prompt-content .prompt-label {{
    font-weight: 600; color: #7b8794;
    text-transform: uppercase; font-size: 10px;
    letter-spacing: 0.5px; margin-top: 8px;
  }}
  .prompt-content .prompt-label:first-child {{ margin-top: 0; }}
  .prompt-content .prompt-text {{
    margin: 4px 0 8px;
    white-space: pre-wrap; word-break: break-word;
  }}

  .error-banner {{
    background: #2a1520; border: 1px solid #4a2030;
    color: #f08080; padding: 12px; border-radius: 8px;
    font-size: 13px; margin: 8px 0;
  }}
</style>
</head>
<body>

<h1>Animation Reference Experiment</h1>
<div class="meta">
  Image model: <span id="image-model"></span> |
  Text model: <span id="text-model"></span> |
  Generated: <span id="generated-at"></span>
</div>

<div class="global-controls">
  <label>FPS:</label>
  <input type="range" id="fps-slider" min="1" max="8" value="4">
  <span class="fps-val" id="fps-val">4</span>
  <label>Click preview to pause/play</label>
</div>

<div id="subjects-container"></div>

<script>
const DATA = {data_json};

let globalFps = 4;
const animStates = []; // track per-animation state

document.getElementById('image-model').textContent = DATA.image_model;
document.getElementById('text-model').textContent = DATA.text_model;
document.getElementById('generated-at').textContent =
  new Date(DATA.generated_at).toLocaleString();

document.getElementById('fps-slider').addEventListener('input', e => {{
  globalFps = parseInt(e.target.value);
  document.getElementById('fps-val').textContent = globalFps;
}});

const container = document.getElementById('subjects-container');

DATA.subjects.forEach((subject, si) => {{
  const card = document.createElement('div');
  card.className = 'subject-card';

  const timing = subject.timing || {{}};
  const timingStr = Object.entries(timing)
    .map(([k, v]) => `${{k}}: ${{v}}s`).join(' | ');

  let bodyHtml = '';

  if (subject.error) {{
    bodyHtml = `<div class="error-banner">${{subject.error}}</div>`;
  }} else {{
    // Base sprite
    bodyHtml += `
      <div class="subject-body">
        <div class="base-section">
          <h3>Base Sprite</h3>
          <div class="checker-bg">
            <img src="${{subject.base_image}}" alt="base">
          </div>
        </div>
        <div class="anims-section">`;

    // Animation rows
    const animTypes = Object.keys(subject.frames || {{}});
    animTypes.forEach((animType, ai) => {{
      const frames = subject.frames[animType] || [];
      const animId = `anim-${{si}}-${{ai}}`;
      const canvasSize = 128;

      bodyHtml += `
        <div class="anim-row">
          <div class="anim-label">${{animType}}</div>
          <div class="anim-preview" id="${{animId}}-preview">
            <div class="checker-bg">
              <canvas id="${{animId}}-canvas" width="${{canvasSize}}" height="${{canvasSize}}"></canvas>
            </div>
            <div class="pause-icon">||</div>
          </div>
          <div class="frame-strip" id="${{animId}}-strip">`;

      frames.forEach((frame, fi) => {{
        const errorClass = frame.error ? ' error' : '';
        bodyHtml += `
          <div class="frame-thumb${{errorClass}}" data-anim="${{animId}}" data-frame="${{fi}}">
            <div class="checker-bg">
              <img src="${{frame.error ? '' : frame.image}}" alt="frame ${{fi+1}}"
                   onerror="this.style.opacity=0.2">
            </div>
            <span class="frame-label">${{fi+1}}</span>
          </div>`;
      }});

      bodyHtml += `</div></div>`;

      // Track animation state
      animStates.push({{
        id: animId,
        subjectIdx: si,
        animType: animType,
        frames: frames,
        frameIndex: 0,
        paused: false,
        images: [],
        loaded: false,
      }});
    }});

    bodyHtml += `</div></div>`;

    // Prompt panel
    bodyHtml += `
      <div class="prompt-panel">
        <details>
          <summary>Prompts & Details</summary>
          <div class="prompt-content">
            <div class="prompt-label">Base Image Prompt</div>
            <div class="prompt-text">${{subject.base_prompt}}</div>`;

    const prompts = subject.animation_prompts || {{}};
    Object.entries(prompts).forEach(([animType, descs]) => {{
      bodyHtml += `<div class="prompt-label">${{animType}} Frame Descriptions (LLM)</div>`;
      descs.forEach((d, i) => {{
        bodyHtml += `<div class="prompt-text">${{i+1}}. ${{d}}</div>`;
      }});
    }});

    const allFrames = Object.values(subject.frames || {{}}).flat();
    if (allFrames.length > 0) {{
      bodyHtml += `<div class="prompt-label">Full Image Prompts (per frame)</div>`;
      allFrames.forEach(f => {{
        bodyHtml += `<div class="prompt-text">${{f.prompt}}</div>`;
      }});
    }}

    bodyHtml += `</div></details></div>`;
  }}

  card.innerHTML = `
    <div class="subject-header">
      <h2>${{subject.name}}</h2>
      <span class="desc">${{subject.description}}</span>
      <span class="timing">${{timingStr}}</span>
    </div>
    ${{bodyHtml}}
  `;
  container.appendChild(card);
}});

// Load images for animation canvases
animStates.forEach(state => {{
  const validFrames = state.frames.filter(f => !f.error);
  state.images = validFrames.map(f => {{
    const img = new window.Image();
    img.src = f.image;
    return img;
  }});
  // Consider loaded when first image loads (others will follow)
  if (state.images.length > 0) {{
    state.images[0].onload = () => {{ state.loaded = true; }};
  }}

  // Pause/play on click
  const preview = document.getElementById(`${{state.id}}-preview`);
  if (preview) {{
    preview.addEventListener('click', () => {{
      state.paused = !state.paused;
      preview.classList.toggle('paused', state.paused);
    }});
  }}
}});

// Frame thumb click → highlight + show in canvas
document.querySelectorAll('.frame-thumb').forEach(thumb => {{
  thumb.addEventListener('click', () => {{
    const animId = thumb.dataset.anim;
    const frameIdx = parseInt(thumb.dataset.frame);
    const state = animStates.find(s => s.id === animId);
    if (state) {{
      state.frameIndex = frameIdx;
      state.paused = true;
      const preview = document.getElementById(`${{animId}}-preview`);
      if (preview) preview.classList.add('paused');
      drawFrame(state);
      // Highlight active thumb
      document.querySelectorAll(`[data-anim="${{animId}}"]`).forEach(t =>
        t.classList.toggle('active', parseInt(t.dataset.frame) === frameIdx)
      );
    }}
  }});
}});

function drawFrame(state) {{
  const canvas = document.getElementById(`${{state.id}}-canvas`);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  // Checkerboard drawn by CSS on parent, just clear and draw
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const img = state.images[state.frameIndex % state.images.length];
  if (img && img.complete && img.naturalWidth > 0) {{
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  }}
  // Update thumb highlights
  document.querySelectorAll(`[data-anim="${{state.id}}"]`).forEach((t, i) =>
    t.classList.toggle('active', i === state.frameIndex % state.images.length)
  );
}}

let lastTick = 0;
function animate(ts) {{
  const interval = 1000 / globalFps;
  if (ts - lastTick >= interval) {{
    lastTick = ts;
    animStates.forEach(state => {{
      if (!state.paused && state.loaded && state.images.length > 0) {{
        state.frameIndex = (state.frameIndex + 1) % state.images.length;
        drawFrame(state);
      }}
    }});
  }}
  requestAnimationFrame(animate);
}}
requestAnimationFrame(animate);

// Initial draw
setTimeout(() => animStates.forEach(drawFrame), 500);
</script>
</body>
</html>"""


# ── Main ───────────────────────────────────────────────────────────────


async def main() -> None:
    global _image_sem, _bg_sem
    _image_sem = asyncio.Semaphore(CONCURRENCY)
    _bg_sem = asyncio.Semaphore(1)  # GPU bg removal is sequential

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    total_images = len(SUBJECTS) * 9  # 1 base + 8 frames each
    cost_est = total_images * 0.04  # ~$0.04 per image gen

    print("Animation Reference Experiment")
    print(f"  {len(SUBJECTS)} subjects, {total_images} total images")
    print(f"  Image model: {IMAGE_MODEL}")
    print(f"  Text model: {TEXT_MODEL}")
    print(f"  Estimated cost: ~${cost_est:.2f}")
    print(f"  Output: {OUTPUT_DIR}\n")

    t0 = time.monotonic()

    # Process subjects sequentially (each subject does parallel frame gen internally)
    results: list[SubjectResult] = []
    for subject in SUBJECTS:
        print(f"\n{'='*50}")
        print(f"  Processing: {subject.name} ({subject.description})")
        print(f"{'='*50}")
        result = await process_subject(subject)
        results.append(result)

    wall = time.monotonic() - t0

    # Write results.json
    results_data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "image_model": IMAGE_MODEL,
        "text_model": TEXT_MODEL,
        "subjects": [],
    }
    for r in results:
        frames_by_type: dict[str, list[dict]] = {}
        for f in r.frames:
            frames_by_type.setdefault(f.anim_type, []).append({
                "image": f.image_path,
                "prompt": f.full_prompt,
                "motion": f.motion_desc,
                "error": f.error,
            })
        results_data["subjects"].append({
            "id": r.subject.id,
            "name": r.subject.name,
            "description": r.subject.description,
            "base_prompt": r.base_prompt,
            "base_image": r.base_image,
            "animation_prompts": r.animation_prompts,
            "frames": frames_by_type,
            "timing": r.timing,
            "error": r.error,
        })

    results_path = OUTPUT_DIR / "results.json"
    results_path.write_text(json.dumps(results_data, indent=2), encoding="utf-8")

    # Generate dashboard
    dashboard_html = generate_dashboard(results)
    dashboard_path = OUTPUT_DIR / "dashboard.html"
    dashboard_path.write_text(dashboard_html, encoding="utf-8")

    # Summary
    ok_subjects = sum(1 for r in results if not r.error)
    ok_frames = sum(1 for r in results for f in r.frames if not f.error)
    total_frames = sum(len(r.frames) for r in results)
    print(f"\n{'='*60}")
    print(f"DONE in {wall:.0f}s")
    print(f"  Subjects: {ok_subjects}/{len(results)}")
    print(f"  Frames: {ok_frames}/{total_frames}")
    print(f"  Results: {results_path}")
    print(f"  Dashboard: {dashboard_path}")
    if any(r.error for r in results):
        print("\nSubject failures:")
        for r in results:
            if r.error:
                print(f"  {r.subject.id}: {r.error}")


if __name__ == "__main__":
    asyncio.run(main())
