# Asset Planner

Analyze a game's visual needs and generate assets within a budget.

## Setup

Read `${CLAUDE_SKILL_DIR}/asset-gen.md` for CLI reference and prompt templates.

## Workflow

### 1. Identify visual elements

Review the game's scenes and design to build an asset list:
- **Textures**: ground surfaces, walls, UI backgrounds — flat materials that tile
- **Backgrounds**: sky panoramas, parallax layers, title screens, large scenic images — use pro image with `--size 2K` and an appropriate `--aspect-ratio`
- **Sprites**: characters, objects, items — single images or sprite sheets

### 2. Prioritize and budget

Each asset costs:
- Texture: 7 cents (1K image)
- HQ texture / background: 10 cents (2K image with `--size 2K`)
- Large map / panorama: 15 cents (4K image with `--size 4K` — one large image can replace several smaller ones)

Prioritize by visual impact — what makes the game recognizable. Cut low-impact assets first if budget is tight. Reserve ~10% of budget for retries.

### 3. Understand art direction

If an art direction has been established, use it as context when crafting each asset prompt — but do NOT mechanically prepend it. Different asset types need different prompting:
- **Textures** often need no style language at all — describe the material and tiling properties
- **Backgrounds/panoramas** benefit most from art direction language
- **Sprites** may need some style cues but adapted to the subject

Craft each prompt for its specific goal. The art direction tells you the visual identity; translate it appropriately per asset type.

### 4. Generate and review

Use the asset-gen instructions for prompt templates, CLI commands, and review guidance. Generate all images in parallel, review each PNG, regenerate bad ones (max 1 retry each).

#### Common Mistakes

- **Detailed image shrunk to a tile** — generating a richly detailed image then scaling it down to a small tile makes details tiny and clunky. Generate with shapes and level of detail appropriate for the target display size.
- **Tiling texture for a unique background** — don't tile a small repeating texture where the game needs a single scenic background. Use a Pro image instead.
- **Sprite sheets for particle effects** — fire, smoke, water, and similar effects look better as procedural particles or shaders. Don't waste a sprite sheet on them unless the game style calls for it.
- **Image where procedural drawing works** — pure geometric primitives (solid-color rectangles for health bars, single-color circle for a ball, straight divider lines) should be drawn in code. But anything with texture, detail, or artistic style — characters, backgrounds, terrain, objects, icons — should use generated assets even if you *could* approximate it with code. Procedural vector art almost always looks worse than a generated image.
- **Stretching one texture over a large area** — a small texture stretched across a big surface looks blurry. Use a tileable texture or generate at higher resolution.
- **Multiple sprite sheets for one character** — the generator cannot reproduce the same character across separate generations. It will look like two different characters. Put all animations for one character into a single sprite sheet (multiple actions across rows).

### 5. Track assets (optional)

Keep an asset manifest to track what was generated and its intended in-game size:

- **Textures:** tile size in pixels or meters, e.g. `2m tile`
- **Backgrounds:** pixel dimensions to display at, e.g. `1920x1080` (fullscreen), `2560x720` (parallax layer)
- **Sprite sheets:** per-frame display size in pixels, e.g. `128x128 px` (player), `64x64 px` (item)

```markdown
## Textures

| Name | Description | Size | Image |
|------|-------------|------|-------|
| grass | green meadow | 2m tile | assets/img/grass.png |

## Backgrounds

| Name | Description | Size | Image |
|------|-------------|------|-------|
| forest_bg | dense forest panorama | 1920x1080, fullscreen | assets/img/forest_bg.png |

## Sprites

| Name | Description | Size | Image |
|------|-------------|------|-------|
| knight | armored knight walk cycle | 128x128 px per frame | assets/img/knight.png |
```
