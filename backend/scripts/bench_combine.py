#!/usr/bin/env python3
"""Image combination experiment round 7: LLM writes the image prompt.

The material template works because it tells FLUX which visual properties to
take from each reference. But it's mechanical: always "silhouette of B
constructed from A". Can the LLM write a BETTER image prompt dynamically,
choosing the right framing per pair?

Input: object names + their existing visual_descriptions (from creation pipeline).
LLM output: the visual description part of the image prompt.
Template always wraps in art style.

Tests different instructions for the prompt-writing LLM call.

Usage:
    cd backend && uv run python scripts/bench_combine.py

Output:
    experiments/combine/index.html
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

BASE_OBJECTS: list[tuple[str, str]] = [
    ("flame", "bright orange fire with flickering tongues and ember particles"),
    ("crystal", "translucent purple crystal with geometric facets and inner glow"),
    ("mushroom", "red-capped forest mushroom with white spots and pale stem"),
    ("gear", "brass clockwork gear with intricate teeth and green patina"),
    ("sword", "steel longsword with leather-wrapped hilt and gleaming blade"),
    ("eye", "floating mystical eye with blue iris and wispy tendrils"),
    ("tree", "gnarled oak tree with twisted branches and thick roots"),
    ("skull", "weathered human skull with cracked bone and hollow eye sockets"),
]

TEST_PAIRS: list[tuple[str, str]] = [
    ("flame", "sword"),
    ("crystal", "skull"),
    ("mushroom", "eye"),
    ("gear", "tree"),
    ("flame", "crystal"),
    ("skull", "gear"),
    ("eye", "sword"),
    ("mushroom", "crystal"),
    ("flame", "tree"),
    ("sword", "skull"),
]

FLUX_URL = "http://127.0.0.1:5100"
FLUX_MODEL = "black-forest-labs/FLUX.2-klein-4B"
OUT_DIR = Path("experiments/combine")
STEPS = 4

# ── LLM instructions for generating the image prompt ──
# Each gets the same user prompt with {name_a}, {name_b}, {desc_a}, {desc_b}.
# The LLM should output JUST the visual description to slot into the template.

LLM_INSTRUCTIONS: list[tuple[str, str, str]] = [
    # (label, description, system_instruction)
    (
        "write-prompt",
        "LLM writes image prompt: told what works, given both visual descriptions",
        "You write visual descriptions for a sprite image generator. "
        "Two game objects are being combined. You will receive their names and visual descriptions. "
        "Write a visual description of the combined object for the image generator. "
        "IMPORTANT: Specify which visual properties come from which source object. "
        "For example: 'the shape/silhouette of X but the texture/color/material of Y' or "
        "'X with Y elements woven into its design'. "
        "Be specific about colors, shapes, and materials. Under 25 words. "
        "Output ONLY the visual description, nothing else.",
    ),
    (
        "write-prompt-v2",
        "LLM writes image prompt: emphasize referencing both source descriptions",
        "You write visual descriptions for a sprite image generator that uses two reference images. "
        "The generator works best when the prompt describes which visual qualities come from "
        "each source. You MUST reference specific visual details from BOTH source descriptions. "
        "Under 25 words. Output ONLY the visual description.",
    ),
    (
        "write-prompt-v3",
        "LLM writes image prompt: told about material/themed/semantic patterns",
        "You write visual descriptions for a sprite image generator. "
        "Two objects are being combined. Choose the best combination approach:\n"
        "- MATERIAL: 'the shape of B but made from/constructed of A' (when A is a material-like thing)\n"
        "- THEMED: 'B with A elements, accents, and motifs woven into its design' (when A is an aesthetic)\n"
        "- SEMANTIC: 'an A B, combining elements of both into one object' (when both contribute equally)\n"
        "Pick the approach that fits best. Reference specific visual details from both source descriptions. "
        "Under 25 words. Output ONLY the visual description.",
    ),
]

# The user prompt is the same for all instructions
USER_PROMPT_TEMPLATE = (
    "Object A: {name_a} — {desc_a}\n"
    "Object B: {name_b} — {desc_b}\n"
    "Write the visual description for combining A with B:"
)


@dataclass
class SpriteEntry:
    name: str
    path: Path
    raw_path: Path | None = None
    order: str = ""
    prompt_label: str = ""
    prompt_desc: str = ""
    prompt_used: str = ""
    input_image_paths: list[Path] = field(default_factory=list)
    elapsed: float = 0.0
    llm_output: str = ""
    order_source: str = ""


# ── Helpers ──


async def generate_base_sprite(name: str, visual: str) -> tuple[bytes, bytes]:
    from app.images.local_image import generate_image
    from app.images.pipeline import (
        TEXTURE_RESOLUTION,
        _crop_and_fit,
        build_prompt,
        remove_bg,
    )

    prompt = build_prompt(name, visual)
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


async def llm_pick_order(
    name_a: str, desc_a: str, name_b: str, desc_b: str
) -> int:
    from app.creator.llm import ask_choice

    result = await ask_choice(
        f"Two objects are being combined into one sprite image. "
        f"The first reference image has more influence on the overall shape and form.\n"
        f"1: {name_a} — {desc_a}\n"
        f"2: {name_b} — {desc_b}\n"
        f"Which should be the primary shape reference?",
        choices=("1", "2"),
        default="1",
    )
    return 0 if result == "1" else 1


async def llm_write_prompt(user_prompt: str, instruction: str) -> str:
    from app.creator.llm import ask_text

    return await ask_text(user_prompt, max_tokens=60, instructions=instruction)


# ── Dashboard ──


def img_to_data_uri(path: Path) -> str:
    return f"data:image/png;base64,{base64.b64encode(path.read_bytes()).decode()}"


def generate_dashboard(
    base_entries: list[SpriteEntry],
    combo_entries: list[SpriteEntry],
) -> Path:
    base_html = '<h2>Base Objects</h2><div class="base-row">'
    for e in base_entries:
        uri = img_to_data_uri(e.path)
        base_html += f"""
        <div class="base-card">
            <img src="{uri}" /><div class="label">{e.name}</div>
        </div>"""
    base_html += "</div>"

    pairs: dict[str, list[SpriteEntry]] = {}
    for e in combo_entries:
        pairs.setdefault(e.name, []).append(e)

    combos_html = ""
    for pair_name, entries in pairs.items():
        combos_html += f'<h2>{pair_name}</h2>'
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
            llm_escaped = (
                e.llm_output.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            )
            raw_html = ""
            if raw_uri:
                raw_html = f'<img class="output-raw" src="{raw_uri}" title="Raw" />'

            order_class = "order-llm" if e.order_source == "llm" else "order-fixed"

            combos_html += f"""
            <div class="combo-row">
                <div class="combo-meta">
                    <span class="order-label {order_class}">{e.order}</span>
                    <span class="prompt-label">{e.prompt_label}</span>
                    <span class="order-src">{e.order_source}</span>
                </div>
                <div class="combo-inputs">{input_imgs_html}</div>
                <div class="combo-prompt">
                    <div class="llm-output">{llm_escaped}</div>
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
<title>FLUX img2img Round 7: LLM Writes the Image Prompt</title>
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: system-ui, -apple-system, sans-serif; background: #111; color: #ddd;
       padding: 2rem; max-width: 1800px; margin: 0 auto; }}
