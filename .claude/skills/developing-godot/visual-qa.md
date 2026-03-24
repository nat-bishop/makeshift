# Visual Quality Assurance

Verify game screenshots by reading them directly with Claude Code's multimodal vision.

## Workflow

1. Capture screenshots using the capture system (see `capture.md`)
2. Read the screenshot PNGs — Claude Code sees images natively
3. If a reference image exists, read it too and compare
4. Check against the checklist below

## What to Look For

### Implementation Quality
- **Grid/uniform placement** where organic arrangement was intended
- **Scale and proportion** issues — everything at uniform/default scale
- **Scene composition** — flat where depth and layering were expected
- **Texture/material application** — stretched, tiled, or carelessly applied materials
- **Camera framing** — doesn't match intended perspective

### Visual Bugs
- Z-fighting: flickering or overlapping surfaces at same depth
- Texture stretching, tiling seams, missing textures (magenta/checkerboard)
- Geometry clipping: objects visibly intersecting
- Floating objects that should be grounded
- Shadow artifacts: detached shadows, shadows through walls, missing shadows
- UI overlapping, truncated text, elements offscreen

### Logical Inconsistencies
- Objects in impossible orientations (sideways, upside-down, embedded in terrain)
- Scale mismatches (tree smaller than character, door too small)
- Misplaced objects (furniture on ceiling, rocks in sky)
- Broken spatial relationships (bridge not connecting, stairs into wall)

### Placeholder Remnants
- Primitive geometry (untextured cubes, spheres) contrasting with surrounding detail
- Default Godot materials (grey StandardMaterial3D, magenta missing shader)
- Debug artifacts (collision shapes, nav mesh, axis gizmos, path lines)
- Orphaned UI elements at default positions

### Motion & Animation (compare consecutive frames)
When frames are captured at known intervals, compare them in sequence:
- **Stuck entities** — same position/pose across multiple frames when movement expected
- **Jitter/teleportation** — large position jumps between consecutive frames
- **Sliding** — position changes but animation pose stays frozen (ice-skating)
- **Physics breaks** — objects passing through walls/floors, endless bouncing
- **Animation mismatches** — walk animation at running speed, idle while moving
- **Collision failures** — objects overlapping that should collide
