#!/usr/bin/env python3
"""Benchmark rembg background removal models — CPU vs GPU, multiple models.

Generates an HTML dashboard showing original images, results per model,
alpha channel visualization (red = transparent), and timing data.

Usage:
    uv run python -m scripts.benchmark_bg_removal [--images-dir benchmark_images]
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image
from rembg import new_session, remove

MODELS = [
    "birefnet-general",
    "birefnet-general-lite",
    "isnet-general-use",
    "u2net",
    "u2netp",
    "silueta",
    "bria-rmbg",
]

# Which providers to test for each model
PROVIDERS_GPU = ["CUDAExecutionProvider", "CPUExecutionProvider"]
PROVIDERS_CPU = ["CPUExecutionProvider"]


def image_to_data_uri(img: Image.Image, fmt: str = "PNG") -> str:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/{fmt.lower()};base64,{b64}"


def alpha_to_red(img: Image.Image) -> Image.Image:
    """Visualize alpha: opaque pixels shown normally, transparent pixels shown as red."""
    arr = np.array(img.convert("RGBA"), dtype=np.uint8).copy()
    alpha = arr[:, :, 3].astype(np.float32) / 255.0

    # Blend toward red based on transparency
    red_layer = np.zeros_like(arr[:, :, :3], dtype=np.float32)
    red_layer[:, :, 0] = 255.0  # red channel

    rgb = arr[:, :, :3].astype(np.float32)
    transparency = 1.0 - alpha
    blended = rgb * alpha[:, :, np.newaxis] + red_layer * transparency[:, :, np.newaxis]

    result = np.zeros_like(arr)
    result[:, :, :3] = blended.astype(np.uint8)
    result[:, :, 3] = 255  # fully opaque output
    return Image.fromarray(result)


def benchmark_model(
    model_name: str,
    image_paths: list[Path],
    use_gpu: bool,
) -> list[dict]:
    """Run a single model on all images. Returns list of result dicts."""
    providers = PROVIDERS_GPU if use_gpu else PROVIDERS_CPU
    provider_label = "GPU" if use_gpu else "CPU"

    print(f"\n  Loading {model_name} ({provider_label})...", flush=True)
    t_load = time.perf_counter()
    try:
        session = new_session(model_name, providers=providers)
    except Exception as e:
        print(f"  FAILED to load: {e}")
        return [
            {
                "model": model_name,
                "provider": provider_label,
                "image": p.stem,
                "time_ms": -1,
                "error": str(e),
            }
            for p in image_paths
        ]
    load_time = time.perf_counter() - t_load
    print(f"  Loaded in {load_time:.2f}s", flush=True)

    # Warmup run
    warmup_bytes = image_paths[0].read_bytes()
    remove(warmup_bytes, session=session)

    results = []
    for path in image_paths:
        image_bytes = path.read_bytes()
        t0 = time.perf_counter()
        try:
            output_bytes = remove(image_bytes, session=session)
            elapsed_ms = (time.perf_counter() - t0) * 1000

            output_img = Image.open(io.BytesIO(output_bytes)).convert("RGBA")
            alpha_vis = alpha_to_red(output_img)

            results.append({
                "model": model_name,
                "provider": provider_label,
                "image": path.stem,
                "time_ms": round(elapsed_ms, 1),
                "output_data_uri": image_to_data_uri(output_img),
                "alpha_data_uri": image_to_data_uri(alpha_vis),
                "error": None,
            })
            print(f"    {path.name}: {elapsed_ms:.0f}ms", flush=True)
        except Exception as e:
            print(f"    {path.name}: ERROR - {e}", flush=True)
            results.append({
                "model": model_name,
                "provider": provider_label,
                "image": path.stem,
                "time_ms": -1,
                "error": str(e),
            })
    return results


def build_html(
    image_paths: list[Path],
    all_results: list[dict],
    output_path: Path,
) -> None:
    """Build an HTML dashboard from benchmark results."""

    # Collect original images as data URIs
    originals = {}
    for p in image_paths:
        img = Image.open(p).convert("RGBA")
        originals[p.stem] = image_to_data_uri(img)

    # Group results by (model, provider)
    model_providers = []
    seen = set()
    for r in all_results:
        key = (r["model"], r["provider"])
        if key not in seen:
            seen.add(key)
            model_providers.append(key)

    # Build timing summary
    timing_summary = {}
    for model, provider in model_providers:
        times = [
            r["time_ms"]
            for r in all_results
            if r["model"] == model and r["provider"] == provider and r["time_ms"] > 0
        ]
        if times:
            timing_summary[(model, provider)] = {
                "mean": round(sum(times) / len(times), 1),
                "min": round(min(times), 1),
                "max": round(max(times), 1),
            }

    image_names = [p.stem for p in image_paths]

    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>BG Removal Benchmark</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, -apple-system, sans-serif; background: #1a1a2e; color: #e0e0e0; padding: 20px; }
  h1 { text-align: center; margin-bottom: 10px; color: #fff; }
  .subtitle { text-align: center; color: #888; margin-bottom: 30px; }

  /* Timing summary table */
  .timing-table { margin: 0 auto 30px; border-collapse: collapse; }
  .timing-table th, .timing-table td { padding: 8px 16px; border: 1px solid #333; text-align: center; }
  .timing-table th { background: #2a2a4a; color: #aaa; font-size: 13px; text-transform: uppercase; }
  .timing-table td { font-size: 14px; }
  .timing-table tr:hover td { background: #2a2a4a; }
  .fast { color: #4ade80; font-weight: bold; }
  .medium-speed { color: #fbbf24; }
  .slow { color: #f87171; }

  /* Controls */
  .controls { text-align: center; margin-bottom: 20px; }
  .controls label { margin: 0 10px; cursor: pointer; }
  .controls input[type="radio"] { margin-right: 4px; }

  /* Grid */
  .grid { display: grid; gap: 12px; padding: 10px; }
  .grid-header { font-weight: bold; text-align: center; font-size: 13px; color: #aaa;
                  display: flex; align-items: center; justify-content: center;
                  background: #2a2a4a; border-radius: 6px; padding: 8px 4px; }
  .cell { background: #16213e; border-radius: 6px; padding: 6px; text-align: center; position: relative; }
  .cell img { width: 100%; height: auto; border-radius: 4px; image-rendering: pixelated; }
  .cell .time { font-size: 11px; color: #888; margin-top: 4px; }
  .cell .error { font-size: 11px; color: #f87171; margin-top: 4px; }
  .cell .name { font-size: 11px; color: #ccc; margin-bottom: 4px; }

  /* Checkerboard for transparency */
  .checker {
    background-image: repeating-conic-gradient(#333 0% 25%, #222 0% 50%);
    background-size: 16px 16px;
    border-radius: 4px;
  }
</style>
</head>
<body>
<h1>Background Removal Benchmark</h1>
<p class="subtitle">rembg models &mdash; CPU vs GPU</p>

<table class="timing-table">
<tr><th>Model</th><th>Provider</th><th>Mean (ms)</th><th>Min</th><th>Max</th></tr>
"""
    # Sort timing summary by mean time
    sorted_timing = sorted(timing_summary.items(), key=lambda x: x[1]["mean"])
    fastest_mean = sorted_timing[0][1]["mean"] if sorted_timing else 999999

    for (model, provider), t in sorted_timing:
        mean = t["mean"]
        if mean <= fastest_mean * 1.5:
            cls = "fast"
        elif mean <= fastest_mean * 3:
            cls = "medium-speed"
        else:
            cls = "slow"
        html += (
            f'<tr><td>{model}</td><td>{provider}</td>'
            f'<td class="{cls}">{mean}</td><td>{t["min"]}</td><td>{t["max"]}</td></tr>\n'
        )

    html += """</table>

<div class="controls">
  <strong>View:</strong>
  <label><input type="radio" name="view" value="result" checked onchange="toggleView(this.value)"> Result</label>
  <label><input type="radio" name="view" value="alpha" onchange="toggleView(this.value)"> Alpha (red=transparent)</label>
</div>

<div class="grid" id="grid">
"""

    n_cols = len(model_providers) + 1  # +1 for original column
    html += f'<style>.grid {{ grid-template-columns: repeat({n_cols}, 1fr); }}</style>\n'

    # Header row
    html += '<div class="grid-header">Original</div>\n'
    for model, provider in model_providers:
        html += f'<div class="grid-header">{model}<br><small>({provider})</small></div>\n'

    # Data rows
    for img_name in image_names:
        # Original
        display_name = img_name.split("_", 1)[1].replace("_", " ").title() if "_" in img_name else img_name
        html += f'<div class="cell"><div class="name">{display_name}</div>'
        html += f'<div class="checker"><img src="{originals[img_name]}"></div></div>\n'

        # Each model result
        for model, provider in model_providers:
            r = next(
                (x for x in all_results if x["model"] == model and x["provider"] == provider and x["image"] == img_name),
                None,
            )
            if r and r["error"]:
                html += f'<div class="cell"><div class="error">Error: {r["error"][:40]}</div></div>\n'
            elif r:
                html += f'<div class="cell">'
                html += f'<div class="checker"><img class="result-img" src="{r["output_data_uri"]}" data-alpha="{r["alpha_data_uri"]}" data-result="{r["output_data_uri"]}"></div>'
                html += f'<div class="time">{r["time_ms"]}ms</div></div>\n'
            else:
                html += '<div class="cell"><div class="error">No data</div></div>\n'

    html += """</div>

<script>
function toggleView(mode) {
  document.querySelectorAll('.result-img').forEach(img => {
    img.src = mode === 'alpha' ? img.dataset.alpha : img.dataset.result;
  });
}
</script>
</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")
    print(f"\nDashboard saved to: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark rembg bg removal models")
    parser.add_argument(
        "--images-dir",
        default="benchmark_images",
        help="Directory containing test images (default: benchmark_images)",
    )
    parser.add_argument(
        "--output",
        default="benchmark_results.html",
        help="Output HTML file (default: benchmark_results.html)",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=MODELS,
        help=f"Models to test (default: {MODELS})",
    )
    parser.add_argument(
        "--cpu-only",
        action="store_true",
        help="Skip GPU tests",
    )
    parser.add_argument(
        "--gpu-only",
        action="store_true",
        help="Skip CPU tests",
    )
    args = parser.parse_args()

    images_dir = Path(args.images_dir)
    if not images_dir.exists():
        print(f"Error: {images_dir} not found")
        return

    image_paths = sorted(images_dir.glob("*.png"))
    if not image_paths:
        print(f"Error: no PNG files in {images_dir}")
        return

    print(f"Found {len(image_paths)} test images")
    print(f"Testing models: {args.models}")

    all_results: list[dict] = []

    for model_name in args.models:
        if not args.cpu_only:
            print(f"\n{'='*60}")
            print(f"Model: {model_name} (GPU)")
            print(f"{'='*60}")
            results = benchmark_model(model_name, image_paths, use_gpu=True)
            all_results.extend(results)

        if not args.gpu_only:
            print(f"\n{'='*60}")
            print(f"Model: {model_name} (CPU)")
            print(f"{'='*60}")
            results = benchmark_model(model_name, image_paths, use_gpu=False)
            all_results.extend(results)

    # Save raw data as JSON too
    json_path = Path(args.output).with_suffix(".json")
    json_safe = [
        {k: v for k, v in r.items() if k not in ("output_data_uri", "alpha_data_uri")}
        for r in all_results
    ]
    json_path.write_text(json.dumps(json_safe, indent=2))
    print(f"\nRaw timing data saved to: {json_path}")

    build_html(image_paths, all_results, Path(args.output))


if __name__ == "__main__":
    main()
