#!/usr/bin/env python3
from __future__ import annotations
"""Asset Generator CLI - creates images and sprite sheets via Gemini.

Subcommands:
  image        Generate a PNG from a prompt (5-15 cents depending on size)
  spritesheet  Generate a 4x4 sprite sheet with template (7 cents)

Output: JSON to stdout. Progress to stderr.
"""

import argparse
import json
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).parent
TEMPLATE_SCRIPT = TOOLS_DIR / "spritesheet_template.py"

IMAGE_MODELS = {
    "flash": "gemini-3.1-flash-image-preview",
    "pro": "gemini-3-pro-image-preview",
}

IMAGE_SIZES = ["512", "1K", "2K", "4K"]
IMAGE_COSTS = {"512": 5, "1K": 7, "2K": 10, "4K": 15}
IMAGE_ASPECT_RATIOS = [
    "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1",
    "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9",
]

SPRITESHEET_SYSTEM_TPL = """\
Using the attached template image as an exact layout guide: generate a sprite sheet.
The image is a 4x4 grid of 16 equal cells separated by red lines.
Replace each numbered cell with the corresponding content, reading left-to-right, \
top-to-bottom (cell 1 = first, cell 16 = last).

Rules:
- KEEP the red grid lines exactly where they are in the template — do not remove, \
shift, or paint over them
- Each cell's content must be CENTERED in its cell and must NOT cross into adjacent cells
- CRITICAL: fill ALL empty space in every cell with flat solid {bg_color} — no gradients, \
no scenery, no patterns, just the plain color
- Maintain consistent style, lighting direction, and proportions across all 16 cells
- CRITICAL: do NOT draw the numbered circles from the template onto the output — replace \
them entirely with the actual drawing content"""


def result_json(
    ok: bool,
    path: str | None = None,
    cost_cents: int = 0,
    error: str | None = None,
):
    d: dict = {"ok": ok, "cost_cents": cost_cents}
    if path:
        d["path"] = path
    if error:
        d["error"] = error
    print(json.dumps(d))


def _load_env():
    """Load .env file from project root if present."""
    import os
    for candidate in [Path.cwd() / ".env", Path.cwd().parent / ".env"]:
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip().strip("'\""))
            break


def _genai():
    _load_env()
    from google import genai
    from google.genai import types
    return genai, types


def cmd_image(args):
    genai, types = _genai()
    model = IMAGE_MODELS[args.model]
    size = args.size
    cost = IMAGE_COSTS[size]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    thinking = getattr(args, "thinking", None)
    thinking_config = None
    if thinking:
        thinking_config = types.ThinkingConfig(
            thinking_level=thinking.capitalize(),
            include_thoughts=True,
        )

    config = types.GenerateContentConfig(
        response_modalities=["TEXT", "IMAGE"],
        image_config=types.ImageConfig(
            image_size=size,
            aspect_ratio=args.aspect_ratio,
        ),
        thinking_config=thinking_config,
    )
    label = f"{args.model} {size} {args.aspect_ratio}"
    if thinking:
        label += f" thinking={thinking}"
    print(f"Generating image ({label})...", file=sys.stderr)

    client = genai.Client()
    contents = []
    for ref_path in (args.ref or []):
        ref_bytes = Path(ref_path).read_bytes()
        contents.append(types.Part.from_bytes(data=ref_bytes, mime_type="image/png"))
    contents.append(args.prompt)
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )

    if response.parts is None:
        reason = "unknown"
        if response.candidates and response.candidates[0].finish_reason:
            reason = response.candidates[0].finish_reason
        result_json(False, error=f"Generation blocked (reason: {reason})")
        sys.exit(1)

    saved = False
    for part in response.parts:
        if getattr(part, "thought", False):
            if part.text:
                print(f"[thought] {part.text}", file=sys.stderr)
            continue
        if part.text:
            print(f"[model] {part.text}", file=sys.stderr)
        if part.inline_data is not None and not saved:
            output.write_bytes(part.inline_data.data)
            print(f"Saved: {output}", file=sys.stderr)
            result_json(True, path=str(output), cost_cents=cost)
            saved = True

    if not saved:
        result_json(False, error="No image returned")
        sys.exit(1)


def generate_template(bg_color: str) -> bytes:
    """Generate a template PNG on the fly with the given BG color."""
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp = f.name
    subprocess.run(
        [sys.executable, str(TEMPLATE_SCRIPT), "-o", tmp, "--bg", bg_color],
        check=True,
        capture_output=True,
    )
    data = Path(tmp).read_bytes()
    Path(tmp).unlink()
    return data


def cmd_spritesheet(args):
    genai, types = _genai()
    model = IMAGE_MODELS[args.model]
    cost = IMAGE_COSTS["1K"]  # 7 cents
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    bg = args.bg
    template_bytes = generate_template(bg)
    system = SPRITESHEET_SYSTEM_TPL.format(bg_color=bg)
    print(f"Generating sprite sheet ({args.model}, bg={bg})...", file=sys.stderr)

    client = genai.Client()
    response = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=template_bytes, mime_type="image/png"),
            args.prompt,
        ],
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            system_instruction=system,
            image_config=types.ImageConfig(
                image_size="1K",
                aspect_ratio="1:1",
            ),
        ),
    )

    if response.parts is None:
        reason = "unknown"
        if response.candidates and response.candidates[0].finish_reason:
            reason = response.candidates[0].finish_reason
        result_json(False, error=f"Generation blocked (reason: {reason})")
        sys.exit(1)

    for part in response.parts:
        if part.inline_data is not None:
            output.write_bytes(part.inline_data.data)
            print(f"Saved: {output}", file=sys.stderr)
            result_json(True, path=str(output), cost_cents=cost)
            return

    result_json(False, error="No image returned")
    sys.exit(1)


