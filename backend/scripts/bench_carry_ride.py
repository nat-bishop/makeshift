#!/usr/bin/env python3
"""Carry/ride sprite combination experiment via FLUX img2img.

Tests generating "character carrying object" and "character riding object" sprites
using two reference images (character + object). Generalized to any character,
not just the player — supports monster-rides-monster in the future.

Usage:
    cd backend && uv run python scripts/bench_carry_ride.py

Output:
    experiments/carry_ride/index.html
"""

from __future__ import annotations

import asyncio
import base64
import io
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx
from PIL import Image

# ── Configuration ──

STYLE = "mixed media collage style paper cutout, side view, flat lighting, clean edges"
SUFFIX = "single centered scene, contrasting solid background color, no text"

FLUX_URL = "http://127.0.0.1:5100"
FLUX_MODEL = "black-forest-labs/FLUX.2-klein-4B"
OUT_DIR = Path("experiments/carry_ride")
STEPS = 4

# Pre-flip objects so they face the same direction as the character.
# "h" = horizontal flip, "v" = vertical flip, "hv" = both.
OBJECT_FLIPS: dict[str, str] = {
    "sword": "hv",
    "horse": "h",
}

# Player sprite sheet — extract first idle frame
PLAYER_SHEET = Path(__file__).resolve().parent.parent.parent / "godot/assets/sprites/player/player_sheet.png"

# Characters to test (name, visual_description)
# Player is extracted from sprite sheet. Others are generated.
CHARACTERS: list[tuple[str, str]] = [
    ("explorer", "small boy with checkered hat, white shirt, brown vest, green shorts and boots"),
]

# Objects to test carrying — includes multiple weapons to test duplication
CARRY_OBJECTS: list[tuple[str, str]] = [
    ("sword", "steel longsword with leather-wrapped hilt and gleaming blade"),
    ("axe", "double-headed battle axe with oak handle and iron blades"),
    ("staff", "tall wooden wizard staff with a glowing blue orb on top"),
    ("crystal", "translucent purple crystal with geometric facets and inner glow"),
    ("bomb", "round black bomb with a lit fuse and sparks"),
    ("torch", "wooden torch with bright orange flame burning at the top"),
    ("shield", "round wooden shield with iron rim and painted crest"),
    ("potion", "small glass bottle filled with bubbling green liquid"),
]

# Objects to test riding
RIDE_OBJECTS: list[tuple[str, str]] = [
    ("horse", "brown horse with flowing mane and leather saddle"),
    ("dragon", "small green dragon with leathery wings and a spiky tail"),
    ("turtle", "giant brown turtle with a mossy green shell"),
    ("wolf", "large grey wolf with thick fur and yellow eyes"),
    ("beetle", "giant iridescent beetle with shiny green carapace"),
]

# ── Prompt strategies ──
# {char_name}, {char_desc}, {obj_name}, {obj_desc} available

# Round 3: baseline wins for everything except swords which duplicate.
# Test whether the duplication is caused by the object description being too
# visually specific (FLUX renders the text description AND the reference image).
# Keep baseline format, test with more objects including multiple weapons.

# "static" prompts are templates. "llm" is generated per-pair at runtime.
# No static prompts this round — only LLM, testing reference image formats
CARRY_PROMPTS_STATIC: list[tuple[str, str]] = []
RIDE_PROMPTS_STATIC: list[tuple[str, str]] = []

# Reference image variants to test
REF_VARIANTS: list[tuple[str, str]] = [
    ("512-transparent", "512x512 RGBA transparent (current)"),
    ("256-transparent", "256x256 RGBA transparent"),
    ("512-white-bg", "512x512 on solid white background"),
    ("256-white-bg", "256x256 on solid white background"),
]

# LLM instruction for generating carry/ride prompts (v3 pattern from combination experiments)
CARRY_LLM_INSTRUCTION = (
    "You write visual descriptions for a sprite image generator. "
    "A character is carrying an object. You receive descriptions of both. "
    "Write a visual description of the character holding/carrying the object "
    "as a single scene. Reference specific visual details from both descriptions. "
    "Under 25 words. Output ONLY the visual description."
)