h1 {{ color: #fff; margin-bottom: 0.25rem; }}
h1 + p {{ color: #888; margin-top: 0; font-size: 0.85rem; line-height: 1.6; }}
h2 {{ color: #ccc; border-bottom: 1px solid #333; padding-bottom: 0.4rem; margin-top: 2.5rem; }}

.base-row {{ display: flex; flex-wrap: wrap; gap: 1rem; }}
.base-card {{ text-align: center; }}
.base-card img {{ width: 110px; height: 110px; border-radius: 6px; background: #0a0a1a; }}
.base-card .label {{ font-weight: bold; font-size: 0.8rem; margin-top: 0.25rem; color: #e8e8ff; }}

.combo-row {{
    display: flex; align-items: center; gap: 0.75rem;
    background: #1a1a2e; border-radius: 8px; padding: 0.5rem 0.75rem;
    margin-bottom: 0.35rem;
}}
.combo-meta {{ flex: 0 0 110px; display: flex; flex-direction: column; gap: 0.15rem; }}
.order-label {{
    font-size: 0.7rem; font-weight: 700; padding: 2px 6px; border-radius: 4px; text-align: center;
}}
.order-fixed {{ color: #e8a848; background: #2a1f0e; }}
.order-llm {{ color: #48e88a; background: #0e2a1f; }}
.prompt-label {{ font-size: 0.75rem; color: #7ea8d4; text-align: center; font-weight: 600; }}
.order-src {{ font-size: 0.6rem; color: #555; text-align: center; }}
.combo-inputs {{ flex: 0 0 auto; display: flex; gap: 0.25rem; }}
.input-wrap {{ position: relative; }}
.input-img {{ width: 80px; height: 80px; border-radius: 4px; background: #0a0a1a; border: 1px solid #333; }}
.pos-label {{
    position: absolute; bottom: 1px; left: 1px; font-size: 0.55rem; color: #aaa;
    background: rgba(0,0,0,0.85); padding: 1px 3px; border-radius: 2px;
}}
.combo-prompt {{ flex: 1 1 auto; min-width: 150px; }}
.llm-output {{
    font-size: 0.78rem; color: #d4be7e; line-height: 1.3;
    background: #1f1a0f; border-radius: 5px 5px 0 0; padding: 0.35rem 0.5rem;
    font-style: italic; border-bottom: 1px solid #2a2a2a;
}}
.prompt-text {{
    font-size: 0.6rem; color: #555; line-height: 1.25;
    background: #0f0f23; border-radius: 0 0 5px 5px; padding: 0.25rem 0.5rem;
    font-family: 'Cascadia Code', 'Fira Code', monospace;
    word-break: break-word; max-height: 45px; overflow-y: auto;
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
<h1>FLUX img2img Round 7: LLM Writes the Image Prompt</h1>
<p>LLM receives both object names + visual descriptions (from creation pipeline) and writes
the image prompt. <span style="color:#d4be7e">Gold text</span> = what the LLM wrote.
Art style template wraps it. Compared against round 3 best templates.<br>
<b>write-prompt</b> = told what works (specify which properties from which source)<br>
<b>write-prompt-v2</b> = must reference specific details from BOTH descriptions<br>
<b>write-prompt-v3</b> = taught the material/themed/semantic pattern, picks best approach</p>
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
    descriptions: dict[str, str] = {}

    # ── Base objects ──
    print("=== Base Objects ===")
    for name, visual in BASE_OBJECTS:
        t0 = time.monotonic()
        print(f"  {name}...", end=" ", flush=True)
        processed, raw = await generate_base_sprite(name, visual)
        elapsed = time.monotonic() - t0
        path = OUT_DIR / f"base_{name}.png"
        raw_path = OUT_DIR / f"base_{name}_raw.png"
        path.write_bytes(processed)
        raw_path.write_bytes(raw)
        sprite_data[name] = processed
        descriptions[name] = visual
        base_entries.append(SpriteEntry(name=name, path=path, raw_path=raw_path, elapsed=elapsed))
        print(f"{elapsed:.1f}s")

    # ── Combinations ──
    # Per pair: 3 LLM variants (LLM order) + 2 best r3 templates (both orders) = 7
    total = len(TEST_PAIRS) * 7
    done = 0
    print(f"\n=== {len(TEST_PAIRS)} pairs x 7 variants = {total} images ===")

    for name_a, name_b in TEST_PAIRS:
        desc_a = descriptions[name_a]
        desc_b = descriptions[name_b]
        print(f"\n  {name_a} + {name_b}:")

        # LLM picks ordering
        llm_order_idx = await llm_pick_order(name_a, desc_a, name_b, desc_b)
        llm_first = [name_a, name_b][llm_order_idx]
        llm_second = [name_a, name_b][1 - llm_order_idx]
        print(f"    LLM order: {llm_first} → {llm_second}")

        user_prompt = USER_PROMPT_TEMPLATE.format(
            name_a=name_a, name_b=name_b, desc_a=desc_a, desc_b=desc_b
        )

        # LLM-generated prompt variants
        for label, strat_desc, instruction in LLM_INSTRUCTIONS:
            llm_desc = await llm_write_prompt(user_prompt, instruction)
            print(f"    {label}: {llm_desc}")

            image_prompt = f"{STYLE}, {llm_desc}, {SUFFIX}"

            done += 1
            print(f"      [{done}/{total}] ({llm_first} → {llm_second})...", end=" ", flush=True)
            t0 = time.monotonic()
            raw = await flux_edits(
                image_prompt,
                [(f"{llm_first}.png", sprite_data[llm_first]),
                 (f"{llm_second}.png", sprite_data[llm_second])],
            )
            processed = await process_sprite(raw)
            elapsed = time.monotonic() - t0

            safe = f"{name_a}+{name_b}_{label}"
            path = OUT_DIR / f"{safe}.png"
            raw_path = OUT_DIR / f"{safe}_raw.png"
            path.write_bytes(processed)
            raw_path.write_bytes(raw)

            combo_entries.append(SpriteEntry(
                name=f"{name_a} + {name_b}", path=path, raw_path=raw_path,
                order=f"{llm_first} \u2192 {llm_second}", prompt_label=label,
                prompt_desc=strat_desc, prompt_used=image_prompt,
                input_image_paths=[
                    OUT_DIR / f"base_{llm_first}.png",
                    OUT_DIR / f"base_{llm_second}.png",
                ],
                elapsed=elapsed, llm_output=llm_desc, order_source="llm",
            ))
            print(f"{elapsed:.1f}s")

        # Round 3 best templates for comparison (both orderings)
        r3_templates = [
            (
                "r3-material",
                "Round 3: material transfer",
                f"{STYLE}, "
                f"a {name_b} made entirely from {name_a}, "
                f"retaining the silhouette of {desc_b} but constructed from {desc_a}, "
                f"{SUFFIX}",
            ),
            (
                "r3-themed",
                "Round 3: themed",
                f"{STYLE}, "
                f"a {name_b} themed with {name_a}, "
                f"{desc_b} with {name_a} elements, accents, and details woven into its design, "
                f"{SUFFIX}",
            ),
        ]

        for label, strat_desc, prompt in r3_templates:
            for first, second, order_label, order_src in [
                (name_a, name_b, f"{name_a} \u2192 {name_b}", "fixed-ab"),
                (name_b, name_a, f"{name_b} \u2192 {name_a}", "fixed-ba"),
            ]:
                done += 1
                print(f"      [{done}/{total}] {label} ({order_label})...", end=" ", flush=True)
                t0 = time.monotonic()
                raw = await flux_edits(
                    prompt,
                    [(f"{first}.png", sprite_data[first]),
                     (f"{second}.png", sprite_data[second])],
                )
                processed = await process_sprite(raw)
                elapsed = time.monotonic() - t0

                safe_order = order_src.replace("-", "")
                safe = f"{name_a}+{name_b}_{label}_{safe_order}"
                path = OUT_DIR / f"{safe}.png"
                raw_path = OUT_DIR / f"{safe}_raw.png"
                path.write_bytes(processed)
                raw_path.write_bytes(raw)

                combo_entries.append(SpriteEntry(
                    name=f"{name_a} + {name_b}", path=path, raw_path=raw_path,
                    order=order_label, prompt_label=label, prompt_desc=strat_desc,
                    prompt_used=prompt,
                    input_image_paths=[
                        OUT_DIR / f"base_{first}.png",
                        OUT_DIR / f"base_{second}.png",
                    ],
                    elapsed=elapsed, order_source=order_src,
                ))
                print(f"{elapsed:.1f}s")

    # ── Dashboard ──
    dash_path = generate_dashboard(base_entries, combo_entries)
    total_time = sum(e.elapsed for e in base_entries) + sum(e.elapsed for e in combo_entries)
    print(f"\n{'=' * 50}")
    print(f"Total images: {len(base_entries) + len(combo_entries)} ({total_time:.0f}s cumulative)")
    print(f"Dashboard:    {dash_path.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
