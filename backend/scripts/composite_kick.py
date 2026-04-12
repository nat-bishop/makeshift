"""Extract kick frames from raw 2-up image, remove backgrounds, and composite onto player sprite sheet."""

import asyncio
import io
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SPRITE_SHEET = Path(__file__).resolve().parent.parent.parent / "godot/assets/sprites/player/player_sheet.png"
RAW_KICK = Path(__file__).resolve().parent / "player_kick_raw.png"
FRAME_SIZE = 248
ORIGINAL_ROWS = 4  # idle, walk, jump, fall
ORIGINAL_HEIGHT = FRAME_SIZE * ORIGINAL_ROWS  # 992


async def main() -> None:
    from app.images.pipeline import _crop_and_fit, remove_bg
    from app.logging_setup import setup_logging

    setup_logging()

    sheet = Image.open(SPRITE_SHEET).convert("RGBA")
    raw = Image.open(RAW_KICK).convert("RGBA")

    # Restore original sheet if it already has a kick row
    if sheet.height > ORIGINAL_HEIGHT:
        print(f"Restoring original sheet from {sheet.height}px to {ORIGINAL_HEIGHT}px")
        sheet = sheet.crop((0, 0, sheet.width, ORIGINAL_HEIGHT))

    w, h = raw.size
    half_w = w // 2

    # Extract square center crops from each half
    # Each half is half_w × h; take the largest centered square
    square_size = min(half_w, h)
    y_offset = (h - square_size) // 2

    frame1_raw = raw.crop((0, y_offset, half_w, y_offset + square_size))
    frame2_raw = raw.crop((half_w, y_offset, w, y_offset + square_size))

    # Remove backgrounds using the project's bg removal pipeline
    frames = []
    for i, frame_img in enumerate([frame1_raw, frame2_raw]):
        buf = io.BytesIO()
        frame_img.save(buf, format="PNG")
        raw_bytes = buf.getvalue()

        print(f"Removing background from frame {i + 1}...")
        clean_bytes = await remove_bg(raw_bytes)

        clean_img = Image.open(io.BytesIO(clean_bytes)).convert("RGBA")
        centered = _crop_and_fit(clean_img, FRAME_SIZE, fill_fraction=0.85)
        frames.append(centered)
        print(f"Frame {i + 1}: done ({centered.size})")

    # Expand sheet: add one row
    new_height = ORIGINAL_HEIGHT + FRAME_SIZE
    new_sheet = Image.new("RGBA", (sheet.width, new_height), (0, 0, 0, 0))
    new_sheet.paste(sheet, (0, 0))

    # Place 2 frames in slots 0 and 1 of the new row
    y = ORIGINAL_HEIGHT
    new_sheet.paste(frames[0], (0, y))
    new_sheet.paste(frames[1], (FRAME_SIZE, y))

    new_sheet.save(SPRITE_SHEET, format="PNG")
    print(f"Saved: {SPRITE_SHEET} ({new_sheet.width}x{new_sheet.height})")


if __name__ == "__main__":
    asyncio.run(main())