RIDE_LLM_INSTRUCTION = (
    "You write visual descriptions for a sprite image generator. "
    "A character is riding a mount. You receive descriptions of both. "
    "Write a visual description of the character sitting on/riding the mount "
    "as a single scene. Reference specific visual details from both descriptions. "
    "Under 25 words. Output ONLY the visual description."
)


@dataclass
class SpriteEntry:
    name: str
    path: Path
    raw_path: Path | None = None
    order: str = ""
    prompt_label: str = ""
    prompt_used: str = ""
    input_image_paths: list[Path] = field(default_factory=list)
    elapsed: float = 0.0
    interaction_type: str = ""  # "carry" or "ride"


# ── Helpers ──


def extract_player_frame(sheet_path: Path) -> bytes:
    """Extract the first idle frame from the player sprite sheet."""
    sheet = Image.open(sheet_path).convert("RGBA")
    # Sheet is 5 columns x 5 rows based on the image. First frame is top-left.
    frame_w = sheet.width // 5
    frame_h = sheet.height // 5
    frame = sheet.crop((0, 0, frame_w, frame_h))
    # Resize to 512x512 with transparency
    canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    # Scale frame to fit, maintaining aspect ratio
    scale = min(460 / frame_w, 460 / frame_h)
    new_w = max(1, round(frame_w * scale))
    new_h = max(1, round(frame_h * scale))
    frame = frame.resize((new_w, new_h), Image.Resampling.LANCZOS)
    paste_x = (512 - new_w) // 2
    paste_y = (512 - new_h) // 2
    canvas.paste(frame, (paste_x, paste_y), frame)
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


def make_ref_variant(png_bytes: bytes, variant: str) -> bytes:
    """Create a reference image variant from a processed sprite."""
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")

    if "256" in variant:
        img = img.resize((256, 256), Image.Resampling.LANCZOS)

    if "white-bg" in variant:
        size = img.size
        bg = Image.new("RGBA", size, (255, 255, 255, 255))
        bg.paste(img, (0, 0), img)
        img = bg

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def flip_sprite(png_bytes: bytes, mode: str) -> bytes:
    """Flip a sprite. mode: 'h' = horizontal, 'v' = vertical, 'hv' = both."""
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    if "h" in mode:
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if "v" in mode:
        img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def generate_sprite(name: str, visual: str) -> tuple[bytes, bytes]:
    """Generate via text-to-image pipeline. Returns (processed, raw)."""
    from app.images.local_image import generate_image
    from app.images.pipeline import (
        TEXTURE_RESOLUTION,
        _crop_and_fit,
        remove_bg,
    )
    from app.prompts.image import build_text_to_image_prompt

    prompt = build_text_to_image_prompt(name, visual)
    raw_bytes = await generate_image(prompt)
    output_bytes = await remove_bg(raw_bytes)
    output_img = Image.open(io.BytesIO(output_bytes)).convert("RGBA")
    output_img = _crop_and_fit(output_img, TEXTURE_RESOLUTION)
    buf = io.BytesIO()
    output_img.save(buf, format="PNG")
    return buf.getvalue(), raw_bytes


async def process_sprite(raw_bytes: bytes) -> bytes:
    from app.images.pipeline import TEXTURE_RESOLUTION, _crop_and_fit, remove_bg

    output_bytes = await remove_bg(raw_bytes)
    output_img = Image.open(io.BytesIO(output_bytes)).convert("RGBA")
    output_img = _crop_and_fit(output_img, TEXTURE_RESOLUTION)
    buf = io.BytesIO()
    output_img.save(buf, format="PNG")
    return buf.getvalue()


