---
name: Documentation Drift Patterns
description: Where docs drift from code and what to check — updated after April 2026 knowledge base reorganization
type: project
---

## Documentation structure (as of April 2026 reorg)

**CLAUDE.md** (~60 lines) is a lean routing guide + gotchas. It does NOT contain:
- Detailed architecture prose (that's in docs/)
- Enum values, dict contents, data model fields (readable from code)
- Environment variables (readable from .env.example)
- Full command list (use `make help`)

**docs/index.md** is the knowledge base entry point — lists all files with "when to read it" guidance.

**docs/** contains implementation docs (flat), **docs/research/** has background research, **docs/archive/** has historical data.

## What to check when auditing

### CLAUDE.md drift triggers

CLAUDE.md is routing info only. It drifts when:
- **New backend modules created/deleted** — check the `backend/app/` file routing list
- **New Godot autoloads or systems added** — check the autoload and systems lists
- **New gotchas discovered** — only add if NOT findable by reading code

### docs/ drift triggers

| Trigger | Files to check |
|---------|---------------|
| `GameObjectBlueprint` fields change | `docs/creation-pipeline.md` (call list), `docs/engine-primitives.md` (properties) |
| `creator/questions.py` token caps or prompt style change | `docs/creation-pipeline.md` visual description example + token count |
| `images/pipeline.py` prompt template changes | `docs/creation-pipeline.md` visual description example |
| Image backends added/removed | `CLAUDE.md` images/ line, `README.md` prerequisites, project overview blurb in both files |
| New img2img use-case functions added | `docs/creation-pipeline.md` spawn integration section, `docs/image-combination.md` |
| `engine/behavior.py` changes call structure | `docs/architecture.md` (staged evaluation), `docs/creation-pipeline.md` (call budgets) |
| New WS message types added | `CLAUDE.md` ws/handler.py line |
| `AffordanceSystem` mechanic changes | `docs/engine-primitives.md` (affordances section) |
| New states added to `models/state.py` | `docs/engine-primitives.md` (states table) |
| Eval system changes | Verify `make eval-*` commands in CLAUDE.md match Makefile |

### Quick verification sources

- Autoloads: `godot/project.godot [autoload]` section
- Backend modules: `ls backend/app/*/`
- Make commands: `make help`
- API endpoints: `backend/app/routers/`
- Env vars: `.env.example`

## Historical lesson

CLAUDE.md used to be 174 lines duplicating code details (enum values, dict contents, all env vars, full data model). This made it drift constantly because every code change required a CLAUDE.md update. The April 2026 reorg trimmed it to routing info only — details live in code and docs/, reducing the drift surface.
