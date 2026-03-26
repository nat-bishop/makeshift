#!/usr/bin/env python3
"""Round 4: Single static sprites across fal.ai models.

No animation — just test which models produce the best paper-cutout art style
with the same prompt. Also includes Gemini Flash direct for comparison.

Usage:
    cd backend && uv run python -m experiments.spritesheet_round4
"""

from __future__ import annotations

import asyncio
import io
import sys
import time
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from PIL import Image

OUTPUT_DIR = SCRIPT_DIR / "output" / "round4"
FAL_CONCURRENCY = 2
GEMINI_CONCURRENCY = 2


@dataclass
class Model:
    id: str
    name: str
    endpoint: str
    provider: str  # "fal" or "gemini"
    cost: str
    extra_args: dict | None = None


@dataclass
class Subject:
    id: str
    name: str
    prompt: str


@dataclass
class Result:
    model_id: str
    model_name: str
    subject_id: str
    subject_name: str
    path: str | None = None
    elapsed: float = 0.0
    error: str | None = None
    cost: str = ""


MODELS = [
    Model("flux-schnell", "Flux Schnell", "fal-ai/flux/schnell", "fal", "$0.003/MP",
          {"num_images": 1, "image_size": {"width": 1024, "height": 1024}}),
    Model("flux2-pro", "Flux 2 Pro", "fal-ai/flux-2-pro", "fal", "$0.03+/img",
          {"num_images": 1, "image_size": {"width": 1024, "height": 1024}}),
    Model("seedream", "Seedream v4", "fal-ai/bytedance/seedream/v4/text-to-image", "fal", "$0.03/img",
          {"num_images": 1, "image_size": {"width": 1024, "height": 1024}}),
    Model("flux-pro", "Flux Pro v1.1 (current)", "fal-ai/flux-pro/v1.1", "fal", "$0.04/MP",
          {"num_images": 1, "width": 1024, "height": 1024}),
    Model("flux2-flex", "Flux 2 Flex", "fal-ai/flux-2-flex", "fal", "$0.05/MP",
          {"num_images": 1, "image_size": {"width": 1024, "height": 1024}}),
    Model("nano-banana-2", "Nano Banana 2", "fal-ai/nano-banana-2", "fal", "$0.08/img @1K",
          {"resolution": "1K", "aspect_ratio": "1:1", "output_format": "png"}),
    Model("nano-banana-pro", "Nano Banana Pro", "fal-ai/nano-banana-pro", "fal", "$0.15/img",
          {"resolution": "1K", "aspect_ratio": "1:1", "output_format": "png"}),
    Model("recraft", "Recraft V4 Pro", "fal-ai/recraft/v4/pro/text-to-image", "fal", "$0.25/img",
          {"image_size": {"width": 1024, "height": 1024}}),
    Model("gemini-flash", "Gemini Flash (direct)", "gemini-3.1-flash-image-preview", "gemini", "~$0.07/img"),
]

BG = "#1a1a1a"

# Same prompt style as the gemini-text cow from round 1 that the user loved
def make_prompt(subject: Subject) -> str:
    return subject.prompt

SUBJECTS = [
    Subject("cow", "Green Cow",
            f"mixed media collage style paper cutout, side view, flat lighting, clean edges, "
            f"medium cow made of fur, green with white accents, "
            f"single centered object, solid {BG} background, no text"),
    Subject("dragon", "Fire Dragon",
            f"mixed media collage style paper cutout, side view, flat lighting, clean edges, "
            f"medium dragon made of scales, red with orange accents, "
            f"single centered object, solid {BG} background, no text"),
    Subject("slime", "Blue Slime",
            f"mixed media collage style paper cutout, side view, flat lighting, clean edges, "
            f"medium slime blob made of translucent gel, blue with cyan accents, "
            f"single centered object, solid {BG} background, no text"),
    Subject("knight", "Knight",
            f"mixed media collage style paper cutout, side view, flat lighting, clean edges, "
            f"small knight in armor made of metal, silver with red cape accents, "
            f"single centered object, solid {BG} background, no text"),
]


# ── Generators ──────────────────────────────────────────────────────────


