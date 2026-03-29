#!/usr/bin/env python3
"""Benchmark BiRefNet via transformers (in-process GPU) vs rembg models.

Tests BiRefNet through HuggingFace transformers with native CUDA,
compared against the best rembg models from the previous benchmark.

Usage:
    uv run python -m scripts.benchmark_birefnet_transformers [--images-dir benchmark_images]
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image


def image_to_data_uri(img: Image.Image, fmt: str = "PNG") -> str:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/{fmt.lower()};base64,{b64}"


def alpha_to_red(img: Image.Image) -> Image.Image:
    """Visualize alpha: opaque pixels normal, transparent pixels red."""
    arr = np.array(img.convert("RGBA"), dtype=np.uint8).copy()
    alpha = arr[:, :, 3].astype(np.float32) / 255.0
    red_layer = np.zeros_like(arr[:, :, :3], dtype=np.float32)
    red_layer[:, :, 0] = 255.0
    rgb = arr[:, :, :3].astype(np.float32)
    transparency = 1.0 - alpha
    blended = rgb * alpha[:, :, np.newaxis] + red_layer * transparency[:, :, np.newaxis]
    result = np.zeros_like(arr)
    result[:, :, :3] = blended.astype(np.uint8)
    result[:, :, 3] = 255
    return Image.fromarray(result)


class BiRefNetTransformers:
    """BiRefNet via HuggingFace transformers pipeline — native CUDA."""

    def __init__(self, model_name: str = "ZhengPeng7/BiRefNet", device: str = "cuda"):
        from transformers import AutoModelForImageSegmentation

        print(f"  Loading {model_name} on {device}...", flush=True)
        t0 = time.perf_counter()
        self.model = AutoModelForImageSegmentation.from_pretrained(
            model_name, trust_remote_code=True, torch_dtype=torch.float32
        )
        self.device = device
        self.model.to(device)
        self.model.eval()

        from torchvision import transforms

        self.transform = transforms.Compose([
            transforms.Resize((1024, 1024)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
        self.load_time = time.perf_counter() - t0
        print(f"  Loaded in {self.load_time:.2f}s", flush=True)

    @torch.no_grad()
    def remove(self, image_bytes: bytes) -> Image.Image:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        orig_size = img.size

        input_tensor = self.transform(img).unsqueeze(0).to(self.device)
        preds = self.model(input_tensor)[-1].sigmoid().cpu()
        mask = preds[0].squeeze()

        # Resize mask back to original size
        mask_pil = Image.fromarray((mask.numpy() * 255).astype(np.uint8), mode="L")
        mask_pil = mask_pil.resize(orig_size, Image.Resampling.LANCZOS)

        # Apply mask
        result = img.convert("RGBA")
        result.putalpha(mask_pil)
        return result


class BiRefNetTransformersLite(BiRefNetTransformers):
    """BiRefNet-lite (smaller/faster variant)."""

    def __init__(self, device: str = "cuda"):
        super().__init__("ZhengPeng7/BiRefNet_lite", device)


class BiRefNetTransformersHalf(BiRefNetTransformers):
    """BiRefNet with float16 for faster inference."""

    def __init__(self, model_name: str = "ZhengPeng7/BiRefNet", device: str = "cuda"):
        from transformers import AutoModelForImageSegmentation

        print(f"  Loading {model_name} (fp16) on {device}...", flush=True)
        t0 = time.perf_counter()
        self.model = AutoModelForImageSegmentation.from_pretrained(
            model_name, trust_remote_code=True
        )
        self.device = device
        self.model.to(device).half()
        self.model.eval()

        from torchvision import transforms

        self.transform = transforms.Compose([
            transforms.Resize((1024, 1024)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
        self.load_time = time.perf_counter() - t0
        print(f"  Loaded in {self.load_time:.2f}s", flush=True)

    @torch.no_grad()
    def remove(self, image_bytes: bytes) -> Image.Image:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        orig_size = img.size

        input_tensor = self.transform(img).unsqueeze(0).to(self.device).half()
        preds = self.model(input_tensor)[-1].sigmoid().cpu().float()
        mask = preds[0].squeeze()

        mask_pil = Image.fromarray((mask.numpy() * 255).astype(np.uint8), mode="L")
        mask_pil = mask_pil.resize(orig_size, Image.Resampling.LANCZOS)

        result = img.convert("RGBA")
        result.putalpha(mask_pil)
        return result


def benchmark_model(
    name: str,
    model: object,
    image_paths: list[Path],
) -> list[dict]:
    """Run a model on all images. Returns list of result dicts."""
    # Warmup
    warmup_bytes = image_paths[0].read_bytes()
    model.remove(warmup_bytes)  # type: ignore[union-attr]

    results = []
    for path in image_paths:
        image_bytes = path.read_bytes()
        t0 = time.perf_counter()
        try:
            output_img = model.remove(image_bytes)  # type: ignore[union-attr]
            elapsed_ms = (time.perf_counter() - t0) * 1000
            alpha_vis = alpha_to_red(output_img)

            results.append({
                "model": name,
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
                "model": name,
                "image": path.stem,
                "time_ms": -1,
                "error": str(e),
            })
    return results


def benchmark_rembg(
    model_name: str,
    image_paths: list[Path],
) -> list[dict]:
    """Run rembg model for comparison."""
    from rembg import new_session, remove

    print(f"\n  Loading rembg/{model_name} (CPU)...", flush=True)
    t0 = time.perf_counter()
    session = new_session(model_name, providers=["CPUExecutionProvider"])
    print(f"  Loaded in {time.perf_counter() - t0:.2f}s", flush=True)

    # Warmup
    remove(image_paths[0].read_bytes(), session=session)

    results = []
    for path in image_paths:
        image_bytes = path.read_bytes()
        t0 = time.perf_counter()
        output_bytes = remove(image_bytes, session=session)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        output_img = Image.open(io.BytesIO(output_bytes)).convert("RGBA")
        alpha_vis = alpha_to_red(output_img)

        results.append({
            "model": f"rembg/{model_name}",
            "image": path.stem,
            "time_ms": round(elapsed_ms, 1),
            "output_data_uri": image_to_data_uri(output_img),
            "alpha_data_uri": image_to_data_uri(alpha_vis),
            "error": None,
        })
        print(f"    {path.name}: {elapsed_ms:.0f}ms", flush=True)
    return results


def build_html(
    image_paths: list[Path],
    all_results: list[dict],
    output_path: Path,
) -> None:
    originals = {}
    for p in image_paths:
        img = Image.open(p).convert("RGBA")
        originals[p.stem] = image_to_data_uri(img)

    model_names = []
    seen = set()
    for r in all_results:
        if r["model"] not in seen:
            seen.add(r["model"])
            model_names.append(r["model"])

    image_names = [p.stem for p in image_paths]

    timing_summary = {}
    for model in model_names:
        times = [r["time_ms"] for r in all_results if r["model"] == model and r["time_ms"] > 0]
        if times:
            timing_summary[model] = {
                "mean": round(sum(times) / len(times), 1),
                "min": round(min(times), 1),
                "max": round(max(times), 1),
            }

    sorted_timing = sorted(timing_summary.items(), key=lambda x: x[1]["mean"])
    fastest_mean = sorted_timing[0][1]["mean"] if sorted_timing else 999999

    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>BiRefNet Transformers Benchmark</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, -apple-system, sans-serif; background: #1a1a2e; color: #e0e0e0; padding: 20px; }
  h1 { text-align: center; margin-bottom: 10px; color: #fff; }
  .subtitle { text-align: center; color: #888; margin-bottom: 30px; }
  .timing-table { margin: 0 auto 30px; border-collapse: collapse; }
  .timing-table th, .timing-table td { padding: 8px 16px; border: 1px solid #333; text-align: center; }
  .timing-table th { background: #2a2a4a; color: #aaa; font-size: 13px; text-transform: uppercase; }
  .fast { color: #4ade80; font-weight: bold; }
  .medium-speed { color: #fbbf24; }
  .slow { color: #f87171; }
  .controls { text-align: center; margin-bottom: 20px; }
  .controls label { margin: 0 10px; cursor: pointer; }
  .grid { display: grid; gap: 12px; padding: 10px; }
  .grid-header { font-weight: bold; text-align: center; font-size: 13px; color: #aaa;
                  display: flex; align-items: center; justify-content: center;
                  background: #2a2a4a; border-radius: 6px; padding: 8px 4px; }
  .cell { background: #16213e; border-radius: 6px; padding: 6px; text-align: center; }
  .cell img { width: 100%; height: auto; border-radius: 4px; image-rendering: pixelated; }
  .cell .time { font-size: 11px; color: #888; margin-top: 4px; }
  .cell .error { font-size: 11px; color: #f87171; margin-top: 4px; }
  .cell .name { font-size: 11px; color: #ccc; margin-bottom: 4px; }
  .checker { background-image: repeating-conic-gradient(#333 0% 25%, #222 0% 50%);
             background-size: 16px 16px; border-radius: 4px; }
</style>
</head>
<body>
<h1>BiRefNet Transformers vs rembg</h1>
<p class="subtitle">Native CUDA GPU vs ONNX CPU</p>

<table class="timing-table">
<tr><th>Model</th><th>Mean (ms)</th><th>Min</th><th>Max</th></tr>
"""
    for model, t in sorted_timing:
        mean = t["mean"]
        cls = "fast" if mean <= fastest_mean * 1.5 else ("medium-speed" if mean <= fastest_mean * 3 else "slow")
        html += f'<tr><td>{model}</td><td class="{cls}">{mean}</td><td>{t["min"]}</td><td>{t["max"]}</td></tr>\n'

    n_cols = len(model_names) + 1
    html += f"""</table>
<div class="controls">
  <strong>View:</strong>
  <label><input type="radio" name="view" value="result" checked onchange="toggleView(this.value)"> Result</label>
  <label><input type="radio" name="view" value="alpha" onchange="toggleView(this.value)"> Alpha (red=transparent)</label>
</div>
<div class="grid" id="grid">
<style>.grid {{ grid-template-columns: repeat({n_cols}, 1fr); }}</style>
"""
    html += '<div class="grid-header">Original</div>\n'
    for model in model_names:
        html += f'<div class="grid-header">{model}</div>\n'

    for img_name in image_names:
        display_name = img_name.split("_", 1)[1].replace("_", " ").title() if "_" in img_name else img_name
        html += f'<div class="cell"><div class="name">{display_name}</div>'
        html += f'<div class="checker"><img src="{originals[img_name]}"></div></div>\n'

        for model in model_names:
            r = next((x for x in all_results if x["model"] == model and x["image"] == img_name), None)
            if r and r.get("error"):
                html += f'<div class="cell"><div class="error">Error: {r["error"][:40]}</div></div>\n'
            elif r:
                html += f'<div class="cell"><div class="checker"><img class="result-img" src="{r["output_data_uri"]}" data-alpha="{r["alpha_data_uri"]}" data-result="{r["output_data_uri"]}"></div>'
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
</body></html>"""

    output_path.write_text(html, encoding="utf-8")
    print(f"\nDashboard saved to: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--images-dir", default="benchmark_images")
    parser.add_argument("--output", default="benchmark_birefnet.html")
    args = parser.parse_args()

    images_dir = Path(args.images_dir)
    image_paths = sorted(images_dir.glob("*.png"))
    if not image_paths:
        print(f"No PNGs in {images_dir}")
        return

    print(f"Found {len(image_paths)} test images")
    print(f"CUDA: {torch.cuda.is_available()}, Device: {torch.cuda.get_device_name(0)}")

    all_results: list[dict] = []

    # BiRefNet via transformers (GPU)
    print(f"\n{'='*60}")
    print("BiRefNet (transformers, fp32, CUDA)")
    print(f"{'='*60}")
    model = BiRefNetTransformers("ZhengPeng7/BiRefNet", "cuda")
    all_results.extend(benchmark_model("BiRefNet GPU fp32", model, image_paths))
    del model
    torch.cuda.empty_cache()

    print(f"\n{'='*60}")
    print("BiRefNet (transformers, fp16, CUDA)")
    print(f"{'='*60}")
    model_half = BiRefNetTransformersHalf("ZhengPeng7/BiRefNet", "cuda")
    all_results.extend(benchmark_model("BiRefNet GPU fp16", model_half, image_paths))
    del model_half
    torch.cuda.empty_cache()

    print(f"\n{'='*60}")
    print("BiRefNet-lite (transformers, fp32, CUDA)")
    print(f"{'='*60}")
    model_lite = BiRefNetTransformersLite("cuda")
    all_results.extend(benchmark_model("BiRefNet-lite GPU fp32", model_lite, image_paths))
    del model_lite
    torch.cuda.empty_cache()

    # rembg comparisons (CPU, best from previous benchmark)
    for rembg_model in ["u2netp", "u2net", "isnet-general-use"]:
        print(f"\n{'='*60}")
        print(f"rembg/{rembg_model} (ONNX CPU)")
        print(f"{'='*60}")
        all_results.extend(benchmark_rembg(rembg_model, image_paths))

    # Save JSON
    json_path = Path(args.output).with_suffix(".json")
    json_safe = [{k: v for k, v in r.items() if "data_uri" not in k} for r in all_results]
    json_path.write_text(json.dumps(json_safe, indent=2))
    print(f"\nRaw data: {json_path}")

    build_html(image_paths, all_results, Path(args.output))


if __name__ == "__main__":
    main()