def cmd_chat(args):
    """Multi-turn image editing chat. Each prompt generates an image, and the model
    sees the full conversation history (including its own previous outputs) for
    style consistency across turns."""
    genai, types = _genai()
    model = IMAGE_MODELS[args.model]
    size = args.size
    cost_per_turn = IMAGE_COSTS[size]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    config = types.GenerateContentConfig(
        response_modalities=["TEXT", "IMAGE"],
        image_config=types.ImageConfig(
            image_size=size,
            aspect_ratio=args.aspect_ratio,
        ),
    )

    client = genai.Client()
    chat = client.chats.create(model=model, config=config)

    prompts = args.prompts  # list of "output_name:prompt text"
    total_cost = 0

    for i, entry in enumerate(prompts):
        name, _, prompt = entry.partition(":")
        if not prompt:
            prompt = name
            name = f"{i+1:02d}"

        parts = []
        # Attach reference images only on the first turn
        if i == 0:
            for ref_path in (args.ref or []):
                ref_bytes = Path(ref_path).read_bytes()
                parts.append(types.Part.from_bytes(data=ref_bytes, mime_type="image/png"))
        parts.append(prompt)

        label = f"Turn {i+1}/{len(prompts)}: {name}"
        print(f"[{label}] Generating ({args.model} {size} {args.aspect_ratio})...", file=sys.stderr)

        response = chat.send_message(parts)
        total_cost += cost_per_turn

        if response.parts is None:
            reason = "unknown"
            if response.candidates and response.candidates[0].finish_reason:
                reason = response.candidates[0].finish_reason
            print(f"[{label}] FAILED: {reason}", file=sys.stderr)
            result_json(False, error=f"Turn {i+1} blocked: {reason}", cost_cents=total_cost)
            sys.exit(1)

        # Save image and print any text
        saved = False
        for part in response.parts:
            if part.text:
                print(f"[{label}] Model: {part.text}", file=sys.stderr)
            if part.inline_data is not None and not saved:
                out_path = out_dir / f"{name}.png"
                out_path.write_bytes(part.inline_data.data)
                print(f"[{label}] Saved: {out_path}", file=sys.stderr)
                saved = True

        if not saved:
            print(f"[{label}] WARNING: No image in response", file=sys.stderr)

    result_json(True, path=str(out_dir), cost_cents=total_cost)


def main():
    parser = argparse.ArgumentParser(
        description="Asset Generator — images and sprite sheets via Gemini"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_img = sub.add_parser("image", help="Generate a PNG image (5-15¢)")
    p_img.add_argument("--prompt", required=True, help="Full image generation prompt")
    p_img.add_argument(
        "--model", choices=list(IMAGE_MODELS), default="flash",
        help="flash (faster/cheaper) or pro (higher quality for hero assets)",
    )
    p_img.add_argument(
        "--size", choices=IMAGE_SIZES, default="1K",
        help="Resolution: 512 (5¢), 1K (7¢), 2K (10¢), 4K (15¢)",
    )
    p_img.add_argument(
        "--aspect-ratio", choices=IMAGE_ASPECT_RATIOS, default="1:1",
    )
    p_img.add_argument("--ref", action="append", help="Reference image(s) to pass alongside the prompt (repeatable)")
    p_img.add_argument("--thinking", choices=["minimal", "high"], default=None, help="Thinking level (Flash 3.1 only)")
    p_img.add_argument("-o", "--output", required=True, help="Output PNG path")
    p_img.set_defaults(func=cmd_image)

    p_ss = sub.add_parser("spritesheet", help="Generate 4x4 sprite sheet (7¢)")
    p_ss.add_argument(
        "--prompt", required=True,
        help="What to generate (animation description or item list)",
    )
    p_ss.add_argument(
        "--model", choices=list(IMAGE_MODELS), default="flash",
        help="flash (faster/cheaper) or pro (higher quality for hero assets)",
    )
    p_ss.add_argument(
        "--bg", default="#808080",
        help="Background color hex. Choose a color absent from the subject.",
    )
    p_ss.add_argument("-o", "--output", required=True, help="Output PNG path")
    p_ss.set_defaults(func=cmd_spritesheet)

    p_chat = sub.add_parser("chat", help="Multi-turn image editing chat (7-15¢ per turn)")
    p_chat.add_argument(
        "--model", choices=list(IMAGE_MODELS), default="flash",
        help="flash (faster/cheaper) or pro (higher quality)",
    )
    p_chat.add_argument(
        "--size", choices=IMAGE_SIZES, default="1K",
        help="Resolution per turn: 1K (7¢), 2K (10¢), 4K (15¢)",
    )
    p_chat.add_argument(
        "--aspect-ratio", choices=IMAGE_ASPECT_RATIOS, default="1:1",
    )
    p_chat.add_argument(
        "--ref", action="append",
        help="Reference image(s) sent with the first prompt (repeatable)",
    )
    p_chat.add_argument(
        "-p", "--prompts", nargs="+", required=True,
        help="Prompts as 'name:prompt text' (name becomes output filename). "
             "Each prompt is a new turn in the conversation.",
    )
    p_chat.add_argument("-o", "--out-dir", required=True, help="Output directory for generated PNGs")
    p_chat.set_defaults(func=cmd_chat)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
