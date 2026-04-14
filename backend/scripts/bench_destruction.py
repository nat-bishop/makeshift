#!/usr/bin/env python3
"""Destruction sprite experiment via FLUX img2img.

Tests generating "destroyed version" sprites from a single reference image.
E.g., a sword sprite → "splinters", a glass bottle → "glass shards".

Uses /v1/images/edits with ONE reference image and a destruction prompt.

Usage:
    cd backend && uv run python scripts/bench_destruction.py

Output:
    experiments/destruction/index.html
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
SUFFIX = "single centered object, contrasting solid background color, no text"

FLUX_URL = "http://127.0.0.1:5100"
FLUX_MODEL = "black-forest-labs/FLUX.2-klein-4B"
OUT_DIR = Path("experiments/destruction")
STEPS = 4

# Objects to test destruction on: (name, visual_description, destruction_result_name)
TEST_OBJECTS: list[tuple[str, str, str]] = [
    ("wooden sword", "crude wooden practice sword with rough grain and chipped edges", "splinters"),
    ("glass bottle", "clear glass bottle with a cork stopper and bubbling green liquid", "glass shards"),
    ("clay pot", "round terracotta clay pot with painted geometric patterns", "pottery fragments"),
    ("ice crystal", "translucent blue ice crystal with sharp frozen edges and frost", "puddle of water"),
    ("stone statue", "small grey stone statue of a warrior in armor", "rubble and dust"),
    ("lantern", "brass lantern with glass panels and a candle flame inside", "broken brass and glass"),
    ("wooden crate", "rough wooden shipping crate with iron nails and rope handles", "pile of planks"),
    ("egg", "large speckled egg with a cracked shell and warm glow from within", "eggshell fragments"),
]

# Prompt strategies for destruction
# {obj_name}, {obj_desc}, {debris_name} available

DESTRUCTION_PROMPTS_STATIC: list[tuple[str, str]] = [
    # Tell FLUX the reference is the intact version, output should be destroyed
    (
        "edit-destroy",
        "The reference image shows the intact object. Generate a destroyed version of it. "
        f"{STYLE}, "
        "destroyed {obj_desc}, smashed and broken into {debris_name}, "
        f"{SUFFIX}",
    ),
    # Same but without debris name — just "destroy the reference"
    (
        "edit-no-debris",
        "The reference image shows the intact object. Generate a destroyed, broken version. "
        f"{STYLE}, "
        "destroyed {obj_desc}, smashed into pieces, "
        f"{SUFFIX}",
    ),
    # Purely reference-driven — no object description at all
    (
        "edit-ref-only",
        "The reference image shows an intact object. "
        "Generate a destroyed, shattered version of this exact object. "
        f"{STYLE}, "
        "broken remains and debris, "
        f"{SUFFIX}",
    ),
    # Previous best template for comparison
    (
        "desc-to-debris",
        f"{STYLE}, "
        "{debris_name}, the destroyed remains of {obj_desc}, "
        f"{SUFFIX}",
    ),
]

LLM_INSTRUCTIONS: list[tuple[str, str]] = [
    (
        "contrast-cutout",
        "You write visual descriptions for paper cutout style game sprites. "
        "An object has been destroyed. Describe the broken remains as a paper cutout sprite. "
        "It must look NOTHING like the original shape — only scattered debris on the ground. "
        "Think: what would be left after this object shattered? "
        "Same colors, completely different shape. Paper cutout art style. "
        "Under 15 words. Output ONLY the visual description.",
    ),
    (
        "contrast-style",
        "You write visual descriptions for a 2D paper craft game. "
        "An object has been destroyed. Describe the debris pile as a flat paper cutout. "
        "Must NOT resemble the intact object. Describe scattered pieces, shards, or rubble. "
        "Use the original's colors and materials. Flat, layered paper craft look. "
        "Under 15 words. Output ONLY the visual description.",
    ),
    (
        "contrast-short",
        "You describe destroyed game objects for a paper cutout sprite generator. "
        "Describe ONLY the debris — a pile of broken pieces on the ground. "
        "NOT the intact object. Same colors, shattered form. "
        "Under 10 words. Output ONLY the description.",
    ),
    (
        "contrast-explicit",
        "You write visual descriptions for a mixed media collage paper cutout game. "
        "An object was smashed. Describe the debris as a single paper cutout sprite. "
        "The debris must look completely different from the original object's silhouette. "
        "It should be a low, flat pile or scatter of broken fragments. "
        "Reference the original's specific colors and material textures. "
        "Under 20 words. Output ONLY the visual description.",
    ),
]


@dataclass
class SpriteEntry:
    name: str
    path: Path
    raw_path: Path | None = None
    prompt_label: str = ""
    prompt_used: str = ""
    input_image_paths: list[Path] = field(default_factory=list)
    elapsed: float = 0.0
    llm_output: str = ""
    group: str = ""


# ── Helpers ──


def prepare_reference(sprite_bytes: bytes) -> bytes:
    """Convert sprite to 256x256 white-bg reference."""
    img = Image.open(io.BytesIO(sprite_bytes)).convert("RGBA")
    img = img.resize((256, 256), Image.Resampling.LANCZOS)
    bg = Image.new("RGBA", (256, 256), (255, 255, 255, 255))
    bg.paste(img, (0, 0), img)
    buf = io.BytesIO()
    bg.save(buf, format="PNG")
    return buf.getvalue()


async def generate_sprite(name: str, visual: str) -> tuple[bytes, bytes]:
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
    base_html = '<h2>Source Objects</h2><div class="base-row">'
    for e in base_entries:
        uri = img_to_data_uri(e.path)
        base_html += f"""
        <div class="base-card">
            <img src="{uri}" />
            <div class="label">{e.name}</div>
        </div>"""
    base_html += "</div>"

    groups: dict[str, list[SpriteEntry]] = {}
    for e in combo_entries:
        groups.setdefault(e.group, []).append(e)

    combos_html = ""
    for group_name, entries in groups.items():
        combos_html += f'<h3>{group_name}</h3>'
        for e in entries:
            output_uri = img_to_data_uri(e.path)
            raw_uri = img_to_data_uri(e.raw_path) if e.raw_path and e.raw_path.exists() else ""

            input_imgs_html = ""
            for inp_path in e.input_image_paths:
                if inp_path.exists():
                    inp_uri = img_to_data_uri(inp_path)
                    input_imgs_html += f'<img class="input-img" src="{inp_uri}" />'

            prompt_escaped = (
                e.prompt_used.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            )
            llm_html = ""
            if e.llm_output:
                llm_escaped = e.llm_output.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                llm_html = f'<div class="llm-output">{llm_escaped}</div>'

            raw_html = ""
            if raw_uri:
                raw_html = f'<img class="output-raw" src="{raw_uri}" title="Raw" />'

            combos_html += f"""
            <div class="combo-row">
                <div class="combo-meta">
                    <span class="prompt-label">{e.prompt_label}</span>
                </div>
                <div class="combo-inputs">{input_imgs_html}</div>
                <div class="combo-prompt">
                    {llm_html}
                    <div class="prompt-text">{prompt_escaped}</div>
                </div>
                <div class="combo-arrow">&#x2192;</div>
                <div class="combo-outputs">
                    <img class="output-img" src="{output_uri}" />
                    {raw_html}
                </div>
            </div>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>FLUX img2img: Destruction Test</title>
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: system-ui, -apple-system, sans-serif; background: #111; color: #ddd;
       padding: 2rem; max-width: 1800px; margin: 0 auto; }}
