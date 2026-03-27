# Animation Pipeline Reference

Reference document for implementing sprite sheet animation generation into the game pipeline. Based on extensive experimentation (March 2026) testing reference images, iterative generation, single-sheet approaches, and various prompting strategies.

## Approach Summary

**Winner: Single-sheet 2x2 spritesheet with template-guided generation.**

Generate all 4 animation frames in a single Gemini image generation call. A lightweight text LLM generates the per-cell pose descriptions, which get slotted into a fixed prompt template.

### Why this approach

- **Reference image approach failed.** Passing the base sprite as a reference and asking for pose variations doesn't work — the model either reproduces the reference exactly or drifts completely. The community confirms this.
- **Iterative/chat approaches are slow and inconsistent.** Generating frames one-by-one (even with chat context) produces characters that look different across frames.
- **Single-sheet generation** keeps character consistency because the model draws all 4 poses in one image. The template grid image anchors the layout structure.
- **TEXT+IMAGE response modality** and **template-guided** were the two best variants in A/B testing. The final pipeline uses template-guided with IMAGE-only modality.

## Pipeline Flow

```
Player types "a fire-breathing dragon"
                    │
                    ▼
        ┌───────────────────────┐
        │   Creator Agent       │  (existing)
        │   (Gemini Flash Lite) │
        │                       │
        │   Output:             │
        │   - name              │
        │   - tags              │
        │   - behaviors         │
        │   - visual_descriptor │
        └───────────┬───────────┘
                    │
          ┌─────────┴──────────┐
          │                    │
          ▼                    ▼
  ┌───────────────┐   ┌────────────────────┐
  │ Static sprite │   │ Cell Creator LLM   │
  │ (existing     │   │ (Gemini Flash Lite)│
  │  pipeline)    │   │                    │
  │               │   │ Input: description │
  │ Output:       │   │ Output:            │
  │ - sprite URL  │   │ - animation_type   │
  │               │   │ - animation_desc   │
  └───────┬───────┘   │ - frame_pattern    │
          │           │ - 4 cell descs     │
          │           └────────┬───────────┘
          │                    │
          │                    ▼
          │           ┌────────────────────┐
          │           │ Prompt Assembly    │
          │           │ (fixed template)   │
          │           │                    │
          │           │ Slots in:          │
          │           │ - appearance       │
          │           │ - anim type + desc │
          │           │ - cell descriptions│
          │           │ - frame_pattern    │
          │           │ - defensive rules  │
          │           └────────┬───────────┘
          │                    │
          │                    ▼
          │           ┌────────────────────┐
          │           │ Gemini Image Gen   │
          │           │                    │
          │           │ Inputs:            │
          │           │ 1. Template image  │
          │           │ 2. Assembled prompt│
          │           │ + system instr     │
          │           │                    │
          │           │ Output: 1024x1024  │
          │           │ 2x2 spritesheet    │
          │           └────────┬───────────┘
          │                    │
          │                    ▼
          │           ┌────────────────────┐
          │           │ Post-processing    │
          │           │                    │
          │           │ 1. Slice into 4    │
          │           │ 2. Bg remove each  │
          │           │ 3. Crop & fit each │
          │           │    to 512x512      │
          │           └────────┬───────────┘
          │                    │
          ▼                    ▼
   sprite_ready          animation_ready
   (WebSocket)           (WebSocket)
```

The static sprite and animation can be generated in parallel. The client shows the static sprite immediately, then upgrades to animated when the spritesheet arrives.

## Timing & Cost

| Step | Time | Cost |
|------|------|------|
| Cell creator LLM (flash-lite) | ~1-2s | ~$0.001 |
| Image generation (1024x1024 sheet) | ~10-15s | ~$0.04 |
| Bg removal x4 (BiRefNet GPU) | ~4-8s | free (local) |
| **Total** | **~15-25s** | **~$0.041** |

This runs in parallel with static sprite generation (~12s), so total wall time doesn't increase much.

## Not Every Object Needs Animation

Gate animation by tags/behaviors:
- `LIVING` tag → animate
- Has movement behaviors (`MOVE_TOWARD`, `MOVE_AWAY`, `PATROL`) → animate
- `FLOATING` tag → animate (bob cycle)
- `LIQUID`, `GAS`, `MOLTEN` → animate (flow cycle)
- Plain `SOLID`+`RIGID` objects (walls, blocks) → skip, keep static sprite

## The Prompts

### 1. Cell Creator System Prompt

This is the system prompt for the text LLM that generates per-cell pose descriptions.

