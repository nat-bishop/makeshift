---
name: developing-godot
description: >
  GDScript reference, programmatic scene/script generation, engine quirk
  workarounds, and visual verification for Godot 4 projects. Use when writing
  or modifying GDScript files, creating Godot scenes programmatically, or
  debugging Godot engine behavior.
---

# Godot Development

Reference files are in `${CLAUDE_SKILL_DIR}/`. Load progressively — read each file only when its topic becomes relevant.

## Before writing any GDScript

Read `quirks.md` (engine gotchas) and `gdscript.md` (language reference).

## When creating or modifying scenes programmatically

Read `scene-generation.md` for the headless builder pattern (extends SceneTree → build nodes → pack → save .tscn).

## When creating or modifying scripts

Read `script-generation.md` for runtime script patterns (lifecycle methods, @onready, signal connections).

## When doing both scenes and scripts

Also read `coordination.md` — scenes must be generated first (they create the nodes that scripts attach to).

## API reference

| File | Content |
|------|---------|
| `doc_api/_common.md` | Index of ~128 common Godot classes |
| `doc_api/_other.md` | Index of ~732 remaining classes |
| `doc_api/{ClassName}.md` | Full reference for a specific class |

Scan the index first, then load the specific class file.

Bootstrap: `bash ${CLAUDE_SKILL_DIR}/tools/ensure_doc_api.sh`

## When generating game assets

Read `asset-gen.md` for prompt templates, CLI reference, and model selection (flash vs pro).
Read `asset-planner.md` for sizing, prioritization, and common mistakes.

Requires `GOOGLE_API_KEY` in environment. Install deps: `uv pip install -r ${CLAUDE_SKILL_DIR}/tools/requirements.txt`

## Visual verification (optional)

| File | Purpose |
|------|---------|
| `test-harness.md` | Writing SceneTree test scripts |
| `capture.md` | Headless screenshot/video capture |
| `visual-qa.md` | Automated screenshot analysis via Gemini (requires GOOGLE_API_KEY) |

## Commands

```bash
# Import assets (must run before scene builders):
timeout 60 godot --headless --import

# Run a scene builder:
timeout 60 godot --headless --script <builder.gd>

# Validate all scripts compile:
timeout 60 godot --headless --quit 2>&1
```

## Error handling

- `Parser Error` — syntax error, fix the indicated line
- `Invalid call` / `method not found` — wrong node type or API, look up class in `doc_api`
- `Cannot infer type` — `:=` used with Variant-returning function, see `quirks.md` type inference section
- Script hangs — missing `quit()` in scene builder
