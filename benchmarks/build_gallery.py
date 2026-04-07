"""Build an HTML gallery dashboard from generated sample images."""

import base64
import os

SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "samples")
OUT_FILE = os.path.join(os.path.dirname(__file__), "dashboard.html")

PROMPTS = [
    ("glowing_fire_sword", "Fire Sword"),
    ("wooden_treasure_chest", "Treasure Chest"),
    ("bouncy_rubber_ball", "Rubber Ball"),
    ("glass_potion_bottle", "Potion Bottle"),
    ("stone_castle_tower", "Castle Tower"),
    ("metal_robot", "Robot"),
    ("an_ice_crystal", "Ice Crystal"),
    ("cloth_flag", "Flag"),
    ("bone_skeleton_key", "Skeleton Key"),
    ("lavrock", "Lava Rock"),
]

MODELS = ["9B", "4B"]
RESOLUTIONS = ["512512", "256256"]


def img_to_data_uri(path: str) -> str:
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:image/png;base64,{b64}"


def build():
    # Pre-encode all images
    images = {}
    for model in MODELS:
        for res in RESOLUTIONS:
            for i, (slug, _) in enumerate(PROMPTS):
                filename = f"{model}_{res}_{i:02d}_{slug}.png"
                filepath = os.path.join(SAMPLES_DIR, filename)
                if os.path.exists(filepath):
                    images[f"{model}_{res}_{i}"] = img_to_data_uri(filepath)
                else:
                    print(f"WARNING: missing {filepath}")
                    images[f"{model}_{res}_{i}"] = ""

    # Build image grid rows
    rows_html = ""
    for i, (slug, label) in enumerate(PROMPTS):
        rows_html += f'<div class="row">\n'
        rows_html += f'  <div class="row-label">{label}</div>\n'
        for model in MODELS:
            for res in RESOLUTIONS:
                key = f"{model}_{res}_{i}"
                src = images.get(key, "")
                res_label = "512" if res == "512512" else "256"
                rows_html += f'  <div class="cell"><img src="{src}" alt="{label} {model} {res_label}" loading="lazy"/></div>\n'
        rows_html += '</div>\n'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FLUX 9B vs 4B — Image Comparison</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace; background: #0a0a0f; color: #e0e0e0; padding: 1.5rem; }}
  h1 {{ font-size: 1.3rem; font-weight: 600; color: #fff; margin-bottom: 0.2rem; }}
  .subtitle {{ color: #555; font-size: 0.75rem; margin-bottom: 1.5rem; }}

  .header-row {{
    display: grid;
    grid-template-columns: 100px repeat(4, 1fr);
    gap: 6px;
    margin-bottom: 6px;
    position: sticky;
    top: 0;
    background: #0a0a0f;
    z-index: 10;
    padding: 0.5rem 0;
  }}
  .header-row .spacer {{ }}
  .header-cell {{
    text-align: center;
    padding: 0.4rem;
    border-radius: 4px;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.03em;
  }}
  .h-9b {{ background: #111828; color: #7eb8ff; }}
  .h-4b {{ background: #1a1128; color: #a78bfa; }}

  .row {{
    display: grid;
    grid-template-columns: 100px repeat(4, 1fr);
    gap: 6px;
    margin-bottom: 6px;
  }}
  .row-label {{
    display: flex;
    align-items: center;
    font-size: 0.7rem;
    color: #888;
    padding-right: 0.5rem;
    text-align: right;
    justify-content: flex-end;
  }}
  .cell {{
    background: #12121a;
    border: 1px solid #1e1e2e;
    border-radius: 6px;
    overflow: hidden;
    aspect-ratio: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: border-color 0.15s, transform 0.15s;
  }}
  .cell:hover {{
    border-color: #3b82f6;
    transform: scale(1.02);
    z-index: 5;
  }}
  .cell img {{
    width: 100%;
    height: 100%;
    object-fit: contain;
    image-rendering: auto;
  }}

  /* Lightbox */
  .lightbox {{
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.9);
    z-index: 100;
    align-items: center;
    justify-content: center;
    cursor: pointer;
  }}
  .lightbox.active {{ display: flex; }}
  .lightbox img {{
    max-width: 90vw;
    max-height: 90vh;
    image-rendering: pixelated;
    border-radius: 8px;
  }}
  .lightbox-label {{
    position: fixed;
    bottom: 2rem;
    left: 50%;
    transform: translateX(-50%);
    color: #888;
    font-size: 0.8rem;
    background: #12121a;
    padding: 0.4rem 1rem;
    border-radius: 4px;
  }}

  /* Stats bar */
  .stats-bar {{
    display: flex;
    gap: 2rem;
    margin-bottom: 1.5rem;
    padding: 0.75rem 1rem;
    background: #12121a;
    border: 1px solid #1e1e2e;
    border-radius: 6px;
    font-size: 0.7rem;
  }}
  .stats-bar .stat {{ display: flex; gap: 0.4rem; }}
  .stats-bar .label {{ color: #555; }}
  .stats-bar .val {{ color: #4ade80; font-weight: 600; }}
</style>
</head>
<body>

<h1>FLUX.2-klein: 9B vs 4B Image Comparison</h1>
<p class="subtitle">4 steps &middot; guidance 1.0 &middot; mixed media collage prompt &middot; same prompts, same seed behavior</p>

<div class="stats-bar">
  <div class="stat"><span class="label">9B @ 512 median:</span><span class="val">0.45s</span></div>
  <div class="stat"><span class="label">4B @ 512 median:</span><span class="val">0.34s</span></div>
  <div class="stat"><span class="label">9B @ 256 median:</span><span class="val">0.41s</span></div>
  <div class="stat"><span class="label">4B @ 256 median:</span><span class="val">0.41s</span></div>
  <div class="stat"><span class="label">4B speedup @ 512:</span><span class="val">24%</span></div>
</div>

<div class="header-row">
  <div class="spacer"></div>
  <div class="header-cell h-9b">9B &middot; 512</div>
  <div class="header-cell h-9b">9B &middot; 256</div>
  <div class="header-cell h-4b">4B &middot; 512</div>
  <div class="header-cell h-4b">4B &middot; 256</div>
</div>

{rows_html}

<div class="lightbox" id="lightbox" onclick="this.classList.remove('active')">
  <img id="lb-img" src="" alt=""/>
  <div class="lightbox-label" id="lb-label"></div>
</div>

<script>
document.querySelectorAll('.cell').forEach(cell => {{
  cell.addEventListener('click', () => {{
    const img = cell.querySelector('img');
    if (!img) return;
    document.getElementById('lb-img').src = img.src;
    document.getElementById('lb-label').textContent = img.alt;
    document.getElementById('lightbox').classList.add('active');
  }});
}});
</script>
</body>
</html>"""

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Dashboard written to {OUT_FILE}")


if __name__ == "__main__":
    build()
