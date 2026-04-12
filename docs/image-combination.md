# Image Combination via FLUX img2img

Experiments testing whether existing sprites can be combined into new sprites using FLUX.2-klein-4B's img2img endpoint, rather than generating every combined object from scratch. Covers three use cases: object combination, carry/ride, and destruction.

## Setup

- **Model**: FLUX.2-klein-4B on SGLang
- **Endpoint**: `/v1/images/edits` (Kontext-style, not traditional img2img)
- **Reference images**: 256x256 PNG on solid white background (see [Reference Image Format](#reference-image-format))
- **Text prompt**: Art style template wrapping an LLM-generated visual description
- **Output pipeline**: BG removal + crop to 512x512, same as regular sprites

## How FLUX Kontext img2img Works

FLUX's edits endpoint is NOT traditional img2img (add noise to image, denoise with prompt). It uses a **Kontext architecture**:

- Each reference image is VAE-encoded independently into latent space
- Each gets a separate **time coordinate** in 3D rotary positional embeddings: first image = T10, second = T20, etc.
- Image latents are **concatenated with the output noise** along the sequence dimension
- The model attends to reference tokens during denoising — they're context, not initialization
- **There is no denoising strength parameter.** The prompt is the only control over how the model uses the references.

Consequence: the text prompt must tell FLUX **what to do** with the reference images. Without direction, it tends to reproduce them side by side or favor one over the other.

## Reference Image Format

Tested 4 variants across all use cases:

| Variant | Result |
|---------|--------|
| 512x512 transparent | Current pipeline default. Works but causes duplication with some objects |
| 256x256 transparent | Better than 512 but still has artifacts |
| 512x512 white background | Good but slightly worse than 256 |
| **256x256 white background** | **Best.** Most consistent, fewest artifacts, best likeness |

**Use 256x256 on solid white background for all reference images.** The smaller resolution reduces the reference's visual weight so FLUX doesn't over-reproduce it, and the solid background avoids transparency-related artifacts.

To prepare a reference image:
```python
def prepare_reference(sprite_bytes: bytes) -> bytes:
    """Convert a 512x512 RGBA sprite to a 256x256 white-bg reference."""
    img = Image.open(io.BytesIO(sprite_bytes)).convert("RGBA")
    img = img.resize((256, 256), Image.Resampling.LANCZOS)
    bg = Image.new("RGBA", (256, 256), (255, 255, 255, 255))
    bg.paste(img, (0, 0), img)
    buf = io.BytesIO()
    bg.save(buf, format="PNG")
    return buf.getvalue()
```

## Use Case 1: Object Combination

Two objects combined into a new hybrid object. E.g., flame + skull → flaming skull.

### Experiment Summary (7 rounds, ~600 images)

- **Round 1-2**: Tested stitching, alpha blending, single-image edit, two-reference. Only two separate references works.
- **Round 3**: Tested template strategies (material/semantic/themed). No single template wins — the combination TYPE determines the best approach.
- **Round 4-6**: Tested LLM-generated descriptions. Over-specified prompts dilute reference image influence. Short names alone aren't enough.
- **Round 7**: LLM taught the three patterns and picks per-pair. **Winner.**

### Pipeline

```
Input:
  object_a: {name, visual_description}   # from creation pipeline
  object_b: {name, visual_description}   # from creation pipeline
  sprite_a: bytes                         # existing sprite PNG
  sprite_b: bytes                         # existing sprite PNG

Step 1 — LLM picks image order (1-token call, parallel):
  "Which should be the primary shape reference? 1: {name_a} 2: {name_b}" → "1" or "2"

Step 2 — LLM generates visual description (~15 output tokens, parallel with step 1):
  System instruction:
    "You write visual descriptions for a sprite image generator.
    Two objects are being combined. Choose the best approach:
    - MATERIAL: 'the shape of B but made from/constructed of A'
    - THEMED: 'B with A elements, accents, and motifs woven into its design'
    - SEMANTIC: 'an A B, combining elements of both into one object'
    Pick the best fit. Reference specific visual details from both descriptions.
    Under 25 words."
  User: "Object A: {name_a} — {desc_a}\nObject B: {name_b} — {desc_b}"

Step 3 — Assemble prompt:
  STYLE + llm_output + SUFFIX

Step 4 — Prepare references:
  Both sprites → 256x256 white background

Step 5 — FLUX /v1/images/edits:
  image1 = LLM-chosen-first, image2 = other

Step 6 — BG removal + crop to 512x512
```

### Image Ordering

First image (T10) has more influence on overall structure. LLM ordering picks correctly ~80% of the time. The "more structurally distinct" object works better as img1.

## Use Case 2: Carry/Ride

Character carrying an object or riding a mount. The character sprite and object sprite are both known.

### Experiment Summary (5 rounds, ~300 images)

- **Round 1**: Tested 4 prompt templates × 2 orderings. `action-detailed` with char→obj ordering wins.
- **Round 2-3**: Fixed duplication issue — object name + description in prompt caused double rendering (e.g., "carrying sword, steel longsword" → two swords). Using description only (no name) helps but doesn't fully fix it.
- **Round 4**: LLM-generated prompts match or beat templates. LLM naturally avoids the duplication issue by writing a scene description rather than listing object properties.
- **Round 5**: Reference image format test. **256x256 white background is best** — fixes remaining duplication/mirroring artifacts.

### Pipeline

```
Input:
  character: {name, visual_description, sprite}
  object: {name, visual_description, sprite}
  action: "carry" or "ride"

Step 1 — LLM generates scene description (~15 output tokens):
  System (carry):
    "You write visual descriptions for a sprite image generator.
    A character is carrying an object. You receive descriptions of both.
    Write a visual description of the character holding/carrying the object
    as a single scene. Reference specific visual details from both descriptions.
    Under 25 words."
  System (ride):
    "...A character is riding a mount...sitting on/riding the mount..."
  User: "Character: {name} — {desc}\nObject/Mount: {name} — {desc}"

Step 2 — Assemble prompt:
  STYLE + llm_output + SUFFIX

Step 3 — Prepare references:
  Character sprite → 256x256 white background (may need horizontal flip to face right)
  Object sprite → 256x256 white background (may need flip to match character direction)

Step 4 — FLUX /v1/images/edits:
  image1 = character (always first, T10)
  image2 = object/mount (always second, T20)

Step 5 — BG removal + crop to 512x512
```

### Key Details

- **Character always img1 (T10)**, object/mount always img2 (T20). No LLM ordering needed.
- **Pre-flip reference images** so character and object face the same direction before sending to FLUX. Prompting "facing right" makes results worse.
- **Don't include both object name AND description** in the prompt — causes duplication. The LLM scene description naturally avoids this.
- Works for any character, not just the player — tested with generated goblin character. Supports monster-rides-monster.

## Use Case 3: Destruction

Single-image edit: transform an object into its destroyed form. Only one reference image needed.

### Experiment Summary (4 rounds, ~140 images)

- **Round 1-2**: Tested template prompts ("destroyed version of...", "broken into debris..."). Templates all reproduce the intact object — FLUX ignores destruction language and just reproduces the reference. Only LLM-generated descriptions work.
- **Round 3**: Tested 4 LLM instruction variants with increasing emphasis on "not the intact object." `llm-contrast` ("must look NOTHING like the original shape") was best but lost the paper cutout art style.
- **Round 4**: Tested contrast variants with paper cutout style reinforced. **`contrast-explicit` wins** — explicitly mentions "mixed media collage paper cutout" in the LLM instruction and asks for specific color/material references.

**Root cause**: FLUX Kontext treats reference images as strong visual anchors. When the text prompt describes something similar to the reference (a broken pot still looks like a pot), FLUX defaults to reproducing the reference. The LLM must generate a description that's **visually distinct from the original shape** while keeping the same colors/materials. The reference image provides color/material continuity; the LLM description provides the new destroyed form.

### Pipeline

```
Input:
  object: {name, visual_description, destruction_result_name, sprite}

Step 1 — LLM generates destruction description (~15 output tokens):
  System instruction:
    "You write visual descriptions for a mixed media collage paper cutout game.
    An object was smashed. Describe the debris as a single paper cutout sprite.
    The debris must look completely different from the original object's silhouette.
    It should be a low, flat pile or scatter of broken fragments.
    Reference the original's specific colors and material textures.
    Under 20 words."
  User: "Object: {name} — {visual_description}\nDebris name: {destruction_result_name}"

Step 2 — Assemble prompt:
  STYLE + llm_output + SUFFIX

Step 3 — Prepare reference:
  Object sprite → 256x256 white background

Step 4 — FLUX /v1/images/edits:
  image1 = object sprite

Step 5 — BG removal + crop to 512x512
```

### Key Details

- **LLM prompt is mandatory** — templates reproduce the intact object regardless of destruction language.
- The LLM instruction must explicitly say the output should look **"completely different from the original object's silhouette"** — without this, the LLM generates descriptions too close to the original and FLUX reproduces the reference.
- The LLM instruction must mention the **art style** ("mixed media collage paper cutout") — without this, the LLM generates realistic descriptions that break the game's aesthetic.
- The reference image provides **color and material continuity** — the debris matches the original's palette without explicit instruction.
- `destruction_result_name` from the creation pipeline gives the LLM the right concept (e.g., "splinters", "glass shards", "puddle of water").

## Key Constraints (All Use Cases)

- **Art style prefix/suffix always in template**, never LLM-generated
- **Prompts under ~25 words** for visual description — longer dilutes reference influence
- **Reference images: 256x256 on white background** — fewer artifacts than 512 or transparent
- **The prompt must reference specific visual details** — generic descriptions don't give FLUX enough direction
- **FLUX Klein (4B) has limited capacity** — some combinations don't work regardless of prompting. FLUX.2-dev would likely improve results.

## Cost Per Use Case

| Use case | LLM calls | FLUX | BG removal | Total |
|----------|-----------|------|------------|-------|
| Combination | 2 parallel (~55ms) | ~180ms | ~65ms | ~300ms |
| Carry/Ride | 1 (~55ms + ~15 tokens) | ~180ms | ~65ms | ~350ms |
| Destruction | 1 (~55ms + ~15 tokens) | ~180ms | ~65ms | ~300ms |

## Reproduction

```bash
cd backend && uv run python scripts/bench_combine.py      # Object combination experiments
cd backend && uv run python scripts/bench_carry_ride.py    # Carry/ride experiments
```

Output: HTML dashboards in `experiments/combine/` and `experiments/carry_ride/`.
