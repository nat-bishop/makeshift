"""Sprite sheet operations: split, reassemble, and resize 2x2 grids."""

from __future__ import annotations

import io

from PIL import Image


def split_grid(image_bytes: bytes, grid: int = 2) -> list[bytes]:
    """Split a square image into grid*grid equal quadrant PNGs."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = img.size
    cell_w, cell_h = w // grid, h // grid

    frames: list[bytes] = []
    for row in range(grid):
        for col in range(grid):
            x0, y0 = col * cell_w, row * cell_h
            cell = img.crop((x0, y0, x0 + cell_w, y0 + cell_h))
            buf = io.BytesIO()
            cell.save(buf, format="PNG")
            frames.append(buf.getvalue())
    return frames


def reassemble_grid(frame_bytes_list: list[bytes], grid: int = 2) -> bytes:
    """Reassemble frame PNGs into a single grid sprite sheet."""
    frames = [Image.open(io.BytesIO(fb)).convert("RGBA") for fb in frame_bytes_list]
    fw, fh = frames[0].size
    sheet = Image.new("RGBA", (fw * grid, fh * grid), (0, 0, 0, 0))
    for i, frame in enumerate(frames):
        row, col = divmod(i, grid)
        sheet.paste(frame, (col * fw, row * fh))
    buf = io.BytesIO()
    sheet.save(buf, format="PNG")
    return buf.getvalue()


def resize_sheet(sheet_bytes: bytes, target_frame_size: int, grid: int = 2) -> bytes:
    """Resize a sprite sheet so each frame matches target_frame_size."""
    sheet = Image.open(io.BytesIO(sheet_bytes)).convert("RGBA")
    new_size = target_frame_size * grid
    sheet = sheet.resize((new_size, new_size), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    sheet.save(buf, format="PNG")
    return buf.getvalue()