```
You write pose descriptions for an AI image generator that will produce a
2x2 sprite sheet — 4 animation frames in a single image. All 4 descriptions
are sent TOGETHER in one prompt, so you CAN reference relationships between
cells (e.g. 'mirror of Cell 1 with opposite limbs').

HOW THE IMAGE GENERATOR WORKS:
- It is best at varying the overall SILHOUETTE SHAPE between cells
- It struggles with 'left leg' vs 'right leg' in side view — these are
  ambiguous. Instead use: 'the leading leg' (toward right edge), 'the
  trailing leg' (toward left edge), 'the OTHER leg', or describe the
  silhouette shape ('legs wide apart' vs 'legs close together')
- It sometimes flips the character direction — explicitly state 'facing
  right' and 'toward the right edge' in EVERY cell description
- It sometimes makes all 4 cells look the same — you must describe what
  is VISUALLY DIFFERENT about each cell's silhouette

YOUR TASK:
1. Determine the movement type from the character's body plan
2. Write 4 pose descriptions that form a looping cycle
3. Write a frame_pattern that summarizes the visual contrast between frames
   (this gets inserted into the consistency rules the image generator sees)

POSE DESCRIPTION RULES:
- Describe the BODY HEIGHT in each frame (low/compressed vs tall/stretched)
- Describe the SILHOUETTE WIDTH (wide/spread vs narrow/compact)
- Use screen-space directions: 'toward the right edge' = forward,
  'toward the left edge' = backward
- NEVER say 'left leg' or 'right leg' — say 'leading leg', 'trailing leg',
  'the OTHER leg', or describe the shape
- State relationships: 'same wide stride as Cell 1 but the OTHER leg leads'
- Mention follow-through elements (capes trailing, tentacles dragging, etc)
- 2-3 sentences per cell
- Do NOT describe color, texture, or art style — only the pose

FRAME PATTERN EXAMPLES:
- Walk: 'Cells 1 and 3 show wide strides (legs apart, body low). Cells 2
  and 4 show compact passing poses (legs together, body tall).'
- Bounce: 'Cells 1 and 3 show squashed flat shapes (wide, low). Cells 2
  and 4 show stretched tall shapes (narrow, high).'
- Float: 'The body rises and falls across cells. Trailing elements change
  angle with each position.'

Output JSON only:
{
  "animation_type": "walk|bounce|slither|float|hop|crawl|etc",
  "animation_description": "2-3 sentences explaining the full motion cycle,
    what drives it, and why it suits this character",
  "frame_pattern": "1-2 sentences describing the visual contrast pattern
    between the 4 cells",
  "cells": {"1": "...", "2": "...", "3": "...", "4": "..."}
}
```

**User message:** `Character: {player's description of the object}`

**Model:** `gemini-3.1-flash-lite-preview` (cheapest, fast, good enough for this)

**Config:** `temperature=0.7`, `response_mime_type="application/json"`

**JSON parsing note:** The LLM sometimes produces trailing commas. Strip them with: `re.sub(r",\s*([}\]])", r"\1", text)` before parsing.

### 2. Image Generation System Instruction

This is the `system_instruction` parameter on the Gemini image generation call. It never changes — it explains what a sprite sheet is and sets the layout rules.

```
You are creating a sprite sheet for a 2D video game. A sprite sheet is a
single image containing multiple frames of a character animation, arranged
in a grid. Game engines display these frames in rapid sequence to create
the illusion of movement — like a flipbook.

You are generating a looping animation cycle. The animation repeats
seamlessly — the last frame connects back to the first frame. The character
faces toward the RIGHT side of the image in every frame.

LAYOUT: The attached template image shows the exact grid layout to follow.
It is a 2x2 grid with 4 equal cells separated by red lines, numbered 1-4.
Cell 1 is top-left, Cell 2 is top-right, Cell 3 is bottom-left, Cell 4 is
bottom-right. Replace each numbered cell with the corresponding animation
frame as described in the prompt.

RULES:
- Keep the red grid lines in place to separate the cells
- Center the character within each cell — do not let the character cross
  into adjacent cells
- Fill all empty space around the character with a flat solid background color
- The character must look identical across all 4 cells — same proportions,
  same colors, same art style. Only the pose changes between cells.
- Do not draw the numbered circles from the template
- Do not include any text, numbers, labels, or watermarks in the output
```

### 3. Image Generation Content Prompt (Template)

This is the user message sent to the image generation call. It's a template with slots filled from the creator agent output and the cell creator LLM output.

