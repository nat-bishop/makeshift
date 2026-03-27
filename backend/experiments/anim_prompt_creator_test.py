#!/usr/bin/env python3
"""Compare different system prompts for the animation cell creator LLM.

Text-only — no image generation. Tests how well different prompting
strategies produce animation cell descriptions for diverse characters.

Usage:
    uv run python -m experiments.anim_prompt_creator_test
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

TEXT_MODEL = "gemini-3.1-flash-lite-preview"
OUTPUT_DIR = SCRIPT_DIR / "output" / "prompt_creator"


# ── Test characters (diverse morphologies) ─────────────────────────────

CHARACTERS = [
    {"id": "knight", "desc": "a knight in plate armor with a sword and cape"},
    {"id": "slime", "desc": "a cheerful green slime blob with big eyes"},
    {"id": "parrot", "desc": "a colorful tropical parrot"},
    {"id": "snake", "desc": "a long purple serpent with yellow markings"},
    {"id": "ghost", "desc": "a glowing translucent ghost with a trailing wispy tail"},
    {"id": "spider", "desc": "a large black spider with eight legs"},
    {"id": "wolf", "desc": "a grey wolf"},
    {"id": "mushroom", "desc": "a walking mushroom creature with stubby legs"},
]


# ── System prompt strategies ───────────────────────────────────────────

STRATEGY_A = {
    "id": "A_minimal",
    "name": "Minimal",
    "system": """\
Generate 4 animation frame descriptions for a 2x2 sprite sheet.
The frames should form a looping animation cycle.
Each description should describe the character's pose, not their appearance.

Output JSON:
{
  "animation_type": "short label like walk, bounce, slither, float, etc",
  "animation_description": "one sentence explaining the motion",
  "cells": {"1": "...", "2": "...", "3": "...", "4": "..."}
}""",
}

STRATEGY_B = {
    "id": "B_detailed",
    "name": "Detailed with context",
    "system": """\
You generate animation frame descriptions for a 2D game sprite sheet.

CONTEXT: A sprite sheet is a single image divided into a grid of cells. Each cell
contains one frame of animation. A game engine displays these frames in rapid
sequence to create movement — like a flipbook. The frames loop continuously,
so the last frame must transition smoothly back to the first.

YOUR TASK: Given a character description, determine the most natural movement
for this type of creature, then describe 4 frames that capture one complete
cycle of that movement. The character always faces right and moves toward the
right edge of the frame.

FRAME DESCRIPTION RULES:
- Each description must be SELF-CONTAINED — it will be used independently to
  generate an image. Do not reference other frames ("returns to", "same as frame 1").
- Describe the POSE: body shape, limb positions, height, compression/extension.
- Do not describe color, texture, or art style — only the physical pose.
- Use directional language relative to the image: "toward the right edge" means
  forward (direction of travel), "toward the left edge" means backward.
- Describe what makes each frame VISUALLY DISTINCT from the others. If two
  frames look identical, the animation fails.
- Keep each description to 2-3 sentences.

Output JSON only, no markdown:
{
  "animation_type": "walk|bounce|slither|float|hop|crawl|etc",
  "animation_description": "A brief explanation of the full motion cycle and why it suits this character",
  "cells": {"1": "frame 1 pose", "2": "frame 2 pose", "3": "frame 3 pose", "4": "frame 4 pose"}
}""",
}

STRATEGY_C = {
    "id": "C_taxonomy",
    "name": "Movement taxonomy",
    "system": """\
You generate animation frame descriptions for a 2D game sprite sheet.

A sprite sheet is a grid of animation frames displayed in sequence to create
movement. You are generating 4 frames that loop seamlessly. The character
faces right and moves rightward.

STEP 1 — Determine the movement type from the character's body plan:
- BIPEDAL WALK: humanoids, birds on ground — alternating leg strides
- QUADRUPED WALK: four-legged animals — diagonal leg pair alternation
- BOUNCE: blobs, slimes, balls — squash flat on ground, stretch tall in air
- SLITHER: snakes, worms — S-curve body shifts forward along the ground
- FLOAT/BOB: ghosts, wisps, jellyfish — vertical oscillation, trailing elements
- HOP: frogs, small birds — crouch, leap, airborne, land
- CRAWL: spiders, insects, crabs — low body, many legs ripple in waves
- WADDLE: penguins, mushroom creatures, short-legged — body rocks side to side with tiny steps

STEP 2 — Describe 4 frames that capture one complete cycle.

