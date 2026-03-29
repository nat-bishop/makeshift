"""Generate kick animation frames using Gemini with the existing sprite sheet as reference."""

from __future__ import annotations

import asyncio
import io
import sys
from pathlib import Path

from PIL import Image

# Add backend to path so we can import app.config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SPRITE_SHEET = Path(__file__).resolve().parent.parent.parent / "godot/assets/sprites/player/player_sheet.png"
RAW_OUTPUT = Path(__file__).resolve().parent / "player_kick_raw.png"
FINAL_SHEET = SPRITE_SHEET  # overwrite in place


PROMPT = """\
Using the attached sprite sheet as reference for the character design and art style, \
create exactly 2 animation frames side by side (1 row, 2 columns) showing this character doing a kick attack. \
Left frame: wind-up pose, the character's LEFT leg (the front leg) is raised preparing to kick forward. \
Right frame: the same LEFT leg is now fully extended forward in a powerful kick to the right. \
Character faces right in both frames. The LEFT leg (front leg) does the kicking in both frames. \
Same chibi proportions, same hat/vest/shorts/boots outfit. \
Solid black background, no text, no labels. 2 frames only, large, filling the image.\
"""


async def generate() -> None:
    from google import genai
    from google.genai import types

    from app.config import settings

    client = genai.Client(api_key=settings.google_api_key)

    # Load reference image
    sheet_bytes = SPRITE_SHEET.read_bytes()
    print(f"Loaded reference sheet: {len(sheet_bytes)} bytes")

    ref_part = types.Part.from_bytes(data=sheet_bytes, mime_type="image/png")

    print(f"Generating with model: {settings.image_model}")
    response = await client.aio.models.generate_content(
        model=settings.image_model,
        contents=[ref_part, PROMPT],
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(
                image_size="512",
                aspect_ratio="1:1",
            ),
        ),
    )

    if response.parts is None:
        reason = "unknown"
        if response.candidates and response.candidates[0].finish_reason:
            reason = str(response.candidates[0].finish_reason)
        print(f"Generation blocked: {reason}")
        return

    for part in response.parts:
        if part.inline_data is not None:
            raw_bytes = part.inline_data.data
            # Ensure PNG
            img = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
            img.save(RAW_OUTPUT, format="PNG")
            print(f"Saved raw output: {RAW_OUTPUT} ({img.size[0]}x{img.size[1]})")
            return

    print("No image data in response")


if __name__ == "__main__":
    asyncio.run(generate())