async def flux_edits(prompt: str, images: list[tuple[str, bytes]]) -> bytes:
    files = [("image", (fname, data, "image/png")) for fname, data in images]
    async with httpx.AsyncClient(base_url=FLUX_URL, timeout=120) as client:
        resp = await client.post(
            "/v1/images/edits",
            files=files,
            data={
                "prompt": prompt,
                "model": FLUX_MODEL,
                "n": "1",
                "size": "512x512",
                "response_format": "b64_json",
                "num_inference_steps": str(STEPS),
            },
        )
        resp.raise_for_status()
        return base64.b64decode(resp.json()["data"][0]["b64_json"])


# ── Dashboard ──


def img_to_data_uri(path: Path) -> str:
    return f"data:image/png;base64,{base64.b64encode(path.read_bytes()).decode()}"


def generate_dashboard(
    base_entries: list[SpriteEntry],
    combo_entries: list[SpriteEntry],
) -> Path:
    # Base sprites
    base_html = '<h2>Base Sprites</h2><div class="base-row">'
    for e in base_entries:
        uri = img_to_data_uri(e.path)
        label_class = "char-label" if e.interaction_type == "character" else "obj-label"
        base_html += f"""
        <div class="base-card">
            <img src="{uri}" />
            <div class="label {label_class}">{e.name}</div>
        </div>"""
    base_html += "</div>"

    # Group combos by character+object+type
    groups: dict[str, list[SpriteEntry]] = {}
    for e in combo_entries:
        groups.setdefault(e.name, []).append(e)

    combos_html = ""
    current_type = ""
    for group_name, entries in groups.items():
        itype = entries[0].interaction_type
        if itype != current_type:
            current_type = itype
            combos_html += f'<h2 class="type-header">{itype.upper()}</h2>'
        combos_html += f'<h3>{group_name}</h3>'
        for e in entries:
            output_uri = img_to_data_uri(e.path)
            raw_uri = img_to_data_uri(e.raw_path) if e.raw_path and e.raw_path.exists() else ""

            input_imgs_html = ""
            for i, inp_path in enumerate(e.input_image_paths):
                if inp_path.exists():
                    inp_uri = img_to_data_uri(inp_path)
                    input_imgs_html += f"""
                    <div class="input-wrap">
                        <img class="input-img" src="{inp_uri}" />
                        <span class="pos-label">img{i + 1}</span>
                    </div>"""

            prompt_escaped = (
                e.prompt_used.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            )
            raw_html = ""
            if raw_uri:
                raw_html = f'<img class="output-raw" src="{raw_uri}" title="Raw" />'

            combos_html += f"""
            <div class="combo-row">
                <div class="combo-meta">
                    <span class="order-label">{e.order}</span>
                    <span class="prompt-label">{e.prompt_label}</span>
                </div>
                <div class="combo-inputs">{input_imgs_html}</div>
                <div class="combo-prompt"><div class="prompt-text">{prompt_escaped}</div></div>
                <div class="combo-arrow">&#x2192;</div>
                <div class="combo-outputs">
                    <img class="output-img" src="{output_uri}" />
                    {raw_html}
                </div>
            </div>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>FLUX img2img: Carry/Ride Test</title>
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: system-ui, -apple-system, sans-serif; background: #111; color: #ddd;
       padding: 2rem; max-width: 1800px; margin: 0 auto; }}
h1 {{ color: #fff; margin-bottom: 0.25rem; }}
h1 + p {{ color: #888; margin-top: 0; font-size: 0.85rem; line-height: 1.6; }}
h2 {{ color: #ccc; border-bottom: 1px solid #333; padding-bottom: 0.4rem; margin-top: 2.5rem; }}
h3 {{ color: #aab; margin-top: 1.5rem; margin-bottom: 0.5rem; }}
.type-header {{ color: #e8a848; font-size: 1.3rem; }}

.base-row {{ display: flex; flex-wrap: wrap; gap: 1rem; }}
.base-card {{ text-align: center; }}
.base-card img {{ width: 110px; height: 110px; border-radius: 6px; background: #0a0a1a; }}
.base-card .label {{ font-weight: bold; font-size: 0.8rem; margin-top: 0.25rem; }}
.char-label {{ color: #48e88a; }}
.obj-label {{ color: #e8e8ff; }}

.combo-row {{
    display: flex; align-items: center; gap: 0.75rem;
    background: #1a1a2e; border-radius: 8px; padding: 0.5rem 0.75rem;
    margin-bottom: 0.35rem;
}}
.combo-meta {{ flex: 0 0 120px; display: flex; flex-direction: column; gap: 0.15rem; }}
.order-label {{
    font-size: 0.7rem; font-weight: 700; color: #e8a848;
    background: #2a1f0e; padding: 2px 6px; border-radius: 4px; text-align: center;
}}
.prompt-label {{ font-size: 0.75rem; color: #7ea8d4; text-align: center; font-weight: 600; }}
.combo-inputs {{ flex: 0 0 auto; display: flex; gap: 0.25rem; }}
.input-wrap {{ position: relative; }}
.input-img {{ width: 80px; height: 80px; border-radius: 4px; background: #0a0a1a; border: 1px solid #333; }}
.pos-label {{
    position: absolute; bottom: 1px; left: 1px; font-size: 0.55rem; color: #aaa;
    background: rgba(0,0,0,0.85); padding: 1px 3px; border-radius: 2px;
}}
.combo-prompt {{ flex: 1 1 auto; min-width: 150px; }}
.prompt-text {{
    font-size: 0.65rem; color: #888; line-height: 1.3;
    background: #0f0f23; border-radius: 5px; padding: 0.35rem 0.5rem;
    font-family: 'Cascadia Code', 'Fira Code', monospace;
    word-break: break-word; max-height: 70px; overflow-y: auto;
}}
.combo-arrow {{ flex: 0 0 auto; font-size: 1.2rem; color: #555; }}
.combo-outputs {{ flex: 0 0 auto; display: flex; gap: 0.35rem; align-items: center; }}
.output-img {{
    width: 120px; height: 120px; border-radius: 6px; background: #0a0a1a;
    border: 2px solid #2a2a4e;
}}
.output-raw {{
    width: 50px; height: 50px; border-radius: 4px; background: #fff;
    border: 1px solid #333; opacity: 0.5; cursor: pointer; transition: all 0.15s;
}}
.output-raw:hover {{ width: 120px; height: 120px; opacity: 1; }}
</style>
</head><body>
<h1>FLUX img2img: Carry/Ride Sprite Test</h1>
<p>Testing "character carrying object" and "character riding mount" sprites
using two reference images. Both image orderings tested (char→obj vs obj→char).
4 prompt variants per combination. Generalized to any character, not just player.</p>
{base_html}
{combos_html}
</body></html>"""

    out_path = OUT_DIR / "index.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path