RULES:
- Each frame description is SELF-CONTAINED — never reference other frames.
- Describe the POSE only, not color or style.
- Each frame must be VISUALLY DISTINCT. Explain what makes it different.
- Use "toward the right edge" for forward, "toward the left edge" for backward.
- 2-3 sentences per frame.

Output JSON only:
{
  "animation_type": "the movement type from the list above",
  "animation_description": "one sentence explaining the full cycle",
  "cells": {"1": "...", "2": "...", "3": "...", "4": "..."}
}""",
}

STRATEGY_D = {
    "id": "D_img_aware",
    "name": "Image-generation aware",
    "system": """\
You write pose descriptions that will be placed into an image generation prompt.
Each description you write will be combined with a character's visual appearance
and sent to an AI image generator to produce one frame of a sprite sheet animation.

The image generator will receive ALL FOUR descriptions at once and produce a
2x2 grid image — one frame per cell. The generator needs to understand:
1. What pose the character is in (body shape, limb positions)
2. How this pose is DIFFERENT from the other three cells
3. That the character faces right in every cell

Because the image generator sometimes makes mistakes, your descriptions should be
DEFENSIVE — explicitly state things that prevent common errors:
- Always mention the character faces right / toward the right edge
- Describe the overall SILHOUETTE SHAPE (wide/narrow, tall/short, compact/spread)
  because this is what the generator is best at varying
- State which parts of the body are HIGH vs LOW, FORWARD vs BACKWARD
- Mention what is DIFFERENT about this frame compared to the others in the cycle

DETERMINE the right movement type for the character (walk, bounce, float, slither,
crawl, hop, etc.) based on their body plan, then write 4 frame descriptions.

Output JSON only:
{
  "animation_type": "movement type",
  "animation_description": "one sentence describing the full motion cycle",
  "cells": {"1": "...", "2": "...", "3": "...", "4": "..."}
}""",
}

STRATEGIES = [STRATEGY_A, STRATEGY_B, STRATEGY_C, STRATEGY_D]


# ── LLM call ───────────────────────────────────────────────────────────


def generate_cells(system_prompt: str, character_desc: str) -> dict:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    response = client.models.generate_content(
        model=TEXT_MODEL,
        contents=f"Character: {character_desc}",
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.7,
            response_mime_type="application/json",
        ),
    )
    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3].strip()
    return json.loads(text)


# ── Dashboard ──────────────────────────────────────────────────────────


def generate_dashboard(all_results: list[dict]) -> str:
    data_json = json.dumps(all_results, indent=2)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Animation Prompt Creator Comparison</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #1a1a2e; color: #e0e0e0;
    font-family: 'Segoe UI', system-ui, sans-serif; padding: 24px;
    max-width: 1400px; margin: 0 auto;
  }}
  h1 {{ font-size: 22px; margin-bottom: 16px; color: #fff; }}
  h2 {{ font-size: 16px; color: #9ecfff; margin-bottom: 8px; }}

  .char-section {{
    margin-bottom: 32px;
  }}
  .char-header {{
    font-size: 15px; color: #fff; margin-bottom: 12px;
    padding: 8px 12px; background: #16213e;
    border: 1px solid #2a2a4a; border-radius: 8px;
  }}
  .char-header .desc {{ color: #888; font-size: 13px; }}

  .strategies {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 12px;
  }}
  .strat-card {{
    background: #16213e; border: 1px solid #2a2a4a; border-radius: 10px;
    padding: 14px;
  }}
  .strat-card h3 {{
    font-size: 13px; color: #c0d0e0; margin-bottom: 4px;
  }}
  .anim-type {{
    display: inline-block; font-size: 11px; padding: 2px 8px;
    border-radius: 4px; background: #1b3a2a; color: #8fc;
    margin-bottom: 8px;
  }}
  .anim-desc {{
    font-size: 11px; color: #999; margin-bottom: 10px;
    font-style: italic;
  }}
  .cell-list {{
    list-style: none; padding: 0;
  }}
  .cell-list li {{
    font-size: 11px; color: #bbb; margin-bottom: 8px;
    padding: 8px; background: #0f1a2e; border-radius: 6px;
    line-height: 1.5;
  }}
  .cell-list li strong {{
    color: #9ecfff; font-size: 10px;
    text-transform: uppercase; letter-spacing: 0.5px;
  }}
  .error {{ color: #f08080; font-size: 12px; }}

  .sys-prompt-section {{
    margin-bottom: 24px;
  }}
  .sys-prompt-section details {{
    margin-bottom: 8px;
  }}
  .sys-prompt-section summary {{
    font-size: 13px; color: #888; cursor: pointer;
    padding: 6px 10px; background: #16213e;
    border: 1px solid #2a2a4a; border-radius: 6px;
  }}
  .sys-prompt-section pre {{
    font-size: 10px; color: #777; margin: 8px 0;
    white-space: pre-wrap; word-break: break-word;
    padding: 10px; background: #0a0f1e; border-radius: 6px;
    max-height: 300px; overflow-y: auto;
    line-height: 1.5;
  }}
</style>
</head>
<body>
<h1>Animation Prompt Creator Comparison</h1>
<p style="font-size:12px;color:#888;margin-bottom:20px">
  Comparing {len(STRATEGIES)} system prompt strategies across {len(CHARACTERS)} character types.
  Text LLM only ({TEXT_MODEL}) — no image generation.
</p>

<div class="sys-prompt-section">
  <h2>System Prompts</h2>
""" + "".join(
    f'  <details><summary>{s["name"]} ({s["id"]})</summary><pre>{s["system"]}</pre></details>\n'
    for s in STRATEGIES
) + f"""
</div>

<div id="results"></div>

<script>
const DATA = {data_json};

const container = document.getElementById('results');

// Group by character
const chars = {{}};
DATA.forEach(r => {{
  if (!chars[r.char_id]) chars[r.char_id] = {{desc: r.char_desc, results: []}};
  chars[r.char_id].results.push(r);
}});

Object.entries(chars).forEach(([charId, data]) => {{
  const section = document.createElement('div');
  section.className = 'char-section';

  let cardsHtml = '';
  data.results.forEach(r => {{
    if (r.error) {{
      cardsHtml += `<div class="strat-card"><h3>${{r.strategy_name}}</h3><div class="error">${{r.error}}</div></div>`;
      return;
    }}

    let cellsHtml = '';
    Object.entries(r.cells).forEach(([k, v]) => {{
      cellsHtml += `<li><strong>Cell ${{k}}</strong><br>${{v}}</li>`;
    }});

    cardsHtml += `
      <div class="strat-card">
        <h3>${{r.strategy_name}}</h3>
        <span class="anim-type">${{r.animation_type}}</span>
        <div class="anim-desc">${{r.animation_description}}</div>
        <ul class="cell-list">${{cellsHtml}}</ul>
      </div>`;
  }});

  section.innerHTML = `
    <div class="char-header">
      ${{charId}} <span class="desc">— ${{data.desc}}</span>
    </div>
    <div class="strategies">${{cardsHtml}}</div>`;
  container.appendChild(section);
}});
</script>
</body>
</html>"""