```
CHARACTER: {appearance} The character is shown in side view, facing right,
moving toward the right edge of the image. Mixed media collage style paper
cutout art, flat lighting, clean edges.

ANIMATION: Generate a 4-frame {animation_type} cycle for this character.
{animation_description}

THE FOUR FRAMES:
Cell 1: {cells["1"]}

Cell 2: {cells["2"]}

Cell 3: {cells["3"]}

Cell 4: {cells["4"]}

CRITICAL CONSISTENCY RULES:
- The character faces toward the RIGHT edge of the image in ALL FOUR cells.
  The character is moving to the right. No cell should show the character
  facing left or turning around.
- Every cell must show a VISIBLY DIFFERENT pose from the others.
  {frame_pattern} If two cells look the same, the animation will not work.
- The character's face, body shape, clothing, colors, and art style must be
  IDENTICAL in all four cells. The only thing that changes between cells is
  the pose.
- The character's full body must be visible from head to feet in every cell,
  centered within the cell boundaries.

Flat solid background color in every cell.
```

### 4. Template Image

A 1024x1024 PNG with a 2x2 grid:
- Red (`#ff0000`) grid lines, 2px width
- Red border around the entire image
- Dark background (`#1a1a1a`)
- White numbered circles (1-4) centered in each cell
- Generated programmatically with PIL

```python
def make_template_2x2() -> bytes:
    size, grid, cell = 1024, 2, 512
    img = Image.new("RGB", (size, size), "#1a1a1a")
    draw = ImageDraw.Draw(img)
    lc = "#ff0000"
    draw.line([(cell, 0), (cell, size - 1)], fill=lc, width=2)
    draw.line([(0, cell), (size - 1, cell)], fill=lc, width=2)
    draw.rectangle([0, 0, size - 1, size - 1], outline=lc, width=2)
    font = ImageFont.load_default(size=48)
    for row in range(grid):
        for col in range(grid):
            num = row * grid + col + 1
            cx, cy = col * cell + cell // 2, row * cell + cell // 2
            r = 40
            draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                         fill="#fff", outline=lc, width=2)
            label = str(num)
            bbox = draw.textbbox((0, 0), label, font=font)
            tw = bbox[2] - bbox[0]
            draw.text((cx - tw // 2, cy - bbox[1] // 2 - bbox[1]),
                      label, fill="#000", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
```

The template can be generated once at startup and cached.

### 5. Gemini API Call Structure

```python
from google.genai import types

# Contents: template image + text prompt
contents = [
    types.Part.from_bytes(data=template_bytes, mime_type="image/png"),
    assembled_prompt_text,
]

response = client.models.generate_content(
    model="gemini-3.1-flash-image-preview",
    contents=contents,
    config=types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        image_config=types.ImageConfig(
            image_size="1K",
            aspect_ratio="1:1",
        ),
        system_instruction=IMAGE_SYS_INSTR,
    ),
)
```

**Key settings:**
- `image_size="1K"` (1024x1024 — needed for 2x2 grid of 512x512 cells)
- `aspect_ratio="1:1"`
- `response_modalities=["IMAGE"]` (IMAGE only, not TEXT+IMAGE)

## Post-Processing

### Slicing

Slice the 1024x1024 sheet into 4 frames with a 4px margin to crop grid line artifacts:

```python
def slice_sheet_2x2(img: Image.Image) -> list[Image.Image]:
    w, h = img.size
    cw, ch = w // 2, h // 2
    margin = 4
    return [
        img.crop((col * cw + margin, row * ch + margin,
                  (col + 1) * cw - margin, (row + 1) * ch - margin))
        for row in range(2) for col in range(2)
    ]
```

### Background Removal

Each frame gets bg removal (BiRefNet GPU, same as static sprites) then crop & fit to 512x512 at 90% fill.

### Delivery

Send via WebSocket as a new `animation_ready` message type:

```json
{
  "type": "animation_ready",
  "object_id": "...",
  "spritesheet_url": "/static/sprites/{hash}_anim.png",
  "frame_count": 4,
  "columns": 2,
  "fps": 4
}
```

Or deliver 4 individual frame URLs if the client prefers to build `SpriteFrames` from individual textures.

## Godot Client Integration

Replace `Sprite2D` with `AnimatedSprite2D` when animation arrives:

1. Create `SpriteFrames` resource programmatically
2. For each frame, create an `AtlasTexture` pointing at the spritesheet region (or load individual frame textures)
3. Set FPS from the message
4. Start playing the default animation
5. Keep the static `Sprite2D` visible until animation is ready (progressive upgrade)

## Learnings from Experimentation

### What failed

| Approach | Problem |
|----------|---------|
| **Reference image per-frame** | Model reproduces the reference exactly or drifts completely. Doesn't change poses. |
| **Iterative chat (frame by frame)** | Character appearance drifts across turns. Slow (4 sequential calls). |
| **Inbetween interpolation** | Same drift problem. Also slow. |
| **"left leg" / "right leg" language** | Ambiguous in side view. Model can't tell which leg is which. |
| **Minimal prompts** | Model defaults to idle/breathing instead of walk. Cells look identical. |
| **Hardcoded hex colors in prompt** | Unnecessary specificity. "Flat solid background color" works fine. |

### What worked

