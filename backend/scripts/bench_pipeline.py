#!/usr/bin/env python3
"""Image pipeline prompt sweep harness — Phase 1.

Runs Phase 1 of the test plan in `backend/experiments/pipeline/PLAN.md`:
single-variable sweeps for H1 (simplify multi-ref), H12 (orientation), and
H10 (lighting 3-way). Cascade-measures build-level interventions through
img2img by re-running baselines on each intervention's base sprites.

Calls the real `app.images.pipeline` entry points via monkey-patching so we
exercise the same code path that ships to production. Seeds are forced via
`app.images.local_image.seed_override` for reproducible FLUX output.

Outputs:
    experiments/pipeline/bases/{base_set}/{object}-s{seed}.png   — base sprites
    experiments/pipeline/sprites/{step}/{pipeline}.{variant}@{bases}/{case}-s{seed}.png
    experiments/pipeline/llm_cache/{variant}/{case}.txt          — LLM output cache
    experiments/pipeline/index.html                              — dashboard

Usage:
    cd backend
    uv run python scripts/bench_pipeline.py --step 1.1            # H1 sweep
    uv run python scripts/bench_pipeline.py --step 1.2            # H12 sweep
    uv run python scripts/bench_pipeline.py --step 1.3            # H10 sweep
    uv run python scripts/bench_pipeline.py --step 1.1 --only combine
    uv run python scripts/bench_pipeline.py --step 1.1 --dry-run  # no FLUX calls
    uv run python scripts/bench_pipeline.py --rebuild-base         # force regen
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import hashlib
import io
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from PIL import Image

# ═══════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════

OUT_DIR = Path("experiments/pipeline")
BASES_DIR = OUT_DIR / "bases"
SPRITES_DIR = OUT_DIR / "sprites"
LLM_CACHE_DIR = OUT_DIR / "llm_cache"
DASHBOARD_PATH = OUT_DIR / "index.html"

SEEDS: list[int] = [1, 2, 3]

Pipeline = Literal["build", "destruction", "carry", "ride", "combine"]


# ═══════════════════════════════════════════════════════════════════════════
# Catalog
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CatalogObject:
    name: str
    visual: str
    tier: Literal["easy", "hard"]


OBJECTS: dict[str, CatalogObject] = {
    # Easy tier
    "flame": CatalogObject(
        "flame", "bright orange fire with flickering tongues and ember particles", "easy"
    ),
    "crystal": CatalogObject(
        "crystal", "translucent purple crystal with geometric facets and inner glow", "easy"
    ),
    "sword": CatalogObject(
        "sword", "steel longsword with leather-wrapped hilt and gleaming blade", "easy"
    ),
    "tree": CatalogObject("tree", "gnarled oak tree with twisted branches and thick roots", "easy"),
    "skull": CatalogObject(
        "skull", "weathered human skull with cracked bone and hollow eye sockets", "easy"
    ),
    "mushroom": CatalogObject(
        "mushroom", "red-capped forest mushroom with white spots and pale stem", "easy"
    ),
    # Hard tier
    "shadow": CatalogObject(
        "shadow", "living silhouette of darkness with wispy tendrils at its edges", "hard"
    ),
    "song": CatalogObject(
        "song", "shimmering ribbon of translucent musical notes trailing golden sparks", "hard"
    ),
    "cloud": CatalogObject(
        "cloud", "fluffy white cumulus with soft cotton texture and faint blue underbelly", "hard"
    ),
    "clockwork": CatalogObject(
        "clockwork",
        "tangle of brass gears, tiny pistons, and coiled springs held in an open frame",
        "hard",
    ),
    "jellyfish": CatalogObject(
        "jellyfish",
        "translucent pink bell with trailing filament tentacles and glowing spots",
        "hard",
    ),
    "bookworm": CatalogObject(
        "bookworm",
        "fat pale grub emerging from a chewed leather-bound tome, paper scraps clinging to it",
        "hard",
    ),
}

BUILD_CASES: list[str] = list(OBJECTS.keys())
DESTRUCTION_CASES: list[str] = ["sword", "tree", "clockwork", "jellyfish"]
CARRY_CASES: list[str] = ["sword", "mushroom", "clockwork", "jellyfish"]
RIDE_CASES: list[str] = ["tree", "skull", "cloud", "jellyfish"]
COMBINE_PAIRS: list[tuple[str, str]] = [
    ("flame", "sword"),
    ("crystal", "skull"),
    ("flame", "cloud"),
    ("tree", "clockwork"),
    ("shadow", "song"),
    ("jellyfish", "bookworm"),
]


def case_id(pipeline: Pipeline, case: str | tuple[str, str]) -> str:
    """Stable identifier for a test case within a pipeline."""
    if isinstance(case, tuple):
        return f"{case[0]}+{case[1]}"
    return case


def safe_name(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._+-]", "_", s)


# ═══════════════════════════════════════════════════════════════════════════
# Variants
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class Variant:
    """A prompt variant = label + patches applied to `app.images.pipeline`.

    `patches` maps attribute name → new value. Values can be constants or
    replacement functions. Applied via `contextlib.ExitStack` so the originals
    are restored after the variant finishes.
    """

    label: str  # e.g. "H1.simple-rel"
    pipeline: Pipeline
    description: str
    patches: dict[str, Any] = field(default_factory=dict)
    is_baseline: bool = False


# ── Baselines (no patches, just labels) ──

BASELINES: dict[Pipeline, Variant] = {
    p: Variant(
        label="baseline", pipeline=p, description="current production prompts", is_baseline=True
    )
    for p in ("build", "destruction", "carry", "ride", "combine")
}


# ── H1 simple-rel ──


def _H1_destruction(object_name: str, object_visual: str, destruction_result_name: str):
    instructions = (
        "You write short visual descriptions for a sprite image generator. "
        "The generator receives a reference image of the object and already knows what it "
        "looks like — do NOT re-describe its colors or materials. "
        "Describe ONLY the destruction: what shape the broken remains take. "
        "Under 12 words. Output ONLY the description."
    )
    user_message = (
        f"Object in reference image: {object_name}\n"
        f"Describe the broken remains as a pile of debris:"
    )
    return instructions, user_message


def _H1_carry_ride(affordance: int, object_name: str, object_visual: str):
    if affordance == 1:
        instructions = (
            "You write short visual descriptions for a sprite image generator. "
            "The generator receives two reference images: a character (image 1) and a mount (image 2). "
            "It already knows what they look like — do NOT re-describe them. "
            "Describe ONLY the relationship: how the character sits on the mount. "
            "Under 10 words. Output ONLY the description."
        )
        user_message = f"Describe the character riding the {object_name}:"
    else:
        instructions = (
            "You write short visual descriptions for a sprite image generator. "
            "The generator receives two reference images: a character (image 1) and an object (image 2). "
            "It already knows what they look like — do NOT re-describe them. "
            "Describe ONLY the relationship: how the character holds or carries the object. "
            "Under 10 words. Output ONLY the description."
        )
        user_message = f"Describe the character carrying the {object_name}:"
    return instructions, user_message


def _H1_combine(name_a: str, visual_a: str, name_b: str, visual_b: str):
    instructions = (
        "You write short visual descriptions for a sprite image generator. "
        "The generator receives two reference images (image 1 and image 2) and already knows "
        "what they look like — do NOT re-describe their colors, materials, or shapes. "
        "Describe ONLY how they combine. Pick ONE pattern:\n"
        "- 'the form of image 2 constructed from image 1' (when image 1 is a material)\n"
        "- 'image 2 with image 1 elements woven into its design' (when image 1 is aesthetic)\n"
        "- 'a hybrid of image 1 and image 2' (when both contribute equally)\n"
        "Under 15 words. Output ONLY the description."
    )
    user_message = f"Image 1: {name_a}\nImage 2: {name_b}\nDescribe the combination:"
    return instructions, user_message


H1_VARIANTS: dict[Pipeline, Variant] = {
    "destruction": Variant(
        label="H1.simple-rel",
        pipeline="destruction",
        description="LLM describes only the destruction, not the object's appearance",
        patches={"build_destruction_prompt": _H1_destruction},
    ),
    "carry": Variant(
        label="H1.simple-rel",
        pipeline="carry",
        description="LLM describes only the carry relationship, not what anything looks like",
        patches={"build_carry_ride_prompt": _H1_carry_ride},
    ),
    "ride": Variant(
        label="H1.simple-rel",
        pipeline="ride",
        description="LLM describes only the ride relationship, not what anything looks like",
        patches={"build_carry_ride_prompt": _H1_carry_ride},
    ),
    "combine": Variant(
        label="H1.simple-rel",
        pipeline="combine",
        description="LLM describes only how the two images combine, no re-describing",
        patches={"build_combine_prompt": _H1_combine},
    ),
}


# ── H12 orient-right (build only; cascade through img2img baselines) ──


def _H12_build(name: str, visual: str) -> str:
    return (
        f"A mixed media collage of {name} made from cut paper, magazine clippings, "
        f"and cardboard, held together with visible scotch tape and glue. "
        f"{visual} "
        f"Side view facing right in profile, single centered object on a solid contrasting background. "
        f"Flat lighting, clean edges, no text."
    )


H12_BUILD = Variant(
    label="H12.orient-right",
    pipeline="build",
    description="append 'facing right in profile' to the build prompt",
    patches={"build_text_to_image_prompt": _H12_build},
)


# ── H10 lighting 3-way (build only; cascade through img2img baselines) ──


def _H10_build_none(name: str, visual: str) -> str:
    return (
        f"A mixed media collage of {name} made from cut paper, magazine clippings, "
        f"and cardboard, held together with visible scotch tape and glue. "
        f"{visual} "
        f"Side view, single centered object on a solid contrasting background. "
        f"Clean edges, no text."
    )


def _H10_build_diffused(name: str, visual: str) -> str:
    return (
        f"A mixed media collage of {name} made from cut paper, magazine clippings, "
        f"and cardboard, held together with visible scotch tape and glue. "
        f"{visual} "
        f"Side view, single centered object on a solid contrasting background. "
        f"Even diffused lighting, no harsh shadows, no cast shadows, clean edges, no text."
    )


H10_BUILD_NONE = Variant(
    label="H10.light-none",
    pipeline="build",
    description="no lighting mention at all",
    patches={"build_text_to_image_prompt": _H10_build_none},
)

H10_BUILD_DIFFUSED = Variant(
    label="H10.light-diffused",
    pipeline="build",
    description="even diffused lighting, no harsh shadows",
    patches={"build_text_to_image_prompt": _H10_build_diffused},
)


# ── H13 paper-as-subject (build only; fixes "real object with paper stuck on") ──
#
# Baseline reads as "start with a {name}, then add paper and tape to it". H13
# variants restructure the sentence so that paper-ness is a property of the
# subject itself, not an additive material layer. Motivated by user feedback on
# step 1.1 bases (crystal, clockwork, flame, jellyfish all show the compositing
# failure mode).


def _H13_build_paper_cutout(name: str, visual: str) -> str:
    return (
        f"{name}, a paper cutout: {visual}. "
        f"Entirely formed from layered construction paper with visible cut edges "
        f"and slight paper grain. Flat lighting, side view, solid contrasting "
        f"background, no text."
    )


def _H13_build_sculpted(name: str, visual: str) -> str:
    return (
        f"{name} sculpted entirely from cut and torn paper: {visual}. "
        f"The object's surface is paper texture; its silhouette is cut from "
        f"construction paper; overlapping layers cast subtle shadows where they meet. "
        f"Side view on solid contrasting background, flat lighting, no text."
    )


def _H13_build_texture_first(name: str, visual: str) -> str:
    return (
        f"{name} with torn-paper edges and construction-paper surfaces: {visual}. "
        f"Visible paper grain, slightly frayed cut lines, matte paper colors throughout. "
        f"Flat lighting, side view on solid contrasting background."
    )


def _H13_build_craft_artwork(name: str, visual: str) -> str:
    return (
        f"A paper craft artwork of {name}: {visual}. "
        f"Every part of the object is cut, folded, or torn from coloured paper. "
        f"Not painted, not photographic — a tactile paper sculpture on a solid "
        f"contrasting background. Side view, flat lighting."
    )


def _H13_build_minimal(name: str, visual: str) -> str:
    return (
        f"Paper craft {name}: {visual}. "
        f"Side view, flat lighting, solid contrasting background, no text."
    )


def _H13_build_hybrid(name: str, visual: str) -> str:
    return (
        f"{name}, a paper cutout: {visual}. "
        f"Entirely formed from layered construction paper with visible cut edges, "
        f"slight paper grain, and subtle shadows where overlapping layers meet. "
        f"Flat lighting, side view, solid contrasting background, no text."
    )


H13_VARIANTS: list[Variant] = [
    Variant(
        label="H13.paper-cutout",
        pipeline="build",
        description="subject-first, 'a paper cutout' appositive",
        patches={"build_text_to_image_prompt": _H13_build_paper_cutout},
    ),
    Variant(
        label="H13.sculpted",
        pipeline="build",
        description="'sculpted entirely from paper' with surface=texture framing",
        patches={"build_text_to_image_prompt": _H13_build_sculpted},
    ),
    Variant(
        label="H13.texture-first",
        pipeline="build",
        description="describes paper properties as subject attributes (guide pattern)",
        patches={"build_text_to_image_prompt": _H13_build_texture_first},
    ),
    Variant(
        label="H13.craft-artwork",
        pipeline="build",
        description="'paper craft artwork' + explicit 'not photographic' negative hint",
        patches={"build_text_to_image_prompt": _H13_build_craft_artwork},
    ),
    Variant(
        label="H13.minimal",
        pipeline="build",
        description="minimal 'paper craft {name}' with no material elaboration",
        patches={"build_text_to_image_prompt": _H13_build_minimal},
    ),
    Variant(
        label="H13.hybrid",
        pipeline="build",
        description="paper-cutout framing + sculpted's 'subtle shadows where layers meet'",
        patches={"build_text_to_image_prompt": _H13_build_hybrid},
    ),
]


# ═══════════════════════════════════════════════════════════════════════════
# Patch application
# ═══════════════════════════════════════════════════════════════════════════


@contextlib.contextmanager
def apply_patches(patches: dict[str, Any]):
    """Temporarily swap attributes on `app.images.pipeline` module."""
    from app.images import pipeline as _pipeline

    if not patches:
        yield
        return
    originals: dict[str, Any] = {}
    try:
        for attr, new_value in patches.items():
            originals[attr] = getattr(_pipeline, attr)
            setattr(_pipeline, attr, new_value)
        yield
    finally:
        for attr, original in originals.items():
            setattr(_pipeline, attr, original)


# ═══════════════════════════════════════════════════════════════════════════
# Caches (disk-backed, resumable)
# ═══════════════════════════════════════════════════════════════════════════


def base_sprite_path(base_set: str, object_name: str, seed: int) -> Path:
    return BASES_DIR / safe_name(base_set) / f"{safe_name(object_name)}-s{seed}.png"


def base_sprite_raw_path(base_set: str, object_name: str, seed: int) -> Path:
    return BASES_DIR / safe_name(base_set) / f"{safe_name(object_name)}-s{seed}.raw.png"


def sprite_output_path(
    step: str, pipeline: Pipeline, variant_label: str, bases: str, case: str, seed: int
) -> Path:
    slug = f"{pipeline}.{safe_name(variant_label)}@{safe_name(bases)}"
    return SPRITES_DIR / step / slug / f"{safe_name(case)}-s{seed}.png"


def sprite_raw_path(
    step: str, pipeline: Pipeline, variant_label: str, bases: str, case: str, seed: int
) -> Path:
    return sprite_output_path(step, pipeline, variant_label, bases, case, seed).with_suffix(
        ".raw.png"
    )


def llm_cache_path(variant_label: str, pipeline: Pipeline, case: str) -> Path:
    return LLM_CACHE_DIR / safe_name(variant_label) / f"{pipeline}-{safe_name(case)}.json"


def load_llm_cache(variant_label: str, pipeline: Pipeline, case: str) -> dict[str, str] | None:
    p = llm_cache_path(variant_label, pipeline, case)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_llm_cache(variant_label: str, pipeline: Pipeline, case: str, data: dict[str, str]) -> None:
    p = llm_cache_path(variant_label, pipeline, case)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# Pipeline runners (call real app.images.pipeline with patches applied)
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class CellResult:
    pipeline: Pipeline
    variant_label: str
    bases: str
    case: str
    seed: int
    output_path: Path
    raw_path: Path
    input_paths: list[Path]
    llm_output: str  # empty string for build
    flux_prompt: str
    elapsed: float
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def sprite_id(self) -> str:
        bases_tag = "" if self.bases == "baseline" else f"@{self.bases}"
        return f"{self.pipeline}.{self.variant_label}{bases_tag}/{self.case}#s{self.seed}"


async def run_build_cell(
    variant: Variant,
    object_name: str,
    seed: int,
    base_set: str,
    *,
    rebuild: bool,
) -> CellResult:
    """Generate one base sprite and cache it. Returns path-only metadata.

    The build step writes its output to the shared base sprite cache, not
    the per-step sprites dir — downstream img2img steps read from that cache.
    """
    from app.images import pipeline as _pipeline
    from app.images.local_image import seed_override

    obj = OBJECTS[object_name]
    out_path = base_sprite_path(base_set, object_name, seed)
    raw_path = base_sprite_raw_path(base_set, object_name, seed)

    with apply_patches(variant.patches):
        prompt = _pipeline.build_text_to_image_prompt(obj.name, obj.visual)

    if out_path.exists() and not rebuild:
        return CellResult(
            pipeline="build",
            variant_label=variant.label,
            bases=base_set,
            case=object_name,
            seed=seed,
            output_path=out_path,
            raw_path=raw_path if raw_path.exists() else out_path,
            input_paths=[],
            llm_output="",
            flux_prompt=prompt,
            elapsed=0.0,
            extra={"cached": True},
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    with apply_patches(variant.patches), seed_override(seed):
        from app.images.local_image import generate_image

        raw_bytes = await generate_image(prompt)
        removed = await _pipeline.remove_bg(raw_bytes)
        processed = _pipeline._postprocess_sprite(removed)

    out_path.write_bytes(processed)
    raw_path.write_bytes(raw_bytes)
    elapsed = time.monotonic() - t0

    return CellResult(
        pipeline="build",
        variant_label=variant.label,
        bases=base_set,
        case=object_name,
        seed=seed,
        output_path=out_path,
        raw_path=raw_path,
        input_paths=[],
        llm_output="",
        flux_prompt=prompt,
        elapsed=elapsed,
    )


async def _get_or_generate_llm(
    variant: Variant,
    pipeline: Pipeline,
    case: str,
    llm_fn: Callable[[], Any],
    key: str = "llm_output",
) -> dict[str, str]:
    cached = load_llm_cache(variant.label, pipeline, case)
    if cached and key in cached:
        return cached
    result = await llm_fn()
    data = cached or {}
    if isinstance(result, dict):
        data.update(result)
    else:
        data[key] = str(result)
    save_llm_cache(variant.label, pipeline, case, data)
    return data


async def run_destruction_cell(
    variant: Variant,
    object_name: str,
    seed: int,
    base_set: str,
    step: str,
) -> CellResult:
    from app.creator.llm import ask_text
    from app.images import pipeline as _pipeline
    from app.images.local_image import seed_override

    obj = OBJECTS[object_name]
    debris_name = f"{object_name} debris"
    base_path = base_sprite_path(base_set, object_name, seed)
    if not base_path.exists():
        raise FileNotFoundError(
            f"Missing base sprite {base_path} — run --step 1.1 first or --rebuild-base"
        )

    # LLM output (cached across seeds)
    async def _llm() -> str:
        with apply_patches(variant.patches):
            instructions, user_prompt = _pipeline.build_destruction_prompt(
                obj.name, obj.visual, debris_name
            )
        return await ask_text(user_prompt, max_tokens=250, instructions=instructions)

    llm_data = await _get_or_generate_llm(variant, "destruction", object_name, _llm)
    llm_output = llm_data["llm_output"]

    # Build FLUX prompt using patched STYLE/SUFFIX
    with apply_patches(variant.patches):
        full_prompt = f"{_pipeline.IMG2IMG_STYLE}, {llm_output}, {_pipeline.IMG2IMG_SUFFIX_OBJECT}"

    obj_ref = _pipeline.prepare_reference(base_path.read_bytes())

    out_path = sprite_output_path(step, "destruction", variant.label, base_set, object_name, seed)
    raw_path = sprite_raw_path(step, "destruction", variant.label, base_set, object_name, seed)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists():
        return CellResult(
            pipeline="destruction",
            variant_label=variant.label,
            bases=base_set,
            case=object_name,
            seed=seed,
            output_path=out_path,
            raw_path=raw_path if raw_path.exists() else out_path,
            input_paths=[base_path],
            llm_output=llm_output,
            flux_prompt=full_prompt,
            elapsed=0.0,
            extra={"cached": True},
        )

    t0 = time.monotonic()
    with seed_override(seed):
        from app.images.local_image import generate_image_edit

        raw_bytes = await generate_image_edit(full_prompt, [("object.png", obj_ref)])
        removed = await _pipeline.remove_bg(raw_bytes)
        processed = _pipeline._postprocess_sprite(removed)
    elapsed = time.monotonic() - t0

    out_path.write_bytes(processed)
    raw_path.write_bytes(raw_bytes)

    return CellResult(
        pipeline="destruction",
        variant_label=variant.label,
        bases=base_set,
        case=object_name,
        seed=seed,
        output_path=out_path,
        raw_path=raw_path,
        input_paths=[base_path],
        llm_output=llm_output,
        flux_prompt=full_prompt,
        elapsed=elapsed,
    )


async def run_carry_ride_cell(
    variant: Variant,
    pipeline: Literal["carry", "ride"],
    object_name: str,
    seed: int,
    base_set: str,
    step: str,
) -> CellResult:
    from app.creator.llm import ask_text
    from app.images import pipeline as _pipeline
    from app.images.local_image import generate_image_edit, seed_override

    obj = OBJECTS[object_name]
    affordance = 1 if pipeline == "ride" else 0
    base_path = base_sprite_path(base_set, object_name, seed)
    if not base_path.exists():
        raise FileNotFoundError(
            f"Missing base sprite {base_path} — run --step 1.1 first or --rebuild-base"
        )

    async def _llm() -> str:
        with apply_patches(variant.patches):
            instructions, user_prompt = _pipeline.build_carry_ride_prompt(
                affordance, obj.name, obj.visual
            )
        return await ask_text(user_prompt, max_tokens=250, instructions=instructions)

    llm_data = await _get_or_generate_llm(variant, pipeline, object_name, _llm)
    llm_output = llm_data["llm_output"]

    with apply_patches(variant.patches):
        full_prompt = f"{_pipeline.IMG2IMG_STYLE}, {llm_output}, {_pipeline.IMG2IMG_SUFFIX_SCENE}"

    char_ref = _pipeline.prepare_reference(_pipeline.get_player_sprite())
    obj_ref = _pipeline.prepare_reference(base_path.read_bytes())

    out_path = sprite_output_path(step, pipeline, variant.label, base_set, object_name, seed)
    raw_path = sprite_raw_path(step, pipeline, variant.label, base_set, object_name, seed)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Save the player ref to disk once per step for dashboard embedding
    player_ref_path = BASES_DIR / "_player_ref.png"
    if not player_ref_path.exists():
        player_ref_path.parent.mkdir(parents=True, exist_ok=True)
        player_ref_path.write_bytes(_pipeline.get_player_sprite())

    if out_path.exists():
        return CellResult(
            pipeline=pipeline,
            variant_label=variant.label,
            bases=base_set,
            case=object_name,
            seed=seed,
            output_path=out_path,
            raw_path=raw_path if raw_path.exists() else out_path,
            input_paths=[player_ref_path, base_path],
            llm_output=llm_output,
            flux_prompt=full_prompt,
            elapsed=0.0,
            extra={"cached": True},
        )

    t0 = time.monotonic()
    with seed_override(seed):
        raw_bytes = await generate_image_edit(
            full_prompt, [("character.png", char_ref), ("object.png", obj_ref)]
        )
        removed = await _pipeline.remove_bg(raw_bytes)
        processed = _pipeline._postprocess_sprite(removed)
    elapsed = time.monotonic() - t0

    out_path.write_bytes(processed)
    raw_path.write_bytes(raw_bytes)

    return CellResult(
        pipeline=pipeline,
        variant_label=variant.label,
        bases=base_set,
        case=object_name,
        seed=seed,
        output_path=out_path,
        raw_path=raw_path,
        input_paths=[player_ref_path, base_path],
        llm_output=llm_output,
        flux_prompt=full_prompt,
        elapsed=elapsed,
    )


async def run_combine_cell(
    variant: Variant,
    pair: tuple[str, str],
    seed: int,
    base_set: str,
    step: str,
) -> CellResult:
    from app.creator.llm import ask_choice, ask_text
    from app.images import pipeline as _pipeline
    from app.images.local_image import generate_image_edit, seed_override

    name_a, name_b = pair
    obj_a, obj_b = OBJECTS[name_a], OBJECTS[name_b]
    base_a = base_sprite_path(base_set, name_a, seed)
    base_b = base_sprite_path(base_set, name_b, seed)
    if not base_a.exists() or not base_b.exists():
        raise FileNotFoundError(
            f"Missing base sprite(s) for {name_a}/{name_b} — run --step 1.1 first"
        )

    case = f"{name_a}+{name_b}"

    async def _llm() -> dict[str, str]:
        with apply_patches(variant.patches):
            order_instructions, order_prompt = _pipeline.build_combine_order_prompt(name_a, name_b)
            desc_instructions, desc_prompt = _pipeline.build_combine_prompt(
                name_a, obj_a.visual, name_b, obj_b.visual
            )
        order_str, llm_desc = await asyncio.gather(
            ask_choice(
                order_prompt, choices=("1", "2"), default="1", instructions=order_instructions
            ),
            ask_text(desc_prompt, max_tokens=250, instructions=desc_instructions),
        )
        return {"llm_output": llm_desc, "order": order_str}

    llm_data = await _get_or_generate_llm(variant, "combine", case, _llm, key="llm_output")
    llm_output = llm_data["llm_output"]
    order_str = llm_data.get("order", "1")

    with apply_patches(variant.patches):
        full_prompt = f"{_pipeline.IMG2IMG_STYLE}, {llm_output}, {_pipeline.IMG2IMG_SUFFIX_OBJECT}"

    ref_a = _pipeline.prepare_reference(base_a.read_bytes())
    ref_b = _pipeline.prepare_reference(base_b.read_bytes())

    if order_str == "1":
        images = [(f"{name_a}.png", ref_a), (f"{name_b}.png", ref_b)]
        inputs = [base_a, base_b]
    else:
        images = [(f"{name_b}.png", ref_b), (f"{name_a}.png", ref_a)]
        inputs = [base_b, base_a]

    out_path = sprite_output_path(step, "combine", variant.label, base_set, case, seed)
    raw_path = sprite_raw_path(step, "combine", variant.label, base_set, case, seed)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists():
        return CellResult(
            pipeline="combine",
            variant_label=variant.label,
            bases=base_set,
            case=case,
            seed=seed,
            output_path=out_path,
            raw_path=raw_path if raw_path.exists() else out_path,
            input_paths=inputs,
            llm_output=llm_output,
            flux_prompt=full_prompt,
            elapsed=0.0,
            extra={"cached": True, "order": order_str},
        )

    t0 = time.monotonic()
    with seed_override(seed):
        raw_bytes = await generate_image_edit(full_prompt, images)
        removed = await _pipeline.remove_bg(raw_bytes)
        processed = _pipeline._postprocess_sprite(removed)
    elapsed = time.monotonic() - t0

    out_path.write_bytes(processed)
    raw_path.write_bytes(raw_bytes)

    return CellResult(
        pipeline="combine",
        variant_label=variant.label,
        bases=base_set,
        case=case,
        seed=seed,
        output_path=out_path,
        raw_path=raw_path,
        input_paths=inputs,
        llm_output=llm_output,
        flux_prompt=full_prompt,
        elapsed=elapsed,
        extra={"order": order_str},
    )


# ═══════════════════════════════════════════════════════════════════════════
# Step runners
# ═══════════════════════════════════════════════════════════════════════════


async def ensure_baseline_bases(
    *, rebuild: bool, only_cases: list[str] | None = None
) -> list[CellResult]:
    """Phase 1 prerequisite: baseline build sprites exist for all BUILD_CASES × 3 seeds."""
    cases = only_cases or BUILD_CASES
    print(f"\n── Baseline base sprites ({len(cases)} objects × {len(SEEDS)} seeds) ──")
    results: list[CellResult] = []
    for obj_name in cases:
        for seed in SEEDS:
            r = await run_build_cell(
                BASELINES["build"], obj_name, seed, "baseline", rebuild=rebuild
            )
            status = "cached" if r.extra.get("cached") else f"{r.elapsed:.1f}s"
            print(f"  baseline/{obj_name}-s{seed}  {status}")
            results.append(r)
    return results


async def run_step_1_1(
    *, only_pipeline: str | None, rebuild_base: bool, dry_run: bool
) -> list[CellResult]:
    """Step 1.1: H1 simple-rel sweep across img2img pipelines, baseline bases."""
    print("\n" + "═" * 70)
    print("STEP 1.1 — H1 simple-rel sweep (img2img only)")
    print("═" * 70)

    if dry_run:
        print("[DRY RUN] Would ensure baseline bases, then run H1 variants for:")
        for p in ("destruction", "carry", "ride", "combine"):
            if only_pipeline and only_pipeline != p:
                continue
            print(f"  {p}: baseline + H1.simple-rel")
        return []

    await ensure_baseline_bases(rebuild=rebuild_base)

    cells: list[CellResult] = []
    pipelines_to_run: list[Pipeline] = ["destruction", "carry", "ride", "combine"]
    if only_pipeline:
        pipelines_to_run = [p for p in pipelines_to_run if p == only_pipeline]  # type: ignore[misc]

    for p in pipelines_to_run:
        print(f"\n── {p} (baseline + H1.simple-rel) ──")
        variants = [BASELINES[p], H1_VARIANTS[p]]
        for variant in variants:
            cells.extend(await _run_img2img_variant("1.1", variant, p, "baseline"))
    return cells


async def run_step_1_2(
    *, only_pipeline: str | None, rebuild_base: bool, dry_run: bool
) -> list[CellResult]:
    """Step 1.2: H12 orient-right build sweep + img2img baselines on H12 bases."""
    print("\n" + "═" * 70)
    print("STEP 1.2 — H12 orient-right sweep (build + img2img cascade)")
    print("═" * 70)

    if dry_run:
        print("[DRY RUN] Would generate H12.orient-right bases for all 12 objects,")
        print("          then re-run img2img baselines on those bases.")
        return []

    await ensure_baseline_bases(rebuild=rebuild_base)

    print(f"\n── H12.orient-right bases ({len(BUILD_CASES)} objects × {len(SEEDS)} seeds) ──")
    cells: list[CellResult] = []
    for obj_name in BUILD_CASES:
        for seed in SEEDS:
            r = await run_build_cell(
                H12_BUILD, obj_name, seed, "H12.orient-right", rebuild=rebuild_base
            )
            status = "cached" if r.extra.get("cached") else f"{r.elapsed:.1f}s"
            print(f"  H12.orient-right/{obj_name}-s{seed}  {status}")
            cells.append(r)

    pipelines_to_run: list[Pipeline] = ["destruction", "carry", "ride", "combine"]
    if only_pipeline:
        pipelines_to_run = [p for p in pipelines_to_run if p == only_pipeline]  # type: ignore[misc]

    for p in pipelines_to_run:
        print(f"\n── {p} baseline on H12.orient-right bases ──")
        cells.extend(await _run_img2img_variant("1.2", BASELINES[p], p, "H12.orient-right"))
    return cells


async def run_step_1_3(
    *, only_pipeline: str | None, rebuild_base: bool, dry_run: bool
) -> list[CellResult]:
    """Step 1.3: H10 lighting 3-way build sweep + cascade."""
    print("\n" + "═" * 70)
    print("STEP 1.3 — H10 lighting 3-way sweep (build + img2img cascade)")
    print("═" * 70)

    if dry_run:
        print("[DRY RUN] Would generate H10.light-none and H10.light-diffused bases,")
        print("          then re-run img2img baselines on each.")
        return []

    await ensure_baseline_bases(rebuild=rebuild_base)

    cells: list[CellResult] = []
    for variant, base_set in (
        (H10_BUILD_NONE, "H10.light-none"),
        (H10_BUILD_DIFFUSED, "H10.light-diffused"),
    ):
        print(f"\n── {base_set} bases ──")
        for obj_name in BUILD_CASES:
            for seed in SEEDS:
                r = await run_build_cell(variant, obj_name, seed, base_set, rebuild=rebuild_base)
                status = "cached" if r.extra.get("cached") else f"{r.elapsed:.1f}s"
                print(f"  {base_set}/{obj_name}-s{seed}  {status}")
                cells.append(r)

    pipelines_to_run: list[Pipeline] = ["destruction", "carry", "ride", "combine"]
    if only_pipeline:
        pipelines_to_run = [p for p in pipelines_to_run if p == only_pipeline]  # type: ignore[misc]

    for base_set in ("H10.light-none", "H10.light-diffused"):
        for p in pipelines_to_run:
            print(f"\n── {p} baseline on {base_set} bases ──")
            cells.extend(await _run_img2img_variant("1.3", BASELINES[p], p, base_set))
    return cells


async def run_step_1_4(
    *, only_pipeline: str | None, rebuild_base: bool, dry_run: bool
) -> list[CellResult]:
    """Step 1.4: H13 build-prompt vocabulary sweep (build only, no cascade).

    Tests 5 variants of the text-to-image prompt that restructure the
    paper-as-subject framing to fix the "real object with paper stuck on"
    failure mode observed after step 1.1.
    """
    del only_pipeline  # build-only sweep, no img2img cascade
    print("\n" + "═" * 70)
    print("STEP 1.4 — H13 paper-as-subject build sweep (build only)")
    print("═" * 70)

    if dry_run:
        print("[DRY RUN] Would generate baseline bases + 5 H13 variants × 12 objects × 3 seeds.")
        for v in H13_VARIANTS:
            print(f"  {v.label}: {v.description}")
        return []

    await ensure_baseline_bases(rebuild=rebuild_base)

    cells: list[CellResult] = []
    for variant in H13_VARIANTS:
        print(f"\n── {variant.label} bases ──")
        for obj_name in BUILD_CASES:
            for seed in SEEDS:
                r = await run_build_cell(
                    variant, obj_name, seed, variant.label, rebuild=rebuild_base
                )
                status = "cached" if r.extra.get("cached") else f"{r.elapsed:.1f}s"
                print(f"  {variant.label}/{obj_name}-s{seed}  {status}")
                cells.append(r)
    return cells


async def _run_img2img_variant(
    step: str, variant: Variant, pipeline: Pipeline, base_set: str
) -> list[CellResult]:
    """Run all (case, seed) cells for one img2img variant on a given base set."""
    cells: list[CellResult] = []
    if pipeline == "destruction":
        cases_list: list[Any] = DESTRUCTION_CASES
    elif pipeline == "carry":
        cases_list = CARRY_CASES
    elif pipeline == "ride":
        cases_list = RIDE_CASES
    elif pipeline == "combine":
        cases_list = COMBINE_PAIRS
    else:
        return cells

    for case in cases_list:
        for seed in SEEDS:
            try:
                if pipeline == "destruction":
                    r = await run_destruction_cell(variant, case, seed, base_set, step)
                elif pipeline in ("carry", "ride"):
                    r = await run_carry_ride_cell(variant, pipeline, case, seed, base_set, step)
                elif pipeline == "combine":
                    r = await run_combine_cell(variant, case, seed, base_set, step)
                else:
                    continue
            except Exception as e:  # noqa: BLE001
                print(f"  !! {variant.label}/{case_id(pipeline, case)}-s{seed}  FAILED: {e}")
                continue
            status = "cached" if r.extra.get("cached") else f"{r.elapsed:.1f}s"
            print(f"  {variant.label}/{case_id(pipeline, case)}-s{seed}  {status}")
            cells.append(r)
    return cells


# ═══════════════════════════════════════════════════════════════════════════
# Dashboard
# ═══════════════════════════════════════════════════════════════════════════


def img_to_data_uri(path: Path) -> str:
    if not path.exists():
        return ""
    return f"data:image/png;base64,{base64.b64encode(path.read_bytes()).decode()}"


def collect_all_cells() -> list[CellResult]:
    """Scan the sprites/ and bases/ dirs for all rendered cells (dashboard aggregation)."""
    cells: list[CellResult] = []

    # Base sprites
    if BASES_DIR.exists():
        for base_set_dir in sorted(BASES_DIR.iterdir()):
            if not base_set_dir.is_dir() or base_set_dir.name.startswith("_"):
                continue
            for sprite_file in sorted(base_set_dir.glob("*.png")):
                if sprite_file.stem.endswith(".raw"):
                    continue
                m = re.match(r"^(.+)-s(\d+)$", sprite_file.stem)
                if not m:
                    continue
                obj_name, seed = m.group(1), int(m.group(2))
                raw = sprite_file.with_suffix(".raw.png")
                cells.append(
                    CellResult(
                        pipeline="build",
                        variant_label=base_set_dir.name
                        if base_set_dir.name != "baseline"
                        else "baseline",
                        bases=base_set_dir.name,
                        case=obj_name,
                        seed=seed,
                        output_path=sprite_file,
                        raw_path=raw if raw.exists() else sprite_file,
                        input_paths=[],
                        llm_output="",
                        flux_prompt="(see harness)",
                        elapsed=0.0,
                    )
                )

    # Img2img sprites
    if SPRITES_DIR.exists():
        for step_dir in sorted(SPRITES_DIR.iterdir()):
            if not step_dir.is_dir():
                continue
            for variant_dir in sorted(step_dir.iterdir()):
                if not variant_dir.is_dir():
                    continue
                # variant_dir name: "{pipeline}.{variant}@{bases}"
                m = re.match(
                    r"^(build|destruction|carry|ride|combine)\.(.+)@(.+)$", variant_dir.name
                )
                if not m:
                    continue
                pipeline_name, variant_label, bases = m.group(1), m.group(2), m.group(3)
                for sprite_file in sorted(variant_dir.glob("*.png")):
                    if sprite_file.stem.endswith(".raw"):
                        continue
                    m2 = re.match(r"^(.+)-s(\d+)$", sprite_file.stem)
                    if not m2:
                        continue
                    case_name, seed = m2.group(1), int(m2.group(2))
                    raw = sprite_file.with_suffix(".raw.png")

                    # Try to load LLM output from cache
                    llm_key_case = case_name
                    llm_data = load_llm_cache(variant_label, pipeline_name, llm_key_case)  # type: ignore[arg-type]
                    llm_text = llm_data.get("llm_output", "") if llm_data else ""

                    input_paths: list[Path] = []
                    if pipeline_name in ("carry", "ride"):
                        input_paths = [
                            BASES_DIR / "_player_ref.png",
                            base_sprite_path(bases, case_name, seed),
                        ]
                    elif pipeline_name == "destruction":
                        input_paths = [base_sprite_path(bases, case_name, seed)]
                    elif pipeline_name == "combine":
                        if "+" in case_name:
                            a, b = case_name.split("+", 1)
                            input_paths = [
                                base_sprite_path(bases, a, seed),
                                base_sprite_path(bases, b, seed),
                            ]

                    cells.append(
                        CellResult(
                            pipeline=pipeline_name,  # type: ignore[arg-type]
                            variant_label=variant_label,
                            bases=bases,
                            case=case_name,
                            seed=seed,
                            output_path=sprite_file,
                            raw_path=raw if raw.exists() else sprite_file,
                            input_paths=input_paths,
                            llm_output=llm_text,
                            flux_prompt="(in harness)",
                            elapsed=0.0,
                        )
                    )
    return cells


def generate_dashboard(cells: list[CellResult]) -> Path:
    """Write an HTML dashboard grouping cells by pipeline → case → variant → seeds.

    Each sprite cell has 3 rating inputs (fidelity/style/usability), a note
    field, and copy-to-clipboard buttons for its ID, LLM output, and FLUX prompt.
    """
    # Group: pipeline → case → (variant, bases) → {seed: cell}
    grouped: dict[str, dict[str, dict[tuple[str, str], dict[int, CellResult]]]] = {}
    for c in cells:
        grouped.setdefault(c.pipeline, {}).setdefault(c.case, {}).setdefault(
            (c.variant_label, c.bases), {}
        )[c.seed] = c

    sections_html: list[str] = []
    pipeline_order = ["build", "destruction", "carry", "ride", "combine"]
    for p in pipeline_order:
        if p not in grouped:
            continue
        case_sections: list[str] = []
        for case in sorted(grouped[p].keys()):
            variant_groups = grouped[p][case]
            variant_rows: list[str] = []
            # Pick any cell to pull reference paths from — all variants of the
            # same case share the same input refs (per base-set group).
            ref_groups: dict[str, list[Path]] = {}
            for (_vl, bases), seed_cells in variant_groups.items():
                if bases in ref_groups:
                    continue
                for cell in seed_cells.values():
                    if cell.input_paths:
                        ref_groups[bases] = cell.input_paths
                        break
            refs_html = _render_case_refs(ref_groups)

            for (variant_label, bases), seed_cells in sorted(variant_groups.items()):
                row_label = (
                    variant_label
                    if bases == "baseline" or p == "build"
                    else f"{variant_label}@{bases}"
                )
                seed_cards: list[str] = []
                for seed in SEEDS:
                    cell = seed_cells.get(seed)
                    if cell is None:
                        seed_cards.append('<div class="card empty">—</div>')
                        continue
                    seed_cards.append(_render_card(cell, row_label))
                variant_rows.append(f"""
                <div class="variant-row">
                    <div class="variant-label">{_escape(row_label)}</div>
                    <div class="seeds">{"".join(seed_cards)}</div>
                </div>""")
            case_sections.append(f"""
            <div class="case-block">
                <div class="case-header">
                    <h3>{_escape(case)}</h3>
                    {refs_html}
                </div>
                {"".join(variant_rows)}
            </div>""")
        sections_html.append(f"""
        <section class="pipeline-section" id="p-{p}">
            <h2>{p}</h2>
            {"".join(case_sections)}
        </section>""")

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Pipeline prompt sweep dashboard</title>
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: system-ui, -apple-system, sans-serif; background: #0f0f14; color: #ddd;
       padding: 1rem; margin: 0; max-width: 100%; }}
header {{ position: sticky; top: 0; background: #0f0f14; padding: 0.75rem 0; z-index: 100;
          border-bottom: 1px solid #2a2a3e; margin-bottom: 1rem; }}
header h1 {{ margin: 0 0 0.5rem 0; color: #fff; font-size: 1.2rem; }}
.toolbar {{ display: flex; gap: 0.5rem; flex-wrap: wrap; }}
.toolbar button {{
    background: #1a1a2e; color: #ddd; border: 1px solid #3a3a5e;
    padding: 0.4rem 0.8rem; border-radius: 4px; cursor: pointer; font-size: 0.85rem;
}}
.toolbar button:hover {{ background: #2a2a4e; }}
nav {{ display: flex; gap: 0.5rem; }}
nav a {{ color: #888; text-decoration: none; padding: 0.3rem 0.6rem;
         border-radius: 4px; font-size: 0.8rem; }}
nav a:hover {{ background: #1a1a2e; color: #ddd; }}
section.pipeline-section {{ margin-bottom: 2rem; }}
section.pipeline-section > h2 {{
    color: #fff; border-bottom: 2px solid #3a3a5e; padding-bottom: 0.3rem;
    font-size: 1.1rem; text-transform: uppercase; letter-spacing: 0.05em;
}}
.case-block {{ margin-bottom: 1rem; background: #16161f; padding: 0.75rem;
               border-radius: 6px; border: 1px solid #23233a; }}
.case-header {{ display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem;
                flex-wrap: wrap; }}
.case-header h3 {{ margin: 0; color: #e8e8ff; font-size: 0.95rem; }}
.case-refs {{ display: flex; align-items: center; gap: 0.5rem; }}
.case-refs .ref-group {{ display: flex; align-items: center; gap: 0.3rem;
                         background: #0f0f1a; padding: 0.25rem 0.4rem; border-radius: 4px;
                         border: 1px solid #2a2a40; }}
.case-refs .ref-group-label {{ font-size: 0.6rem; color: #666; font-family: monospace;
                               text-transform: uppercase; letter-spacing: 0.05em; }}
.case-refs .ref-img {{ width: 56px; height: 56px; border-radius: 3px; background: #fff;
                       border: 1px solid #2a2a40; object-fit: contain; }}
.variant-row {{ display: flex; align-items: flex-start; gap: 0.5rem; margin-bottom: 0.5rem; }}
.variant-label {{ flex: 0 0 180px; font-weight: 600; font-size: 0.8rem;
                  color: #a8b8e8; padding-top: 0.3rem; cursor: pointer;
                  word-break: break-word; font-family: 'Cascadia Code', monospace; }}
.variant-label:hover {{ color: #fff; }}
.seeds {{ display: flex; gap: 0.4rem; flex: 1 1 auto; flex-wrap: wrap; }}
.card {{
    background: #1a1a28; border: 1px solid #2a2a40; border-radius: 6px;
    padding: 0.35rem; width: 160px; display: flex; flex-direction: column;
    gap: 0.3rem; font-size: 0.7rem;
}}
.card.empty {{ opacity: 0.3; justify-content: center; align-items: center;
               min-height: 160px; }}
.sprite-id {{ font-family: monospace; font-size: 0.6rem; color: #666;
              word-break: break-all; cursor: pointer; }}
.sprite-id:hover {{ color: #aaa; }}
.sprite-img {{ width: 100%; aspect-ratio: 1 / 1; border-radius: 4px;
               background: #000; cursor: pointer; object-fit: contain; }}
.sprite-img.raw-hover:hover {{ background: #fff; }}
.expand-btn {{
    background: none; border: 1px solid #333; color: #888;
    padding: 0.1rem 0.3rem; border-radius: 3px; cursor: pointer; font-size: 0.65rem;
}}
.expand-btn:hover {{ color: #ddd; border-color: #555; }}
.details {{ display: none; flex-direction: column; gap: 0.25rem; }}
.details.open {{ display: flex; }}
.details .inputs {{ display: flex; gap: 0.2rem; }}
.details .inputs img {{ width: 40px; height: 40px; background: #fff; border-radius: 3px; }}
.details .llm, .details .prompt {{
    font-family: 'Cascadia Code', monospace; font-size: 0.65rem; line-height: 1.3;
    padding: 0.25rem; border-radius: 3px; cursor: pointer; word-break: break-word;
}}
.details .llm {{ background: #1f1a0f; color: #d4be7e; }}
.details .prompt {{ background: #0f0f23; color: #7ea8d4; }}
.details .llm:hover, .details .prompt:hover {{ filter: brightness(1.3); }}
.ratings {{ display: flex; gap: 0.15rem; flex-direction: column; }}
.rating-axis {{ display: flex; align-items: center; gap: 0.25rem; font-size: 0.65rem; }}
.rating-axis label {{ flex: 0 0 50px; color: #888; }}
.rating-axis .stars {{ display: flex; gap: 0.1rem; }}
.rating-axis .star {{ cursor: pointer; color: #333; font-size: 0.9rem; }}
.rating-axis .star.filled {{ color: #e8c048; }}
.rating-axis .star:hover {{ color: #ffd85a; }}
.note {{
    width: 100%; background: #0a0a14; color: #ddd; border: 1px solid #2a2a40;
    border-radius: 3px; padding: 0.2rem; font-size: 0.65rem;
    font-family: inherit; resize: vertical; min-height: 1.5em;
}}
.copied {{ color: #48e88a !important; }}
.toast {{
    position: fixed; bottom: 1rem; left: 50%; transform: translateX(-50%);
    background: #1a3a2a; color: #48e88a; padding: 0.5rem 1rem; border-radius: 4px;
    font-size: 0.85rem; opacity: 0; transition: opacity 0.2s; z-index: 1000;
    pointer-events: none;
}}
.toast.show {{ opacity: 1; }}
</style>
</head><body>
<header>
<h1>Image pipeline prompt sweep — Phase 1</h1>
<div class="toolbar">
    <button onclick="exportSummary()">Copy summary JSON</button>
    <button onclick="exportAllRatings()">Copy raw ratings JSON</button>
    <button onclick="clearRatings()">Clear all ratings (local)</button>
</div>
<nav>
    <a href="#p-build">build</a>
    <a href="#p-destruction">destruction</a>
    <a href="#p-carry">carry</a>
    <a href="#p-ride">ride</a>
    <a href="#p-combine">combine</a>
</nav>
</header>

{"".join(sections_html)}

<div id="toast" class="toast"></div>

<script>
const LS_KEY = "makeshift.pipeline.ratings.v1";
function loadRatings() {{
    try {{ return JSON.parse(localStorage.getItem(LS_KEY) || "{{}}"); }}
    catch(e) {{ return {{}}; }}
}}
function saveRatings(r) {{ localStorage.setItem(LS_KEY, JSON.stringify(r)); }}

function rateId(spriteId, axis, value) {{
    const r = loadRatings();
    if (!r[spriteId]) r[spriteId] = {{}};
    r[spriteId][axis] = value;
    saveRatings(r);
    renderStars(spriteId, axis, value);
}}
function renderStars(spriteId, axis, value) {{
    const el = document.querySelector(`[data-sprite-id="${{spriteId}}"] .rating-axis[data-axis="${{axis}}"]`);
    if (!el) return;
    el.querySelectorAll('.star').forEach((s, i) => {{
        s.classList.toggle('filled', i < value);
    }});
}}
function noteChange(spriteId, value) {{
    const r = loadRatings();
    if (!r[spriteId]) r[spriteId] = {{}};
    r[spriteId].note = value;
    saveRatings(r);
}}
function toast(msg) {{
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 1400);
}}
function copyText(text, label) {{
    navigator.clipboard.writeText(text).then(() => toast(label + ' copied'));
}}
function parseSpriteId(id) {{
    // "{{pipeline}}.{{variant}}[@{{bases}}]/{{case}}#s{{seed}}"
    const [head, rest] = id.split('/');
    const [caseName, seedPart] = rest.split('#s');
    const [pipelineVar, bases] = head.includes('@') ? head.split('@') : [head, 'baseline'];
    const [pipeline, ...variantParts] = pipelineVar.split('.');
    const variant = variantParts.join('.');
    return {{ pipeline, variant, bases, case: caseName, seed: parseInt(seedPart) }};
}}
function variantKey(id) {{
    const p = parseSpriteId(id);
    const basesTag = p.bases === 'baseline' ? '' : '@' + p.bases;
    return `${{p.pipeline}}.${{p.variant}}${{basesTag}}`;
}}
function exportSummary() {{
    const ratings = loadRatings();
    const agg = {{}};
    for (const [spriteId, r] of Object.entries(ratings)) {{
        const key = variantKey(spriteId);
        if (!agg[key]) agg[key] = {{
            fidelity_sum: 0, fidelity_n: 0,
            style_sum: 0, style_n: 0,
            usability_sum: 0, usability_n: 0,
            notes: []
        }};
        for (const axis of ['fidelity', 'style', 'usability']) {{
            if (typeof r[axis] === 'number') {{
                agg[key][axis + '_sum'] += r[axis];
                agg[key][axis + '_n'] += 1;
            }}
        }}
        if (r.note && r.note.trim()) {{
            agg[key].notes.push(`${{spriteId}}: ${{r.note.trim()}}`);
        }}
    }}
    const out = {{}};
    for (const [key, v] of Object.entries(agg)) {{
        const fid = v.fidelity_n ? v.fidelity_sum / v.fidelity_n : null;
        const sty = v.style_n ? v.style_sum / v.style_n : null;
        const usa = v.usability_n ? v.usability_sum / v.usability_n : null;
        const means = [fid, sty, usa].filter(x => x !== null);
        out[key] = {{
            fidelity: fid ? Math.round(fid * 100) / 100 : null,
            style: sty ? Math.round(sty * 100) / 100 : null,
            usability: usa ? Math.round(usa * 100) / 100 : null,
            mean: means.length ? Math.round((means.reduce((a,b)=>a+b,0)/means.length) * 100) / 100 : null,
            n_rated: Math.max(v.fidelity_n, v.style_n, v.usability_n),
            notes: v.notes
        }};
    }}
    copyText(JSON.stringify(out, null, 2), 'Summary JSON');
}}
function exportAllRatings() {{
    copyText(JSON.stringify(loadRatings(), null, 2), 'Raw ratings JSON');
}}
function clearRatings() {{
    if (confirm('Clear all ratings from localStorage?')) {{
        localStorage.removeItem(LS_KEY);
        document.querySelectorAll('.star.filled').forEach(s => s.classList.remove('filled'));
        document.querySelectorAll('.note').forEach(n => n.value = '');
        toast('Ratings cleared');
    }}
}}
function toggleDetails(btn) {{
    btn.parentElement.querySelector('.details').classList.toggle('open');
}}
// Initial render of any saved ratings
document.addEventListener('DOMContentLoaded', () => {{
    const ratings = loadRatings();
    for (const [spriteId, r] of Object.entries(ratings)) {{
        for (const axis of ['fidelity', 'style', 'usability']) {{
            if (typeof r[axis] === 'number') renderStars(spriteId, axis, r[axis]);
        }}
        if (r.note) {{
            const n = document.querySelector(`[data-sprite-id="${{spriteId}}"] .note`);
            if (n) n.value = r.note;
        }}
    }}
}});
</script>
</body></html>"""

    DASHBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    DASHBOARD_PATH.write_text(html, encoding="utf-8")
    return DASHBOARD_PATH