# ── Main ───────────────────────────────────────────────────────────────


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    total = len(STRATEGIES) * len(CHARACTERS)
    print(f"Animation Prompt Creator Comparison")
    print(f"  {len(STRATEGIES)} strategies x {len(CHARACTERS)} characters = {total} LLM calls")
    print(f"  Text model: {TEXT_MODEL}")
    print(f"  Output: {OUTPUT_DIR}\n")

    all_results: list[dict] = []

    for char in CHARACTERS:
        print(f"  {char['id']}:")
        for strat in STRATEGIES:
            result = {
                "char_id": char["id"],
                "char_desc": char["desc"],
                "strategy_id": strat["id"],
                "strategy_name": strat["name"],
                "animation_type": "",
                "animation_description": "",
                "cells": {},
                "error": None,
            }
            try:
                data = generate_cells(strat["system"], char["desc"])
                result["animation_type"] = data.get("animation_type", "unknown")
                result["animation_description"] = data.get("animation_description", "")
                result["cells"] = data.get("cells", {})
                print(f"    {strat['id']}: {result['animation_type']}")
            except Exception as e:
                result["error"] = f"{type(e).__name__}: {e}"
                print(f"    {strat['id']}: FAILED — {result['error']}")

            all_results.append(result)

    # Save results
    results_path = OUTPUT_DIR / "results.json"
    results_path.write_text(json.dumps(all_results, indent=2), encoding="utf-8")

    dashboard = generate_dashboard(all_results)
    (OUTPUT_DIR / "dashboard.html").write_text(dashboard, encoding="utf-8")

    ok = sum(1 for r in all_results if not r["error"])
    print(f"\n{'='*60}")
    print(f"DONE — {ok}/{total} succeeded")
    print(f"Dashboard: {OUTPUT_DIR / 'dashboard.html'}")


if __name__ == "__main__":
    main()
