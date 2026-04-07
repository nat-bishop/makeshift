"""Generate sample images from FLUX and save to disk for visual comparison."""

import base64
import httpx
import os
import sys
import time

URL = "http://127.0.0.1:5100/v1/images/generations"
TIMEOUT = 180.0
STEPS = 4
GUIDANCE = 1.0
OUT_DIR = os.path.join(os.path.dirname(__file__), "samples")

PROMPTS = [
    "a glowing fire sword",
    "a wooden treasure chest",
    "a bouncy rubber ball",
    "a glass potion bottle",
    "a stone castle tower",
    "a metal robot",
    "an ice crystal",
    "a cloth flag",
    "a bone skeleton key",
    "a lava rock",
]

PROMPT_PREFIX = "mixed media collage style paper cutout, side view, flat lighting, clean edges"
PROMPT_SUFFIX = "single centered object, contrasting solid background color, no text"


def generate_and_save(prompt: str, size: str, model_label: str, index: int) -> float:
    full_prompt = f"{PROMPT_PREFIX}, {prompt}, {PROMPT_SUFFIX}"
    payload = {
        "model": "flux",
        "prompt": full_prompt,
        "n": 1,
        "size": size,
        "response_format": "b64_json",
        "num_inference_steps": STEPS,
        "guidance_scale": GUIDANCE,
    }
    t0 = time.perf_counter()
    r = httpx.post(URL, json=payload, timeout=TIMEOUT)
    elapsed = time.perf_counter() - t0
    r.raise_for_status()

    img_b64 = r.json()["data"][0]["b64_json"]
    img_bytes = base64.b64decode(img_b64)

    safe_name = prompt.replace(" ", "_").replace("a_", "")
    res_label = size.replace("x", "")
    filename = f"{model_label}_{res_label}_{index:02d}_{safe_name}.png"
    filepath = os.path.join(OUT_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(img_bytes)

    return elapsed


def main():
    model_label = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    os.makedirs(OUT_DIR, exist_ok=True)

    # Warmup request (not saved)
    print(f"Warming up {model_label}...", end=" ", flush=True)
    try:
        generate_and_save("warmup test", "512x512", "warmup", 0)
        os.remove(os.path.join(OUT_DIR, "warmup_512_00_warmup_test.png"))
    except Exception:
        pass
    print("done")

    for size in ["512x512", "256x256"]:
        print(f"\n{model_label} @ {size}:")
        for i, prompt in enumerate(PROMPTS):
            t = generate_and_save(prompt, size, model_label, i)
            print(f"  {i+1:2d}/10  {t:.2f}s  {prompt}")

    print(f"\nImages saved to {OUT_DIR}/")


if __name__ == "__main__":
    main()