def _render_card(cell: CellResult, variant_label: str) -> str:
    sprite_id = cell.sprite_id
    sprite_uri = img_to_data_uri(cell.output_path)
    raw_uri = img_to_data_uri(cell.raw_path) if cell.raw_path != cell.output_path else sprite_uri
    input_imgs = "".join(
        f'<img src="{img_to_data_uri(p)}" title="{_escape(p.name)}" />' for p in cell.input_paths
    )
    llm = _escape(cell.llm_output) if cell.llm_output else "(none)"
    prompt = _escape(cell.flux_prompt)
    rating_axes = ""
    for axis in ("fidelity", "style", "usability"):
        stars = "".join(
            f"<span class=\"star\" onclick=\"rateId('{sprite_id}','{axis}',{i})\">★</span>"
            for i in range(1, 6)
        )
        rating_axes += (
            f'<div class="rating-axis" data-axis="{axis}">'
            f'<label>{axis[:3]}</label><div class="stars">{stars}</div></div>'
        )

    return f"""
<div class="card" data-sprite-id="{sprite_id}">
    <div class="sprite-id" onclick="copyText('{sprite_id}', 'ID')" title="Click to copy">{_escape(f"s{cell.seed}")}</div>
    <img class="sprite-img" src="{sprite_uri}" onclick="this.src = this.src === '{sprite_uri}' ? '{raw_uri}' : '{sprite_uri}'" title="Click to toggle raw" />
    <button class="expand-btn" onclick="toggleDetails(this)">details</button>
    <div class="details">
        <div class="inputs">{input_imgs}</div>
        <div class="llm" onclick="copyText(this.textContent, 'LLM text')" title="click to copy">{llm}</div>
        <div class="prompt" onclick="copyText(this.textContent, 'FLUX prompt')" title="click to copy">{prompt}</div>
    </div>
    <div class="ratings">{rating_axes}</div>
    <textarea class="note" placeholder="note..." oninput="noteChange('{sprite_id}', this.value)"></textarea>
</div>"""


