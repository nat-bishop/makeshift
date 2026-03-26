"""Tests for sprite sheet operations."""

from __future__ import annotations

import io

from app.images.spritesheet import reassemble_grid, resize_sheet, split_grid
from PIL import Image


def _make_colored_image(size: int, color: tuple[int, int, int, int]) -> bytes:
    """Create a solid-color RGBA image and return PNG bytes."""
    img = Image.new("RGBA", (size, size), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_grid_image(size: int) -> bytes:
    """Create a 2x2 grid image with 4 distinct colored quadrants."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    half = size // 2
    colors = [
        (255, 0, 0, 255),
        (0, 255, 0, 255),
        (0, 0, 255, 255),
        (255, 255, 0, 255),
    ]
    for i, color in enumerate(colors):
        row, col = divmod(i, 2)
        for y in range(row * half, (row + 1) * half):
            for x in range(col * half, (col + 1) * half):
                img.putpixel((x, y), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_split_grid_produces_4_frames() -> None:
    grid_bytes = _make_grid_image(1024)
    frames = split_grid(grid_bytes, grid=2)
    assert len(frames) == 4


def test_split_grid_frame_size() -> None:
    grid_bytes = _make_grid_image(1024)
    frames = split_grid(grid_bytes, grid=2)
    for frame_bytes in frames:
        img = Image.open(io.BytesIO(frame_bytes))
        assert img.size == (512, 512)


def test_split_grid_preserves_colors() -> None:
    grid_bytes = _make_grid_image(100)
    frames = split_grid(grid_bytes, grid=2)

    expected_colors = [
        (255, 0, 0, 255),
        (0, 255, 0, 255),
        (0, 0, 255, 255),
        (255, 255, 0, 255),
    ]
    for frame_bytes, expected in zip(frames, expected_colors, strict=True):
        img = Image.open(io.BytesIO(frame_bytes)).convert("RGBA")
        pixel = img.getpixel((img.size[0] // 2, img.size[1] // 2))
        assert pixel == expected


def test_reassemble_grid_size() -> None:
    frames = [_make_colored_image(64, (255, 0, 0, 255)) for _ in range(4)]
    sheet_bytes = reassemble_grid(frames, grid=2)
    img = Image.open(io.BytesIO(sheet_bytes))
    assert img.size == (128, 128)


def test_split_reassemble_roundtrip() -> None:
    original = _make_grid_image(200)
    frames = split_grid(original, grid=2)
    reassembled = reassemble_grid(frames, grid=2)

    orig_img = Image.open(io.BytesIO(original)).convert("RGBA")
    result_img = Image.open(io.BytesIO(reassembled)).convert("RGBA")
    assert orig_img.size == result_img.size

    # Check center pixels of each quadrant match
    half = orig_img.size[0] // 2
    for qr in range(2):
        for qc in range(2):
            cx = qc * half + half // 2
            cy = qr * half + half // 2
            assert orig_img.getpixel((cx, cy)) == result_img.getpixel((cx, cy))


def test_resize_sheet() -> None:
    frames = [_make_colored_image(64, (255, 0, 0, 255)) for _ in range(4)]
    sheet_bytes = reassemble_grid(frames, grid=2)
    resized = resize_sheet(sheet_bytes, target_frame_size=32, grid=2)
    img = Image.open(io.BytesIO(resized))
    assert img.size == (64, 64)  # 32 * 2


def test_resize_sheet_is_png() -> None:
    frames = [_make_colored_image(64, (255, 0, 0, 255)) for _ in range(4)]
    sheet_bytes = reassemble_grid(frames, grid=2)
    resized = resize_sheet(sheet_bytes, target_frame_size=48, grid=2)
    assert resized[:8] == b"\x89PNG\r\n\x1a\n"
