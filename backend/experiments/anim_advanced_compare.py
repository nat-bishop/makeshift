#!/usr/bin/env python3
"""Animation experiment round 3 — advanced strategies.

Tests 5 approaches:
  A. Defensive template 2x2 (hyper-specific prompting against known failures)
  B. Pose reference sheet (stick-figure pose guide + template)
  C. Iterative sequential (multi-turn chat, frames build on prior)
  D. Inbetween interpolation (start/end → middle, bracketing frames only)
  E. Iterative with ALL prior frames (inbetween but full context)

All use response_modalities=["IMAGE"] only.

Usage:
    uv run python -m experiments.anim_advanced_compare
"""

from __future__ import annotations

import asyncio
import io
import json
import math
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

from PIL import Image, ImageDraw

OUTPUT_DIR = SCRIPT_DIR / "output" / "anim_advanced"
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gemini-3.1-flash-image-preview")
BG = "#1a1a1a"

# ── Shared character + pose descriptions ───────────────────────────────

CHARACTER = (
    "A human adventurer in side view facing right. Medium build, wearing a "
    "forest-green tunic belted at the waist, a brown leather backpack with "
    "visible shoulder straps, sturdy brown leather boots reaching mid-calf, "
    "brown trousers, and a short brown cape. Short tousled brown hair. "
    "Mixed media collage style paper cutout art, flat lighting, clean edges."
)

FRAME_DESCS = {
    1: (
        "CONTACT RIGHT pose: Right leg extended forward with heel near ground, "
        "left leg extended behind pushing off. Arms counterbalanced — left arm "
        "swings forward, right arm back. Body at lowest point of stride."
    ),
    2: (
        "PASSING RIGHT pose: Full weight on right leg directly under body, "
        "left leg swinging forward past the planted right leg. Both legs close "
        "together. Body at tallest point of stride. Arms relaxed at sides."
    ),
    3: (
        "CONTACT LEFT pose: Left leg extended forward with heel near ground, "
        "right leg extended behind pushing off. Arms counterbalanced — right arm "
        "swings forward, left arm back. Body at lowest point. Mirror of contact right."
    ),
    4: (
        "PASSING LEFT pose: Full weight on left leg directly under body, "
        "right leg swinging forward past the planted left leg. Both legs close "
        "together. Body at tallest point. Arms relaxed at sides. This pose "
        "transitions smoothly back to the contact right pose."
    ),
}

DEFENSIVE_REQUIREMENTS = (
    "\n\nANIMATION REQUIREMENTS:\n"
    "- The character faces right in ALL FOUR cells. Every cell shows the character "
    "in side view facing toward the right edge of the image.\n"
    "- Each cell shows a DISTINCTLY DIFFERENT leg position. No two cells have "
    "the same pose. The legs must visibly change position from cell to cell.\n"
    "- The four poses form a complete walk cycle: contact-right, passing-right, "
    "contact-left, passing-left. The cycle loops — cell 4 transitions seamlessly "
    "back to cell 1.\n"
    "- The character's body proportions, clothing, colors, and art style are "
    "IDENTICAL across all four cells. Only the limb positions change.\n"
    "- Full body visible from head to toe in every cell, centered in the cell."
)


# ── Helpers ────────────────────────────────────────────────────────────


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


_client_instance = None


def _get_client():
    global _client_instance
    if _client_instance is None:
        from google import genai
        _client_instance = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    return _client_instance