async def generate_fal(
    model: Model, subject: Subject, sem: asyncio.Semaphore,
) -> Result:
    import fal_client
    import httpx

    prompt = make_prompt(subject)
    result = Result(
        model_id=model.id, model_name=model.name,
        subject_id=subject.id, subject_name=subject.name, cost=model.cost,
    )
    async with sem:
        t0 = time.monotonic()
        try:
            args = {"prompt": prompt}
            if model.extra_args:
                args.update(model.extra_args)

            tag = f"{model.id} x {subject.id}"
            print(f"  [{tag}] -> {model.endpoint} ...")

            handler = await fal_client.submit_async(model.endpoint, arguments=args)
            fal_result = await handler.get()

            # Extract image URL
            images = fal_result.get("images") or []
            if not images:
                img_data = fal_result.get("image")
                if img_data:
                    images = [img_data]
            if not images:
                raise ValueError(f"No images in response: {list(fal_result.keys())}")

            image_url = images[0]["url"] if isinstance(images[0], dict) else images[0]

            async with httpx.AsyncClient() as client:
                resp = await client.get(image_url)
                resp.raise_for_status()
                img_bytes = resp.content

            out_path = OUTPUT_DIR / f"{model.id}_{subject.id}.png"
            if img_bytes[:4] != b"\x89PNG":
                img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                img_bytes = buf.getvalue()
            out_path.write_bytes(img_bytes)

            result.path = str(out_path)
            result.elapsed = time.monotonic() - t0
            print(f"  [{tag}] done ({result.elapsed:.1f}s)")

        except Exception as e:
            result.error = f"{type(e).__name__}: {e}"
            result.elapsed = time.monotonic() - t0
            print(f"  [{tag}] FAILED: {result.error}")
    return result


async def generate_gemini(
    model: Model, subject: Subject, sem: asyncio.Semaphore,
) -> Result:
    prompt = make_prompt(subject)
    result = Result(
        model_id=model.id, model_name=model.name,
        subject_id=subject.id, subject_name=subject.name, cost=model.cost,
    )
    async with sem:
        t0 = time.monotonic()
        try:
            tag = f"{model.id} x {subject.id}"
            print(f"  [{tag}] -> {model.endpoint} ...")

            img_bytes = await asyncio.to_thread(_gemini_sync, model.endpoint, prompt)

            out_path = OUTPUT_DIR / f"{model.id}_{subject.id}.png"
            if img_bytes[:4] != b"\x89PNG":
                img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                img_bytes = buf.getvalue()
            out_path.write_bytes(img_bytes)

            result.path = str(out_path)
            result.elapsed = time.monotonic() - t0
            print(f"  [{tag}] done ({result.elapsed:.1f}s)")

        except Exception as e:
            result.error = f"{type(e).__name__}: {e}"
            result.elapsed = time.monotonic() - t0
            print(f"  [{tag}] FAILED: {result.error}")
    return result


def _gemini_sync(endpoint: str, prompt: str) -> bytes:
    from google import genai
    from google.genai import types

    client = genai.Client()
    response = client.models.generate_content(
        model=endpoint,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(image_size="1K", aspect_ratio="1:1"),
        ),
    )
    if response.parts is None:
        reason = "unknown"
        if response.candidates and response.candidates[0].finish_reason:
            reason = str(response.candidates[0].finish_reason)
        raise ValueError(f"Blocked: {reason}")
    for part in response.parts:
        if part.inline_data is not None:
            return part.inline_data.data
    raise ValueError("No image in response")


# ── Report ──────────────────────────────────────────────────────────────


