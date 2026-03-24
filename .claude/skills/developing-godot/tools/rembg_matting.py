"""Remove solid-color background using rembg (birefnet) + foreground color recovery.

Uses rembg's built-in alpha matting for the mask/alpha, then recovers true
foreground colors on semi-transparent edge pixels to prevent bg-colored halos.
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image
from rembg import remove, new_session


def sample_bg_color(img: np.ndarray, block: int = 2) -> np.ndarray:
    """Average color from 2x2 blocks at all 4 corners (16 pixels)."""
    corners = np.concatenate([
        img[:block, :block].reshape(-1, 3),
        img[:block, -block:].reshape(-1, 3),
        img[-block:, :block].reshape(-1, 3),
        img[-block:, -block:].reshape(-1, 3),
    ])
    return corners.mean(axis=0)


def recover_foreground(img: np.ndarray, alpha: np.ndarray,
                       bg_color: np.ndarray) -> np.ndarray:
    """Undo background compositing: fg = (pixel - (1-a)*bg) / a."""
    a = alpha[:, :, np.newaxis]
    bg = bg_color[np.newaxis, np.newaxis, :]
    safe_a = np.where(a > 0.02, a, 1.0)
    fg = np.clip((img - (1.0 - a) * bg) / safe_a, 0.0, 1.0)
    fg[alpha < 0.02] = 0.0
    return fg


def main():
    parser = argparse.ArgumentParser(
        description="Remove solid-color background using rembg + fg recovery")
    parser.add_argument("input", help="Input image path")
    parser.add_argument("-o", "--output", help="Output PNG path (default: <input>_nobg.png)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_stem(input_path.stem + "_nobg")

    # Load
    img_pil = Image.open(input_path).convert("RGBA")
    img = np.array(img_pil.convert("RGB"), dtype=np.float64) / 255.0
    h, w = img.shape[:2]
    print(f"Image: {w}x{h} ({input_path})")

    # Remove background with built-in alpha matting
    session = new_session("birefnet-general")
    result = remove(img_pil, session=session, alpha_matting=True, post_process_mask=True)
    alpha = np.array(result)[:, :, 3].astype(np.float64) / 255.0

    # Recover true foreground colors on semi-transparent edges
    bg_color = sample_bg_color(img)
    print(f"BG color: RGB({bg_color[0]*255:.0f}, {bg_color[1]*255:.0f}, {bg_color[2]*255:.0f})")
    fg = recover_foreground(img, alpha, bg_color)

    # Output
    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[:, :, :3] = (fg * 255).clip(0, 255).astype(np.uint8)
    out[:, :, 3] = (alpha * 255).clip(0, 255).astype(np.uint8)

    Image.fromarray(out).save(output_path)
    print(f"\nSaved: {output_path}")
    print(f"  Opaque: {(out[:,:,3] == 255).sum()}")
    print(f"  Transparent: {(out[:,:,3] == 0).sum()}")
    print(f"  Semi-transparent: {((out[:,:,3] > 0) & (out[:,:,3] < 255)).sum()}")


if __name__ == "__main__":
    main()