def _call_gemini(
    contents: list,
    system_instruction: str | None = None,
    size: str = "1K",
) -> bytes:
    from google.genai import types

    config_kwargs: dict = {
        "response_modalities": ["IMAGE"],
        "image_config": types.ImageConfig(image_size=size, aspect_ratio="1:1"),
    }
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction

    response = _get_client().models.generate_content(
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


# ── Template generation ────────────────────────────────────────────────


def make_template_2x2() -> bytes:
    size, grid, cell = 1024, 2, 512
    img = Image.new("RGB", (size, size), BG)
    draw = ImageDraw.Draw(img)
    lc = "#ff0000"
    draw.line([(cell, 0), (cell, size - 1)], fill=lc, width=2)
    draw.line([(0, cell), (size - 1, cell)], fill=lc, width=2)
    draw.rectangle([0, 0, size - 1, size - 1], outline=lc, width=2)
    from PIL import ImageFont
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


def template_sys_instr() -> str:
    return (
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


# ── Pose reference image (stick figures) ───────────────────────────────


def make_pose_reference() -> bytes:
    """Draw a 2x2 grid of stick-figure walk cycle poses."""
    size, cell = 1024, 512
    img = Image.new("RGB", (size, size), "#ffffff")
    draw = ImageDraw.Draw(img)

    # Grid lines
    draw.line([(cell, 0), (cell, size - 1)], fill="#cccccc", width=2)
    draw.line([(0, cell), (size - 1, cell)], fill="#cccccc", width=2)

    # Walk cycle poses as stick figures (facing right)
    # Each entry: leg (dx_foot, dy_foot) pairs, arm (dx_hand, dy_hand) pairs, body_y offset
    # Positive dx = toward right (forward), negative = toward left (backward)
    poses = [
        # Contact right: right leg far fwd, left leg far back — wide stride, body low
        {"legs": [(70, 70), (-60, 70)], "arms": [(-40, 55), (35, 55)], "body_y": 15},
        # Passing right: legs together under body, body at tallest
        {"legs": [(5, 85), (-5, 85)], "arms": [(5, 50), (-5, 50)], "body_y": -10},
        # Contact left: left leg far fwd, right leg far back — mirror of contact R
        {"legs": [(-60, 70), (70, 70)], "arms": [(35, 55), (-40, 55)], "body_y": 15},
        # Passing left: legs together under body, body at tallest
        {"legs": [(-5, 85), (5, 85)], "arms": [(-5, 50), (5, 50)], "body_y": -10},
    ]

    positions = [(0, 0), (1, 0), (0, 1), (1, 1)]
    color = "#333333"
    lw = 7

    from PIL import ImageFont
    font = ImageFont.load_default(size=22)

    for (col, row), pose in zip(positions, poses):
        cx = col * cell + cell // 2
        ground_y = row * cell + cell - 50

        # Body baseline
        hip_y = ground_y - 150 + pose["body_y"]
        shoulder_y = hip_y - 110
        head_y = shoulder_y - 35

        # Head
        draw.ellipse(
            [cx - 22, head_y - 22, cx + 22, head_y + 22],
            fill=color,
        )
        # Torso
        draw.line([(cx, shoulder_y), (cx, hip_y)], fill=color, width=lw)

        # Legs (with knee bend)
        for dx, dy in pose["legs"]:
            foot_x = cx + dx
            foot_y = hip_y + dy
            # Knee bends outward from midpoint for natural look
            mid_x = cx + dx * 0.4
            mid_y = hip_y + dy * 0.5
            draw.line([(cx, hip_y), (int(mid_x), int(mid_y))], fill=color, width=lw)
            draw.line([(int(mid_x), int(mid_y)), (int(foot_x), int(foot_y))], fill=color, width=lw)
            # Foot dot
            draw.ellipse(
                [int(foot_x) - 4, int(foot_y) - 4, int(foot_x) + 4, int(foot_y) + 4],
                fill=color,
            )

        # Arms (thinner)
        for dx, dy in pose["arms"]:
            hand_x = cx + dx
            hand_y = shoulder_y + dy
            elbow_x = cx + dx * 0.45
            elbow_y = shoulder_y + dy * 0.5
            draw.line([(cx, shoulder_y), (int(elbow_x), int(elbow_y))], fill=color, width=5)
            draw.line([(int(elbow_x), int(elbow_y)), (int(hand_x), int(hand_y))], fill=color, width=5)

        # Label
        labels = ["1: Contact R", "2: Passing R", "3: Contact L", "4: Passing L"]
        idx = positions.index((col, row))
        draw.text((col * cell + 20, row * cell + 20), labels[idx], fill="#666", font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── Frame slicing + bg removal ─────────────────────────────────────────


def slice_sheet_2x2(img: Image.Image) -> list[Image.Image]:
    w, h = img.size
    cw, ch = w // 2, h // 2
    margin = 4
    frames = []
    for row in range(2):
        for col in range(2):
            frames.append(img.crop((
                col * cw + margin, row * ch + margin,
                (col + 1) * cw - margin, (row + 1) * ch - margin,
            )))
    return frames


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


async def _process_frame(raw_bytes: bytes, out_path: Path) -> None:
    """Bg remove + crop/fit + save a single frame."""
    bg_removed = await asyncio.to_thread(_remove_bg, raw_bytes)
    img = Image.open(io.BytesIO(bg_removed)).convert("RGBA")
    img = _crop_and_fit(img)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(buf.getvalue())


async def _process_sheet(raw_bytes: bytes, subdir: Path) -> list[str]:
    """Slice a 2x2 sheet, bg remove each frame, return relative paths."""
    sheet_img = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
    frames = slice_sheet_2x2(sheet_img)
    paths = []
    for i, frame in enumerate(frames):
        buf = io.BytesIO()
        frame.save(buf, format="PNG")
        frame_path = subdir / f"frame_{i+1}.png"
        await _process_frame(buf.getvalue(), frame_path)
        paths.append(f"{subdir.name}/frame_{i+1}.png")
    return paths


# ── Strategy results ───────────────────────────────────────────────────


@dataclass
class StrategyResult:
    id: str
    name: str
    description: str
    sheet_path: str = ""
    frame_paths: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    generation_order: list[int] = field(default_factory=list)  # order frames were created
    timing_s: float = 0.0
    error: str | None = None


# ── Strategy A: Defensive template ─────────────────────────────────────


async def strategy_A() -> StrategyResult:
    r = StrategyResult(
        "A_defensive", "Defensive template 2x2",
        "Template-guided with hyper-specific character description and defensive constraints against known failures",
    )
    t0 = time.monotonic()
    try:
        template = make_template_2x2()
        prompt = (
            f"{CHARACTER} Walking in a 4-frame walk cycle loop.\n\n"
            f"Step-by-step, the four cells show:\n"
            f"Cell 1: {FRAME_DESCS[1]}\n"
            f"Cell 2: {FRAME_DESCS[2]}\n"
            f"Cell 3: {FRAME_DESCS[3]}\n"
            f"Cell 4: {FRAME_DESCS[4]}\n"
            f"{DEFENSIVE_REQUIREMENTS}\n\n"
            f"Solid {BG} background in every cell."
        )
        r.prompts = [prompt]
        print("    Generating sheet...")
        raw = await asyncio.to_thread(
            _call_gemini,
            [_make_part(template), prompt],
            system_instruction=template_sys_instr(),
        )
        subdir = OUTPUT_DIR / r.id
        subdir.mkdir(parents=True, exist_ok=True)
        (subdir / "sheet.png").write_bytes(raw)
        r.sheet_path = f"{r.id}/sheet.png"
        print("    Processing frames...")
        r.frame_paths = await _process_sheet(raw, subdir)
        r.generation_order = [1, 2, 3, 4]
    except Exception as e:
        r.error = f"{type(e).__name__}: {e}"
        print(f"    FAILED: {r.error}")
    r.timing_s = round(time.monotonic() - t0, 2)
    return r


# ── Strategy B: Pose reference sheet ───────────────────────────────────


async def strategy_B() -> StrategyResult:
    r = StrategyResult(
        "B_pose_ref", "Pose reference sheet",
        "Template + stick-figure pose reference image showing target body positions for each cell",
    )
    t0 = time.monotonic()
    try:
        template = make_template_2x2()
        pose_ref = make_pose_reference()

        # Save pose reference for inspection
        subdir = OUTPUT_DIR / r.id
        subdir.mkdir(parents=True, exist_ok=True)
        (subdir / "pose_reference.png").write_bytes(pose_ref)

        sys_instr = (
            template_sys_instr() + "\n\n"
            "ADDITIONAL: A second reference image is provided showing stick-figure "
            "silhouettes of the 4 target poses. Match the body positions and limb "
            "angles shown in each cell of the pose reference."
        )
        prompt = (
            f"{CHARACTER} Walking in a 4-frame walk cycle loop.\n\n"
            f"The pose reference image shows the target body positions as stick figures. "
            f"Each cell in your output should match the corresponding stick figure's pose:\n"
            f"Cell 1: {FRAME_DESCS[1]}\n"
            f"Cell 2: {FRAME_DESCS[2]}\n"
            f"Cell 3: {FRAME_DESCS[3]}\n"
            f"Cell 4: {FRAME_DESCS[4]}\n"
            f"{DEFENSIVE_REQUIREMENTS}\n\n"
            f"Solid {BG} background in every cell."
        )
        r.prompts = [prompt]
        print("    Generating sheet with pose reference...")
        raw = await asyncio.to_thread(
            _call_gemini,
            [_make_part(template), _make_part(pose_ref), prompt],
            system_instruction=sys_instr,
        )
        (subdir / "sheet.png").write_bytes(raw)
        r.sheet_path = f"{r.id}/sheet.png"
        print("    Processing frames...")
        r.frame_paths = await _process_sheet(raw, subdir)
        r.generation_order = [1, 2, 3, 4]
    except Exception as e:
        r.error = f"{type(e).__name__}: {e}"
        print(f"    FAILED: {r.error}")
    r.timing_s = round(time.monotonic() - t0, 2)
    return r


# ── Strategy C: Iterative sequential (chat) ────────────────────────────


async def strategy_C() -> StrategyResult:
    r = StrategyResult(
        "C_iterative", "Iterative sequential (chat)",
        "Multi-turn chat: generate frames 1→2→3→4, each turn includes all prior frames",
    )
    t0 = time.monotonic()
    subdir = OUTPUT_DIR / r.id
    subdir.mkdir(parents=True, exist_ok=True)

    try:
        from google.genai import types

        client = _get_client()
        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(image_size="512", aspect_ratio="1:1"),
        )
        chat = client.chats.create(model=IMAGE_MODEL, config=config)

        generated_frames: list[bytes] = []

        for frame_num in [1, 2, 3, 4]:
            parts: list = []

            # Include all prior frames as context
            for i, prev_bytes in enumerate(generated_frames):
                parts.append(_make_part(prev_bytes))

            if frame_num == 1:
                prompt = (
                    f"Generate frame 1 of a 4-frame walk cycle animation.\n\n"
                    f"{CHARACTER}\n\n"
                    f"{FRAME_DESCS[1]}\n\n"
                    f"This is the first of 4 frames. The walk cycle goes: "
                    f"contact-right → passing-right → contact-left → passing-left → loops back.\n"
                    f"Full body, head to toe, centered. Solid {BG} background, no text."
                )
            elif frame_num == 4:
                prompt = (
                    f"Generate frame 4 of the walk cycle. The previous {len(generated_frames)} "
                    f"frames are attached above.\n\n"
                    f"{FRAME_DESCS[4]}\n\n"
                    f"CRITICAL: Same character as all previous frames — same proportions, "
                    f"clothing, colors, art style. Only the limb positions change. "
                    f"Character faces right. This frame completes the loop back to frame 1.\n"
                    f"Full body, head to toe, centered. Solid {BG} background, no text."
                )
            else:
                prompt = (
                    f"Generate frame {frame_num} of the walk cycle. The previous "
                    f"{len(generated_frames)} frame(s) are attached above.\n\n"
                    f"{FRAME_DESCS[frame_num]}\n\n"
                    f"CRITICAL: Same character as previous frame(s) — same proportions, "
                    f"clothing, colors, art style. Only the limb positions change. "
                    f"Character faces right.\n"
                    f"Full body, head to toe, centered. Solid {BG} background, no text."
                )

            parts.append(prompt)
            r.prompts.append(prompt)

            print(f"    Generating frame {frame_num} (chat turn {frame_num})...")
            response = await asyncio.to_thread(chat.send_message, parts)

            frame_bytes = None
            for part in response.parts or []:
                if part.inline_data is not None:
                    frame_bytes = _ensure_png(part.inline_data.data)
                    break
            if frame_bytes is None:
                raise ValueError(f"No image in response for frame {frame_num}")

            generated_frames.append(frame_bytes)
            frame_path = subdir / f"frame_{frame_num}.png"
            await _process_frame(frame_bytes, frame_path)
            r.frame_paths.append(f"{r.id}/frame_{frame_num}.png")
            print(f"    Frame {frame_num} done")

        r.generation_order = [1, 2, 3, 4]
    except Exception as e:
        r.error = f"{type(e).__name__}: {e}"
        print(f"    FAILED: {r.error}")
    r.timing_s = round(time.monotonic() - t0, 2)
    return r


# ── Strategy D: Inbetween interpolation (bracketing only) ─────────────


async def strategy_D() -> StrategyResult:
    r = StrategyResult(
        "D_inbetween", "Inbetween interpolation",
        "Generate extremes first (1,3), then fill inbetweens (2,4). Each call sees only its bracketing frames.",
    )
    t0 = time.monotonic()
    subdir = OUTPUT_DIR / r.id
    subdir.mkdir(parents=True, exist_ok=True)

    try:
        frames: dict[int, bytes] = {}

        # Step 1: Generate frame 1 (contact right)
        prompt1 = (
            f"Generate a single character image.\n\n"
            f"{CHARACTER}\n\n"
            f"{FRAME_DESCS[1]}\n\n"
            f"Full body, head to toe, centered. Solid {BG} background, no text."
        )
        r.prompts.append(prompt1)
        print("    Generating frame 1 (contact right)...")
        frames[1] = await asyncio.to_thread(_call_gemini, [prompt1], size="512")

        # Step 2: Generate frame 3 (contact left) with frame 1 as reference
        prompt3 = (
            f"The attached image shows a character in a walking contact pose with one "
            f"leg forward. Generate the SAME character in the OPPOSITE contact pose — "
            f"the other leg is now forward.\n\n"
            f"{FRAME_DESCS[3]}\n\n"
            f"CRITICAL: Same character — identical proportions, clothing, colors, "
            f"art style. Character faces right. Only the leg and arm positions swap.\n"
            f"Full body, head to toe, centered. Solid {BG} background, no text."
        )
        r.prompts.append(prompt3)
        print("    Generating frame 3 (contact left, opposite of 1)...")
        frames[3] = await asyncio.to_thread(
            _call_gemini, [_make_part(frames[1]), prompt3], size="512",
        )

        # Step 3: Generate frame 2 (inbetween 1→3)
        prompt2 = (
            f"The two attached images show frames 1 and 3 of a 4-frame walk cycle. "
            f"Generate the INBETWEEN frame that goes between them — frame 2.\n\n"
            f"{FRAME_DESCS[2]}\n\n"
            f"CRITICAL: Same character as both reference frames — identical proportions, "
            f"clothing, colors, art style. This is the transitional pose between the two "
            f"contact poses. Character faces right.\n"
            f"Full body, head to toe, centered. Solid {BG} background, no text."
        )
        r.prompts.append(prompt2)
        print("    Generating frame 2 (inbetween 1→3)...")
        frames[2] = await asyncio.to_thread(
            _call_gemini, [_make_part(frames[1]), _make_part(frames[3]), prompt2], size="512",
        )

        # Step 4: Generate frame 4 (inbetween 3→1, closing the loop)
        prompt4 = (
            f"The two attached images show frames 3 and 1 of a 4-frame walk cycle. "
            f"Generate the INBETWEEN frame that transitions from frame 3 back to "
            f"frame 1, completing the loop — frame 4.\n\n"
            f"{FRAME_DESCS[4]}\n\n"
            f"CRITICAL: Same character as both reference frames — identical proportions, "
            f"clothing, colors, art style. This is the transitional pose completing the "
            f"walk cycle loop. Character faces right.\n"
            f"Full body, head to toe, centered. Solid {BG} background, no text."
        )
        r.prompts.append(prompt4)
        print("    Generating frame 4 (inbetween 3→1, loop close)...")
        frames[4] = await asyncio.to_thread(
            _call_gemini, [_make_part(frames[3]), _make_part(frames[1]), prompt4], size="512",
        )

        # Save in playback order
        for i in [1, 2, 3, 4]:
            frame_path = subdir / f"frame_{i}.png"
            await _process_frame(frames[i], frame_path)
            r.frame_paths.append(f"{r.id}/frame_{i}.png")

        r.generation_order = [1, 3, 2, 4]
    except Exception as e:
        r.error = f"{type(e).__name__}: {e}"
        print(f"    FAILED: {r.error}")
    r.timing_s = round(time.monotonic() - t0, 2)
    return r


# ── Strategy E: Iterative with ALL prior frames ───────────────────────


async def strategy_E() -> StrategyResult:
    r = StrategyResult(
        "E_inbetween_full", "Inbetween with full context",
        "Same generation order as D (1→3→2→4) but each call includes ALL frames generated so far.",
    )
    t0 = time.monotonic()
    subdir = OUTPUT_DIR / r.id
    subdir.mkdir(parents=True, exist_ok=True)

    try:
        frames: dict[int, bytes] = {}

        # Step 1: Frame 1
        prompt1 = (
            f"Generate a single character image. This will be frame 1 of a 4-frame "
            f"walk cycle animation.\n\n"
            f"{CHARACTER}\n\n"
            f"{FRAME_DESCS[1]}\n\n"
            f"Full body, head to toe, centered. Solid {BG} background, no text."
        )
        r.prompts.append(prompt1)
        print("    Generating frame 1...")
        frames[1] = await asyncio.to_thread(_call_gemini, [prompt1], size="512")

        # Step 2: Frame 3 with frame 1
        prompt3 = (
            f"The attached image is frame 1 of a 4-frame walk cycle. "
            f"Generate frame 3 — the OPPOSITE contact pose.\n\n"
            f"{FRAME_DESCS[3]}\n\n"
            f"CRITICAL: Same character, identical appearance. Only limb positions change. "
            f"Character faces right.\n"
            f"Full body, head to toe, centered. Solid {BG} background, no text."
        )
        r.prompts.append(prompt3)
        print("    Generating frame 3 (with frame 1)...")
        frames[3] = await asyncio.to_thread(
            _call_gemini, [_make_part(frames[1]), prompt3], size="512",
        )

        # Step 3: Frame 2 with frames 1 AND 3
        prompt2 = (
            f"The attached images are frames 1 and 3 of a 4-frame walk cycle. "
            f"Generate frame 2 — the passing pose between them.\n\n"
            f"{FRAME_DESCS[2]}\n\n"
            f"CRITICAL: Same character as both reference frames. This is the transitional "
            f"pose halfway between frame 1 and frame 3. Character faces right.\n"
            f"Full body, head to toe, centered. Solid {BG} background, no text."
        )
        r.prompts.append(prompt2)
        print("    Generating frame 2 (with frames 1, 3)...")
        frames[2] = await asyncio.to_thread(
            _call_gemini,
            [_make_part(frames[1]), _make_part(frames[3]), prompt2],
            size="512",
        )

        # Step 4: Frame 4 with frames 1, 2, AND 3
        prompt4 = (
            f"The attached images are frames 1, 3, and 2 of a 4-frame walk cycle "
            f"(in generation order). Generate frame 4 — the final passing pose that "
            f"loops back to frame 1.\n\n"
            f"{FRAME_DESCS[4]}\n\n"
            f"CRITICAL: Same character as all reference frames. This completes the "
            f"walk cycle loop. Character faces right.\n"
            f"Full body, head to toe, centered. Solid {BG} background, no text."
        )
        r.prompts.append(prompt4)
        print("    Generating frame 4 (with frames 1, 3, 2)...")
        frames[4] = await asyncio.to_thread(
            _call_gemini,
            [_make_part(frames[1]), _make_part(frames[3]), _make_part(frames[2]), prompt4],
            size="512",
        )

        for i in [1, 2, 3, 4]:
            frame_path = subdir / f"frame_{i}.png"
            await _process_frame(frames[i], frame_path)
            r.frame_paths.append(f"{r.id}/frame_{i}.png")

        r.generation_order = [1, 3, 2, 4]
    except Exception as e:
        r.error = f"{type(e).__name__}: {e}"
        print(f"    FAILED: {r.error}")
    r.timing_s = round(time.monotonic() - t0, 2)
    return r


# ── Dashboard ──────────────────────────────────────────────────────────


def generate_dashboard(results: list[StrategyResult]) -> str:
    strats_json = []
    for r in results:
        strats_json.append({
            "id": r.id, "name": r.name, "description": r.description,
            "sheet": r.sheet_path, "frames": r.frame_paths,
            "generation_order": r.generation_order,
            "prompts": r.prompts, "timing_s": r.timing_s, "error": r.error,
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
<title>Animation Advanced Comparison</title>
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
    border: 1px solid #333; border-radius: 4px; cursor: pointer;
  }}
  .sheet-col .label {{ font-size: 10px; color: #555; margin-top: 4px; }}
  .anim-col {{
    display: flex; flex-direction: column; gap: 8px; align-items: center;
  }}
  .anim-preview {{ cursor: pointer; position: relative; }}
  .anim-preview canvas {{ border: 1px solid #333; border-radius: 4px; }}
  .anim-preview .po {{
    position: absolute; top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    font-size: 24px; color: rgba(255,255,255,0.5);
    pointer-events: none; display: none;
  }}
  .anim-preview.paused .po {{ display: block; }}
  .anim-label {{ font-size: 10px; color: #555; }}
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
  .frames-strip {{ display: flex; gap: 6px; flex-wrap: wrap; align-items: flex-end; }}
  .frame-cell {{ cursor: pointer; text-align: center; }}
  .frame-cell img {{
    width: 80px; height: 80px;
    border: 2px solid transparent; border-radius: 3px;
    transition: border-color 0.15s;
  }}
  .frame-cell img:hover {{ border-color: #5588cc; }}
  .frame-cell.active img {{
    border-color: #5588cc;
    box-shadow: 0 0 6px rgba(85,136,204,0.4);
  }}
  .frame-cell .num {{ font-size: 10px; color: #555; }}
  .gen-order {{ font-size: 9px; color: #444; }}
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
    color: #f08080; padding: 8px 12px; border-radius: 6px; font-size: 12px;
  }}
</style>
</head>
<body>

<h1>Animation Advanced Comparison (Round 3)</h1>
<div class="meta">
  Model: <span id="m"></span> | <span id="t"></span>
</div>
<div class="controls">
  <label>FPS:</label>
  <input type="range" id="fps" min="1" max="8" value="4">
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

  let sheetHtml = '';
  if (strat.sheet) {{
    sheetHtml = `
      <div class="sheet-col">
        <a href="${{strat.sheet}}" target="_blank">
          <img src="${{strat.sheet}}" alt="sheet">
        </a>
        <div class="label">Raw sheet</div>
      </div>`;
  }}

  let framesHtml = '';
  strat.frames.forEach((f, fi) => {{
    const genIdx = strat.generation_order ? strat.generation_order.indexOf(fi + 1) + 1 : fi + 1;
    framesHtml += `
      <div class="frame-cell" data-a="${{aid}}" data-f="${{fi}}">
        <div class="checker">
          <img src="${{f}}" alt="f${{fi+1}}" onerror="this.style.opacity=0.2">
        </div>
        <div class="num">Frame ${{fi+1}}</div>
        <div class="gen-order">gen #${{genIdx}}</div>
      </div>`;
  }});

  let promptsHtml = '';
  strat.prompts.forEach((p, pi) => {{
    promptsHtml += `<div class="prompt-text">${{p}}</div>`;
  }});

  card.innerHTML = `
    <div class="strategy-header">
      <h2>${{strat.name}}</h2>
      <span class="strategy-timing">${{strat.timing_s}}s</span>
    </div>
    <div class="strategy-desc">${{strat.description}}</div>
    <div class="strategy-body">
      ${{sheetHtml}}
      <div class="anim-col">
        <div class="anim-preview" id="${{aid}}-p">
          <div class="checker">
            <canvas id="${{aid}}-c" width="128" height="128"></canvas>
          </div>
          <div class="po">||</div>
        </div>
        <div class="anim-label">Animated</div>
      </div>
      <div class="frames-strip">${{framesHtml}}</div>
    </div>
    <details><summary>Prompts (${{strat.prompts.length}})</summary>${{promptsHtml}}</details>`;
  sc.appendChild(card);

  const imgs = strat.frames.map(f => {{
    const img = new window.Image(); img.src = f; return img;
  }});
  const st = {{ id: aid, fi: 0, paused: false, images: imgs, loaded: false }};
  if (imgs.length > 0) imgs[0].onload = () => {{ st.loaded = true; }};
  anims.push(st);

  const pp = document.getElementById(`${{aid}}-p`);
  if (pp) pp.addEventListener('click', () => {{
    st.paused = !st.paused;
    pp.classList.toggle('paused', st.paused);
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
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Save templates/references for inspection
    (OUTPUT_DIR / "template_2x2.png").write_bytes(make_template_2x2())
    (OUTPUT_DIR / "pose_reference.png").write_bytes(make_pose_reference())

    print("Animation Advanced Comparison (Round 3)")
    print(f"  5 strategies, ~21 image generations")
    print(f"  Image model: {IMAGE_MODEL}")
    print(f"  Output: {OUTPUT_DIR}\n")

    t0 = time.monotonic()
    results: list[StrategyResult] = []

    strategies = [
        ("A", strategy_A),
        ("B", strategy_B),
        ("C", strategy_C),
        ("D", strategy_D),
        ("E", strategy_E),
    ]

    for label, fn in strategies:
        print(f"\n{'='*50}")
        print(f"  Strategy {label}")
        print(f"{'='*50}")
        r = await fn()
        results.append(r)
        print(f"  → {r.timing_s}s, {len(r.frame_paths)} frames" +
              (f" ERROR: {r.error}" if r.error else ""))

    wall = time.monotonic() - t0

    dashboard = generate_dashboard(results)
    (OUTPUT_DIR / "dashboard.html").write_text(dashboard, encoding="utf-8")

    ok = sum(1 for r in results if not r.error)
    print(f"\n{'='*60}")
    print(f"DONE in {wall:.0f}s — {ok}/{len(results)} strategies succeeded")
    print(f"Dashboard: {OUTPUT_DIR / 'dashboard.html'}")


if __name__ == "__main__":
    asyncio.run(main())