def generate_report(results: list[Result]) -> str:
    model_ids = [m.id for m in MODELS]
    subject_ids = [s.id for s in SUBJECTS]
    models_map = {m.id: m for m in MODELS}
    subjects_map = {s.id: s for s in SUBJECTS}

    ok = [r for r in results if not r.error]
    total_time = sum(r.elapsed for r in results)

    headers = "".join(
        f'<th>{models_map[m].name}<br><span style="color:#888;font-weight:normal">'
        f'{models_map[m].cost}</span></th>'
        for m in model_ids
    )

    rows = []
    for sid in subject_ids:
        cells = []
        for mid in model_ids:
            r = next((r for r in results if r.model_id == mid and r.subject_id == sid), None)
            if r and r.path and not r.error:
                fname = Path(r.path).name
                cells.append(
                    f'<td class="cell">'
                    f'<a href="{fname}" target="_blank">'
                    f'<img src="{fname}" alt="{mid} {sid}"></a>'
                    f'<div class="meta">{r.elapsed:.1f}s</div></td>'
                )
            elif r and r.error:
                short = r.error[:100].replace("<", "&lt;")
                cells.append(
                    f'<td class="cell error"><div class="error-msg">FAILED<br>'
                    f'<small>{short}</small></div></td>'
                )
            else:
                cells.append('<td class="cell">-</td>')
        rows.append(
            f'<tr><th class="subject">{subjects_map[sid].name}</th>{"".join(cells)}</tr>'
        )

    prompt_example = SUBJECTS[0].prompt.replace("<", "&lt;")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Round 4: Model Comparison (Static Sprites)</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: system-ui, sans-serif; background: #111; color: #ddd; padding: 24px; }}
  h1 {{ margin-bottom: 4px; }}
  .summary {{ color: #999; margin-bottom: 8px; }}
  .prompt-info {{ background: #1a1a1a; border: 1px solid #333; border-radius: 6px;
                  padding: 12px; margin: 12px 0 24px; font-size: 12px; }}
  .prompt-info code {{ color: #8f8; }}
  table {{ border-collapse: collapse; margin: 16px 0; }}
  th, td {{ border: 1px solid #333; padding: 8px; text-align: center; vertical-align: top; }}
  th {{ background: #1a1a1a; font-size: 11px; max-width: 130px; }}
  .subject {{ text-align: right; padding-right: 16px; font-size: 15px; font-weight: 600; }}
  .cell {{ background: #0a0a0a; }}
  .cell img {{ max-width: 200px; max-height: 200px; display: block; margin: 4px auto;
               border: 1px solid #222; }}
  .cell .meta {{ font-size: 11px; color: #666; margin-top: 4px; }}
  .cell.error {{ background: #1a0808; }}
  .error-msg {{ color: #c44; font-size: 11px; padding: 20px 4px; }}
</style>
</head>
<body>
<h1>Round 4: fal.ai Model Comparison (Static Sprites)</h1>
<div class="summary">
  {len(ok)}/{len(results)} succeeded | {total_time:.0f}s wall time |
  Same prompt across all models
</div>
<div class="prompt-info">
  <strong>Prompt (cow example):</strong><br>
  <code>{prompt_example}</code>
</div>

<table>
  <tr><th>Subject</th>{headers}</tr>
  {"".join(rows)}
</table>
</body>
</html>"""


# ── Main ────────────────────────────────────────────────────────────────


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    n = len(MODELS) * len(SUBJECTS)
    print(f"Round 4: Static Sprite Model Comparison")
    print(f"  {len(MODELS)} models x {len(SUBJECTS)} subjects = {n} generations")
    print(f"  Output: {OUTPUT_DIR}\n")

    fal_sem = asyncio.Semaphore(FAL_CONCURRENCY)
    gemini_sem = asyncio.Semaphore(GEMINI_CONCURRENCY)

    tasks = []
    for model in MODELS:
        for subject in SUBJECTS:
            if model.provider == "fal":
                tasks.append(generate_fal(model, subject, fal_sem))
            else:
                tasks.append(generate_gemini(model, subject, gemini_sem))

    print(f"Running {len(tasks)} generations...\n")
    t0 = time.monotonic()
    results = list(await asyncio.gather(*tasks))
    wall = time.monotonic() - t0

    report = generate_report(results)
    report_path = OUTPUT_DIR / "report.html"
    report_path.write_text(report, encoding="utf-8")

    ok = [r for r in results if not r.error]
    failed = [r for r in results if r.error]
    print(f"\n{'=' * 60}")
    print(f"DONE in {wall:.0f}s: {len(ok)} succeeded, {len(failed)} failed")
    print(f"Report: {report_path}")
    if failed:
        print("\nFailures:")
        for r in failed:
            print(f"  {r.model_id} x {r.subject_id}: {r.error}")


if __name__ == "__main__":
    asyncio.run(main())