# ── Main ──


async def main() -> None:
    from app.logging_setup import setup_logging

    setup_logging()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base_entries: list[SpriteEntry] = []
    combo_entries: list[SpriteEntry] = []
    sprite_data: dict[str, bytes] = {}
    descs: dict[str, str] = {}

    # ── Generate character sprites ──
    print("=== Characters ===")
    # Explorer: extract from player sprite sheet
    print(f"  explorer (from sprite sheet)...", end=" ", flush=True)
    player_bytes = extract_player_frame(PLAYER_SHEET)
    path = OUT_DIR / "char_explorer.png"
    path.write_bytes(player_bytes)
    sprite_data["explorer"] = player_bytes
    descs["explorer"] = CHARACTERS[0][1]
    base_entries.append(SpriteEntry(
        name="explorer", path=path, interaction_type="character",
    ))
    print("done")

    # Other characters: generate
    for name, visual in CHARACTERS[1:]:
        t0 = time.monotonic()
        print(f"  {name}...", end=" ", flush=True)
        processed, raw = await generate_sprite(name, visual)
        elapsed = time.monotonic() - t0
        path = OUT_DIR / f"char_{name}.png"
        raw_path = OUT_DIR / f"char_{name}_raw.png"
        path.write_bytes(processed)
        raw_path.write_bytes(raw)
        sprite_data[name] = processed
        descs[name] = visual
        base_entries.append(SpriteEntry(
            name=name, path=path, raw_path=raw_path,
            elapsed=elapsed, interaction_type="character",
        ))
        print(f"{elapsed:.1f}s")

    # ── Generate carry objects ──
    print("\n=== Carry Objects ===")
    for name, visual in CARRY_OBJECTS:
        t0 = time.monotonic()
        flip = OBJECT_FLIPS.get(name)
        flip_label = f" (flip {flip})" if flip else ""
        print(f"  {name}{flip_label}...", end=" ", flush=True)
        processed, raw = await generate_sprite(name, visual)
        if flip:
            processed = flip_sprite(processed, flip)
        elapsed = time.monotonic() - t0
        path = OUT_DIR / f"obj_{name}.png"
        raw_path = OUT_DIR / f"obj_{name}_raw.png"
        path.write_bytes(processed)
        raw_path.write_bytes(raw)
        sprite_data[name] = processed
        descs[name] = visual
        base_entries.append(SpriteEntry(
            name=f"{name}{flip_label}", path=path, raw_path=raw_path,
            elapsed=elapsed, interaction_type="object",
        ))
        print(f"{elapsed:.1f}s")

    # ── Generate ride objects ──
    print("\n=== Ride Objects ===")
    for name, visual in RIDE_OBJECTS:
        t0 = time.monotonic()
        flip = OBJECT_FLIPS.get(name)
        flip_label = f" (flip {flip})" if flip else ""
        print(f"  {name}{flip_label}...", end=" ", flush=True)
        processed, raw = await generate_sprite(name, visual)
        if flip:
            processed = flip_sprite(processed, flip)
        elapsed = time.monotonic() - t0
        path = OUT_DIR / f"obj_{name}.png"
        raw_path = OUT_DIR / f"obj_{name}_raw.png"
        path.write_bytes(processed)
        raw_path.write_bytes(raw)
        sprite_data[name] = processed
        descs[name] = visual
        base_entries.append(SpriteEntry(
            name=f"{name}{flip_label}", path=path, raw_path=raw_path,
            elapsed=elapsed, interaction_type="object",
        ))
        print(f"{elapsed:.1f}s")

    # ── Helper to run one combo ──
    from app.creator.llm import ask_text

    char_names = [name for name, _ in CHARACTERS]

    async def run_combo(
        char_name: str, obj_name: str, prompt_label: str, prompt: str,
        interaction_type: str,
        char_ref: bytes, obj_ref: bytes,
        char_ref_path: Path, obj_ref_path: Path,
    ) -> SpriteEntry:
        t0 = time.monotonic()
        raw = await flux_edits(
            prompt,
            [(f"{char_name}.png", char_ref),
             (f"{obj_name}.png", obj_ref)],
        )
        processed = await process_sprite(raw)
        elapsed = time.monotonic() - t0

        safe = f"{interaction_type}_{char_name}+{obj_name}_{prompt_label}"
        path = OUT_DIR / f"{safe}.png"
        raw_path = OUT_DIR / f"{safe}_raw.png"
        path.write_bytes(processed)
        raw_path.write_bytes(raw)

        action = "carries" if interaction_type == "carry" else "rides"
        return SpriteEntry(
            name=f"{char_name} {action} {obj_name}",
            path=path, raw_path=raw_path,
            order=f"{char_name} \u2192 {obj_name}",
            prompt_label=prompt_label, prompt_used=prompt,
            input_image_paths=[char_ref_path, obj_ref_path],
            elapsed=elapsed, interaction_type=interaction_type,
        )

    # ── Test each ref variant with LLM prompt ──
    # Only test sword (carry problem case) and horse (ride problem case) + one good case each
    test_carry = [o for o in CARRY_OBJECTS if o[0] in ("sword", "crystal", "bomb", "axe")]
    test_ride = [o for o in RIDE_OBJECTS if o[0] in ("horse", "dragon", "wolf")]

    n_variants = len(REF_VARIANTS)
    carry_total = len(CHARACTERS) * len(test_carry) * n_variants
    ride_total = len(CHARACTERS) * len(test_ride) * n_variants
    total = carry_total + ride_total
    done = 0

    print(f"\n=== CARRY: {len(test_carry)} objects x {n_variants} ref variants = {carry_total} ===")

    for char_name, char_desc in CHARACTERS:
        for obj_name, obj_desc in test_carry:
            # Generate LLM prompt once per pair
            llm_user = (
                f"Character: {char_name} — {char_desc}\n"
                f"Object: {obj_name} — {obj_desc}\n"
                f"Describe the character carrying the object:"
            )
            llm_desc = await ask_text(llm_user, max_tokens=50, instructions=CARRY_LLM_INSTRUCTION)
            prompt = f"{STYLE}, {llm_desc}, {SUFFIX}"
            print(f"\n  {char_name} carries {obj_name}: {llm_desc}")

            for var_key, var_desc in REF_VARIANTS:
                done += 1
                print(f"    [{done}/{total}] {var_key}...", end=" ", flush=True)

                char_ref = make_ref_variant(sprite_data[char_name], var_key)
                obj_ref = make_ref_variant(sprite_data[obj_name], var_key)

                # Save ref variants for dashboard
                char_ref_path = OUT_DIR / f"ref_{char_name}_{var_key}.png"
                obj_ref_path = OUT_DIR / f"ref_{obj_name}_{var_key}.png"
                char_ref_path.write_bytes(char_ref)
                obj_ref_path.write_bytes(obj_ref)

                entry = await run_combo(
                    char_name, obj_name, var_key, prompt, "carry",
                    char_ref, obj_ref, char_ref_path, obj_ref_path,
                )
                combo_entries.append(entry)
                print(f"{entry.elapsed:.1f}s")

    # ── Ride tests ──
    print(f"\n=== RIDE: {len(test_ride)} objects x {n_variants} ref variants = {ride_total} ===")

    for char_name, char_desc in CHARACTERS:
        for obj_name, obj_desc in test_ride:
            llm_user = (
                f"Character: {char_name} — {char_desc}\n"
                f"Mount: {obj_name} — {obj_desc}\n"
                f"Describe the character riding the mount:"
            )
            llm_desc = await ask_text(llm_user, max_tokens=50, instructions=RIDE_LLM_INSTRUCTION)
            prompt = f"{STYLE}, {llm_desc}, {SUFFIX}"
            print(f"\n  {char_name} rides {obj_name}: {llm_desc}")

            for var_key, var_desc in REF_VARIANTS:
                done += 1
                print(f"    [{done}/{total}] {var_key}...", end=" ", flush=True)

                char_ref = make_ref_variant(sprite_data[char_name], var_key)
                obj_ref = make_ref_variant(sprite_data[obj_name], var_key)

                char_ref_path = OUT_DIR / f"ref_{char_name}_{var_key}.png"
                obj_ref_path = OUT_DIR / f"ref_{obj_name}_{var_key}.png"
                char_ref_path.write_bytes(char_ref)
                obj_ref_path.write_bytes(obj_ref)

                entry = await run_combo(
                    char_name, obj_name, var_key, prompt, "ride",
                    char_ref, obj_ref, char_ref_path, obj_ref_path,
                )
                combo_entries.append(entry)
                print(f"{entry.elapsed:.1f}s")

    # ── Dashboard ──
    dash_path = generate_dashboard(base_entries, combo_entries)
    total_time = sum(e.elapsed for e in combo_entries)
    print(f"\n{'=' * 50}")
    print(f"Total images: {len(base_entries) + len(combo_entries)} ({total_time:.0f}s cumulative)")
    print(f"Dashboard:    {dash_path.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