| Technique | Why |
|-----------|-----|
| **Template image** | Visual constraint anchors the grid layout. Model understands cell boundaries. |
| **System instruction explaining sprite sheets** | Model doesn't inherently know what sprite sheets are. Context helps enormously. |
| **Screen-space directions** | "toward the right edge" is unambiguous. "left leg" is not. |
| **Silhouette shape language** | "wide stride" vs "narrow compact pose" — the model is good at varying overall shape. |
| **Body height descriptions** | "body at lowest point" vs "body at tallest point" gives clear visual contrast. |
| **Frame relationships** | "mirror of Cell 1 with opposite leg leading" helps the model understand the cycle structure. |
| **frame_pattern in defensive rules** | Explicitly telling the model "Cells 1,3 are wide; Cells 2,4 are compact" prevents same-pose-everywhere. |
| **Defensive/positive framing** | "The character faces right in ALL FOUR cells" works better than "don't face left". |
| **Follow-through mentions** | "Cape trailing behind" adds life and helps differentiate frames. |

### Known remaining issues

- **Direction flipping** still happens occasionally (~10% of generations). Re-generating usually fixes it.
- **Quadruped walk** is harder than bipedal — the model sometimes shows 3/4 view instead of side view.
- **Very unusual creatures** (jellyfish, abstract shapes) work surprisingly well because silhouette variation is the primary motion.
- **Image gen is non-deterministic** — same prompt can produce good or bad results. Consider generating 2 sheets and picking the better one, or implementing a simple quality check.

## Example Outputs

### Cell Creator LLM Output (knight)

```json
{
  "animation_type": "walk",
  "animation_description": "A rhythmic, heavy walk cycle for a knight in
    plate armor. The motion emphasizes the weight of the steel through
    deep knee bends and a rhythmic swing of the cape that follows the
    momentum of the stride.",
  "frame_pattern": "Cells 1 and 3 show wide strides with the body at its
    lowest point. Cells 2 and 4 show compact passing poses with the body
    at its highest point.",
  "cells": {
    "1": "The knight is facing right with a wide stride, leading leg
      planted forward and trailing leg extended back. The body is low
      to the ground, and the red cape is bunched behind the shoulders.",
    "2": "The knight is facing right in a narrow, tall passing pose,
      with the trailing leg pulling forward to meet the leading leg.
      The body is at its peak height, and the cape swings forward to
      follow the momentum.",
    "3": "The knight is facing right with a wide stride, mirroring
      Cell 1 but with the other leg now leading forward. The body is
      compressed and low, and the cape drags heavily toward the left edge.",
    "4": "The knight is facing right in a narrow, tall passing pose,
      with the other leg pulling forward to reset the stride. The body
      is at its peak height, and the cape billows out behind the knight
      to prepare for the next step."
  }
}
```

### Cell Creator LLM Output (slime)

```json
{
  "animation_type": "hop",
  "animation_description": "A bouncy hop cycle. The slime compresses
    against the ground then launches upward, stretching tall before
    landing and compressing again.",
  "frame_pattern": "Cells 1 and 3 show wide, flat, compressed shapes
    (squashed against ground). Cells 2 and 4 show tall, narrow,
    stretched shapes (airborne/peak).",
  "cells": {
    "1": "Facing right, the slime is squashed flat against the ground,
      very wide and low. The body bulges slightly forward toward the
      right edge, preparing to launch.",
    "2": "Facing right, the slime is stretched tall and narrow, airborne
      above the ground. The body leans forward toward the right edge,
      eyes looking ahead.",
    "3": "Facing right, the slime has landed and is squashed flat again,
      even wider than Cell 1. A slight ripple runs through the body
      from the impact.",
    "4": "Facing right, the slime is stretched upward again, slightly
      tilted forward. The base tapers to a point as it lifts off."
  }
}
```

## File References

All experiment scripts are in `backend/experiments/`:

| File | What it tests |
|------|---------------|
| `anim_e2e_compare.py` | Full pipeline: 4 prompt strategies × 4 characters. **Best reference for implementation.** |
| `real_walk_ref_test.py` | Real walk cycle photo as pose reference vs template-only |
| `anim_advanced_compare.py` | Defensive template, pose ref, iterative chat, inbetween interpolation |
| `spritesheet_walk_compare.py` | Single-sheet strategies: IDENTICAL constraint, LLM choreography, template-guided |
| `walk_strategy_compare.py` | Reference image strategies: edit framing, system instruction, no-reference |
| `walk_prompt_compare.py` | Walk prompt wording: near/far leg, silhouette, phase names, minimal |
| `animation_ref_experiment.py` | Original reference image approach (per-frame generation) |
| `anim_prompt_creator_test.py` | Comparing cell creator system prompts (text-only, no image gen) |
