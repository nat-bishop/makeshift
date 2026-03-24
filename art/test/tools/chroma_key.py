#!/usr/bin/env python3
"""Chroma key background removal — replaces a solid color with transparency.

Better than rembg for landscape layers where the subject and background have clear
color separation. Uses smooth alpha transition at edges to avoid hard cutouts.

Usage:
    python chroma_key.py input.png -o output.png [--color FF00FF] [--tolerance 120]
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def chroma_key(
    input_path: str,
    output_path: str,
    key_color: tuple[int, int, int] = (255, 0, 255),
    tolerance: int = 120,
) -> None:
    img = Image.open(input_path).convert("RGBA")
    data = np.array(img, dtype=np.float32)

    key = np.array(key_color, dtype=np.float32)
    rgb = data[:, :, :3]
    dist = np.sqrt(np.sum((rgb - key) ** 2, axis=2))

    # Smooth transition: fully transparent inside inner, fully opaque outside outer
    inner = tolerance * 0.6
    outer = float(tolerance)
    alpha = np.clip((dist - inner) / (outer - inner) * 255, 0, 255).astype(np.uint8)
    data[:, :, 3] = alpha

    result = Image.fromarray(data.astype(np.uint8))
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    result.save(output_path)

    transparent_pct = np.sum(alpha == 0) / alpha.size * 100
    print(f"Saved: {output_path} ({transparent_pct:.1f}% transparent)", file=sys.stderr)


def parse_hex_color(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def main() -> None:
    parser = argparse.ArgumentParser(description="Chroma key background removal")
    parser.add_argument("input", help="Input PNG path")
    parser.add_argument("-o", "--output", required=True, help="Output PNG path")
    parser.add_argument(
        "--color", default="FF00FF",
        help="Key color hex (default: FF00FF magenta)",
    )
    parser.add_argument(
        "--tolerance", type=int, default=120,
        help="Color distance tolerance (default: 120)",
    )
    args = parser.parse_args()
    chroma_key(args.input, args.output, parse_hex_color(args.color), args.tolerance)


if __name__ == "__main__":
    main()