def _render_case_refs(ref_groups: dict[str, list[Path]]) -> str:
    """Render input-reference thumbnails for a case, grouped by base-set.

    `ref_groups` maps base-set label (e.g. "baseline", "H12.orient-right")
    to the list of reference image paths for that base set. For most cases
    there's only one group; when a build-level hypothesis (H12, H10) has
    cascaded, we show one group per base set so you can see how the refs
    differ.
    """
    if not ref_groups:
        return ""
    parts: list[str] = ['<div class="case-refs">']
    show_label = len(ref_groups) > 1
    for base_set, paths in sorted(ref_groups.items()):
        imgs = "".join(
            f'<img class="ref-img" src="{img_to_data_uri(p)}" title="{_escape(p.name)}" />'
            for p in paths
            if p.exists()
        )
        if not imgs:
            continue
        label_html = (
            f'<span class="ref-group-label">{_escape(base_set)}</span>' if show_label else ""
        )
        parts.append(f'<div class="ref-group">{label_html}{imgs}</div>')
    parts.append("</div>")
    return "".join(parts)


def _escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# ═══════════════════════════════════════════════════════════════════════════
# Main / CLI
# ═══════════════════════════════════════════════════════════════════════════


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--step",
        choices=["1.1", "1.2", "1.3", "1.4"],
        help="Which Phase 1 step to run",
    )
    parser.add_argument(
        "--only",
        choices=["build", "destruction", "carry", "ride", "combine"],
        help="Restrict to one pipeline (mainly for dry-run inspection)",
    )
    parser.add_argument(
        "--rebuild-base", action="store_true", help="Force regeneration of base sprites"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print what would run, skip FLUX calls"
    )
    parser.add_argument(
        "--dashboard-only",
        action="store_true",
        help="Skip generation, just regenerate the dashboard from existing files",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.dashboard_only:
        cells = collect_all_cells()
        path = generate_dashboard(cells)
        print(f"\nDashboard regenerated: {path.resolve()} ({len(cells)} cells)")
        return

    if not args.step:
        print(
            "ERROR: --step is required (1.1, 1.2, or 1.3). Use --dashboard-only to regenerate HTML."
        )
        sys.exit(2)

    from app.logging_setup import setup_logging

    setup_logging()

    t0 = time.monotonic()
    if args.step == "1.1":
        await run_step_1_1(
            only_pipeline=args.only, rebuild_base=args.rebuild_base, dry_run=args.dry_run
        )
    elif args.step == "1.2":
        await run_step_1_2(
            only_pipeline=args.only, rebuild_base=args.rebuild_base, dry_run=args.dry_run
        )
    elif args.step == "1.3":
        await run_step_1_3(
            only_pipeline=args.only, rebuild_base=args.rebuild_base, dry_run=args.dry_run
        )
    elif args.step == "1.4":
        await run_step_1_4(
            only_pipeline=args.only, rebuild_base=args.rebuild_base, dry_run=args.dry_run
        )

    if not args.dry_run:
        cells = collect_all_cells()
        path = generate_dashboard(cells)
        print(f"\n{'═' * 70}")
        print(f"Step {args.step} done in {time.monotonic() - t0:.0f}s")
        print(f"Dashboard:  {path.resolve()}")
        print(f"Cells:      {len(cells)}")


if __name__ == "__main__":
    asyncio.run(main())