h1 {{ color: #fff; margin-bottom: 0.25rem; }}
h1 + p {{ color: #888; margin-top: 0; font-size: 0.85rem; line-height: 1.6; }}
h3 {{ color: #ccc; border-bottom: 1px solid #333; padding-bottom: 0.4rem; margin-top: 2rem; }}

.base-row {{ display: flex; flex-wrap: wrap; gap: 1rem; }}
.base-card {{ text-align: center; }}
.base-card img {{ width: 110px; height: 110px; border-radius: 6px; background: #0a0a1a; }}
.base-card .label {{ font-weight: bold; font-size: 0.75rem; margin-top: 0.25rem; color: #e8e8ff; }}

.combo-row {{
    display: flex; align-items: center; gap: 0.75rem;
    background: #1a1a2e; border-radius: 8px; padding: 0.5rem 0.75rem;
    margin-bottom: 0.35rem;
}}
.combo-meta {{ flex: 0 0 110px; }}
.prompt-label {{ font-size: 0.75rem; color: #7ea8d4; font-weight: 600; }}
.combo-inputs {{ flex: 0 0 auto; }}
.input-img {{ width: 80px; height: 80px; border-radius: 4px; background: #0a0a1a; border: 1px solid #333; }}
.combo-prompt {{ flex: 1 1 auto; min-width: 150px; }}
.llm-output {{
    font-size: 0.78rem; color: #d4be7e; line-height: 1.3;
    background: #1f1a0f; border-radius: 5px 5px 0 0; padding: 0.3rem 0.5rem;
    font-style: italic; border-bottom: 1px solid #2a2a2a;
}}
.prompt-text {{
    font-size: 0.62rem; color: #666; line-height: 1.25;
    background: #0f0f23; border-radius: 0 0 5px 5px; padding: 0.25rem 0.5rem;
    font-family: 'Cascadia Code', 'Fira Code', monospace;
    word-break: break-word; max-height: 55px; overflow-y: auto;
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
<h1>FLUX img2img: Destruction Sprite Test</h1>
<p>Single reference image (the intact object) → destroyed remains.
3 template prompts + 1 LLM-generated. Reference images are 256x256 on white background.</p>
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
    from app.creator.llm import ask_text

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base_entries: list[SpriteEntry] = []
    combo_entries: list[SpriteEntry] = []
    sprite_data: dict[str, bytes] = {}
    descriptions: dict[str, str] = {}

    # ── Generate source objects ──
    print("=== Source Objects ===")
    for name, visual, _ in TEST_OBJECTS:
        t0 = time.monotonic()
        print(f"  {name}...", end=" ", flush=True)
        processed, raw = await generate_sprite(name, visual)
        elapsed = time.monotonic() - t0
        safe = name.replace(" ", "_")
        path = OUT_DIR / f"obj_{safe}.png"
        raw_path = OUT_DIR / f"obj_{safe}_raw.png"
        path.write_bytes(processed)
        raw_path.write_bytes(raw)
        sprite_data[name] = processed
        descriptions[name] = visual
        base_entries.append(SpriteEntry(name=name, path=path, raw_path=raw_path, elapsed=elapsed))
        print(f"{elapsed:.1f}s")

    # ── Destruction tests ──
    n_prompts = len(LLM_INSTRUCTIONS)
    total = len(TEST_OBJECTS) * n_prompts
    done = 0
    print(f"\n=== {len(TEST_OBJECTS)} objects x {n_prompts} LLM variants = {total} destructions ===")

    for obj_name, obj_desc, debris_name in TEST_OBJECTS:
        group = f"{obj_name} → {debris_name}"
        safe_obj = obj_name.replace(" ", "_")
        print(f"\n  {group}:")

        # Prepare 256x256 white-bg reference
        ref = prepare_reference(sprite_data[obj_name])
        ref_path = OUT_DIR / f"ref_{safe_obj}.png"
        ref_path.write_bytes(ref)

        llm_user = (
            f"Object: {obj_name} — {obj_desc}\n"
            f"Debris name: {debris_name}\n"
            f"Describe the destroyed remains:"
        )

        for prompt_label, instruction in LLM_INSTRUCTIONS:
            llm_desc = await ask_text(llm_user, max_tokens=40, instructions=instruction)
            prompt = f"{STYLE}, {llm_desc}, {SUFFIX}"
            done += 1
            print(f"    [{done}/{total}] {prompt_label} ({llm_desc})...", end=" ", flush=True)
            t0 = time.monotonic()

            raw = await flux_edits(prompt, [(f"{safe_obj}.png", ref)])
            processed = await process_sprite(raw)
            elapsed = time.monotonic() - t0

            path = OUT_DIR / f"dest_{safe_obj}_{prompt_label}.png"
            raw_path = OUT_DIR / f"dest_{safe_obj}_{prompt_label}_raw.png"
            path.write_bytes(processed)
            raw_path.write_bytes(raw)

            combo_entries.append(SpriteEntry(
                name=obj_name, path=path, raw_path=raw_path,
                prompt_label=prompt_label, prompt_used=prompt,
                input_image_paths=[ref_path], elapsed=elapsed,
                llm_output=llm_desc, group=group,
            ))
            print(f"{elapsed:.1f}s")

    # ── Dashboard ──
    dash_path = generate_dashboard(base_entries, combo_entries)
    total_time = sum(e.elapsed for e in combo_entries)
    print(f"\n{'=' * 50}")
    print(f"Total images: {len(base_entries) + len(combo_entries)} ({total_time:.0f}s cumulative)")
    print(f"Dashboard:    {dash_path.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
