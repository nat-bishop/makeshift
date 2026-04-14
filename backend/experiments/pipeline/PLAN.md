# Image pipeline prompt test plan

Source guide: https://docs.bfl.m/guides/prompting_guide_flux2_klein
(Note: guide url is `docs.bfl.ml` — typo-safe)

**Scope:** iterate on the five image-generation prompts — `build` (text-to-image), `destruction`, `carry`, `ride`, `combine` (all img2img) — against the FLUX2-klein prompting guide.

**Method:** phased single-variable sweeps, winner stacking, then prose test against the optimised stack. Scientific rigor over running everything at once.

---

## Execution plan

### Phase 1 — Single-variable sweeps

One hypothesis at a time, everything else frozen to baseline. Run order prioritises the three hypotheses that target actual observed failure modes (duplication, edge quality, orientation).

| Step | Hypothesis | Applies to | Cascade? | Rough cost |
|---|---|---|---|---|
| **1.1** | **H1** simple-rel | img2img only | no | ~110 FLUX calls |
| **1.2** | **H12** orient-right | build + img2img re-run on oriented base sprites | yes | ~170 calls |
| **1.3** | **H10** lighting 3-way (`none` / `flat` / `diffused`) | build + img2img re-run on each lighting's base sprites | yes | ~250 calls |

Cascade note: H12 and H10 are build-level interventions that change the reference sprites fed to img2img. To measure their *real* effect (not just "do build sprites change shape"), the harness re-runs all img2img baselines using the intervention's base sprites as references. H1 has no cascade — img2img-only, base sprites unchanged.

After each step you rate the new cells, export a per-variant summary JSON from the dashboard, and paste it to me. We pick a winner before starting the next step. If a step is ambiguous, we iterate on the variant prompt text before moving on.

### Phase 2 — Winner stacking

Take the winning level of H1, H12, and H10, bake them into a single `phase2-stack` variant per pipeline, and run it against baseline. One combined variant × all cases × 3 seeds. If the stack isn't better than the sum of its Phase 1 parts, interactions exist and we debug.

### Phase 3 — Prose vs optimised stack

H2 (flowing) and H8 (full-prose) are structural rewrites — can't be tested in isolation without confounding with every other choice. Test these **against the Phase 2 stacked winner**, not against the original baseline. The question is "does prose beat the optimised template", not "does prose beat the unoptimised template".

Phase 3 likely also pulls in H11 (`style-mood-suffix`), since it's another prompt-structure variant.

### Phases 4+ (deferred)

Remaining hypotheses — H3 (subject-first), H4 (transformation), H5 (image-refs), H6 (terse), H7 (action-first), H9 (texture-rich) — only get tested if Phase 1/2/3 leave gaps. Many of these overlap with Phase 1 winners and won't need their own sweep.

---

## Controls

- **Seeds:** every `(variant, case)` combo is rendered at **3 fixed seeds** (`[1, 2, 3]`) to separate prompt effects from FLUX noise. Seed is passed through a `ContextVar` in `local_image.py` to `/v1/images/generations` and `/v1/images/edits`. If the SGLang server ignores the `seed` field we'll see it on the first run and fall back to treating the 3 renders as independent samples.
- **Base sprite reuse:** each build variant's output is cached to `experiments/pipeline/_base/{build-variant}/{object}-s{seed}.png` and reused as input to img2img steps. H1 reuses the baseline bases. H12/H10 generate their own bases and pipe them to the cascade.
- **LLM output determinism:** LLM description calls are cached on disk by `(variant-label, case-id)` so all 3 seeds of one variant share the *same* LLM text — isolates FLUX randomness from LLM randomness. Cache invalidates when you edit a variant's prompt in the harness.
- **Production code untouched:** variants are applied by monkey-patching `app.images.pipeline` (not `app.prompts.image`, since `pipeline.py` binds those names at import time). Harness-local. Zero shipping risk until a winner lands.

---

## Success signal

Subjective, judged by eye across 3 seeds. Each rendered sprite gets **three 1–5 rating axes + an optional note**, persisted in `localStorage`:

1. **Fidelity** — does the sprite match the intended subject / interaction / transformation?
2. **Style** — does it match the paper cutout aesthetic (clean cut edges, visible craft materials, flat lighting)?
3. **Usability** — is it a usable game sprite? Framing, silhouette clarity, orientation, background-removal-friendly edges.

Dashboard aggregates as `variant → {fidelity, style, usability, mean, n, notes[]}`. Top-of-page **"Copy summary JSON"** button dumps the aggregate to clipboard:

```json
{
  "combine.baseline":    {"fidelity": 3.2, "style": 3.6, "usability": 3.1, "mean": 3.30, "n": 18, "notes": []},
  "combine.simple-rel":  {"fidelity": 4.1, "style": 3.8, "usability": 4.3, "mean": 4.07, "n": 18, "notes": ["flame+sword s2 — best"]}
}
```

Paste that to me → winner is obvious without squinting at thumbnails.

**Sprite IDs:** `{pipeline}.{variant}/{case}#s{seed}` — use these to reference specific cells in notes and chat. Example: `combine.simple-rel/flame+sword#s2`.

---

## Test catalog

Shared across all pipelines where applicable. Split into easy / hard tiers so variants get exercised on both concrete and abstract subjects.

### Easy tier
- `flame` — bright orange fire with flickering tongues and ember particles
- `crystal` — translucent purple crystal with geometric facets and inner glow
- `sword` — steel longsword with leather-wrapped hilt and gleaming blade
- `tree` — gnarled oak tree with twisted branches and thick roots
- `skull` — weathered human skull with cracked bone and hollow eye sockets
- `mushroom` — red-capped forest mushroom with white spots and pale stem

### Hard tier — conceptually strange / abstract / hard to visually merge
- `shadow` — living silhouette of darkness with wispy tendrils at its edges
- `song` — shimmering ribbon of translucent musical notes trailing golden sparks
- `cloud` — fluffy white cumulus with soft cotton texture and faint blue underbelly
- `clockwork` — tangle of brass gears, tiny pistons, and coiled springs held in an open frame
- `jellyfish` — translucent pink bell with trailing filament tentacles and glowing spots
- `bookworm` — fat pale grub emerging from a chewed leather-bound tome, paper scraps clinging to it

### Build cases
All 12 objects above.

### Destruction cases (4)
`sword`, `tree`, `clockwork`, `jellyfish`. Debris name = `{object} debris`.

### Carry cases (4)
`sword`, `mushroom`, `clockwork`, `jellyfish`.

### Ride cases (4)
`tree`, `skull`, `cloud`, `jellyfish` (ride-a-jellyfish is a stress test).

### Combine pairs (6 — mix of tiers)
- **Easy × easy:** `flame + sword`, `crystal + skull`
- **Easy × hard:** `flame + cloud`, `tree + clockwork`
- **Hard × hard:** `shadow + song`, `jellyfish + bookworm`

---

## Appendix A — Full hypothesis list

Numbered for reference. Phase 1 runs H1, H12, H10. Phase 3 runs H2/H8/H11. Phase 4+ (if needed) runs the rest.

### H1. Simplify multi-ref prompts — refs carry detail, prompt describes relationship
**Pipelines:** carry, ride, combine, destruction. **Phase:** 1.
**Current failure:** LLM re-describes both objects in full — wasting tokens the reference image already encodes, and sometimes overriding the reference with stale description details.
**Variant `simple-rel`:** LLM outputs only the relationship, not visual details. Examples:
- Carry: `"the player holding the sword"` (not "the player holding a steel longsword with leather-wrapped hilt")
- Combine: `"a flame sword — the material of image 1 shaping the form of image 2"`
- Destruction: `"broken fragments of the object in the reference"`

### H2. Flowing paragraphs beat template fragments
**Pipelines:** build (primary), img2img (secondary). **Phase:** 3.
**Variant `flowing`:** LLM writes a single prose paragraph that weaves subject + visual + style naturally. No comma-chained tag suffix.

### H3. Lead with the subject, not the style
**Pipelines:** build, all img2img. **Phase:** 4+.
**Variant `subject-first`:** `"{name}. {visual}. Styled as..."` and `"{llm_desc}. {STYLE}. {SUFFIX}"`.

### H4. Img2img prompts describe transformation, not final state
**Pipelines:** carry, ride, combine, destruction. **Phase:** 4+.
**Variant `transformation`:** destruction → "Smash the object in the reference into a low pile of debris fragments." Carry → "Place image 2 into image 1's hands."

### H5. Explicitly reference images by position
**Pipelines:** carry, ride, combine. **Phase:** 4+.
**Variant `image-refs`:** prompts say "image 1", "image 2" explicitly.

### H6. Terse prompts for img2img
**Pipelines:** img2img. **Phase:** 4+.
**Variant `terse`:** hard cap at 15 words, no style wrapper (or minimal style suffix only). Guide: short 10–30 word prompts work for quick concepts.

### H7. Word order — lead with subject and action
**Pipelines:** all LLM-generated descriptions. **Phase:** 4+.
**Variant `action-first`:** instruction explicitly says "lead with the subject and the action, then details".

### H8. Full prose, no template
**Pipelines:** build (primary), img2img (secondary). **Phase:** 3.
**Variant `full-prose`:** LLM writes the *entire* FLUX prompt as a single paragraph. No `STYLE`/`SUFFIX` wrappers — instruction tells the LLM the target aesthetic and lets it compose prose naturally. **Requires pipeline.py refactor** (the hardcoded `f"{IMG2IMG_STYLE}, {llm_desc}, {IMG2IMG_SUFFIX_*}"` assembly needs to become overridable).

### H9. Texture-rich descriptions
**Pipelines:** build, combine. **Phase:** 4+.
**Variant `texture-rich`:** LLM instructed to include 1–2 tactile/material/surface details per object (e.g. "rough-hewn bark", "waxy petals", "pitted iron").

### H10. Lighting specification affects edge cleanliness and BiRefNet bg removal
**Pipelines:** build, all img2img. **Phase:** 1 (step 1.3).
**Current:** build prompt says `"flat lighting"`, img2img has no lighting mention.
**Variants (3-way sweep):**
- `light-none` — no lighting mention at all
- `light-flat` — current baseline
- `light-diffused` — `"even diffused lighting, no harsh shadows, no cast shadows"` — hypothesis: cleaner edges → fewer BiRefNet mask artifacts
**Extra metric:** log BiRefNet raw vs. processed byte count per sprite — large deltas may indicate mask quality regressions.

### H11. Trailing `Style: … Mood: …` annotation block
**Pipelines:** build, img2img. **Phase:** 3.
**Variant `style-mood-suffix`:** LLM writes prose description; harness appends `"Style: mixed media paper cutout collage, cut paper and cardboard, visible scotch tape and glue, flat lighting, side view. Mood: playful, crafted, handmade."` as a separate trailing block.

### H12. Explicit orientation in prompt
**Pipelines:** build (primary), img2img (cascade). **Phase:** 1 (step 1.2).
**Problem:** base sprites don't consistently face the same direction → combine/carry results misalign when `image 1` faces left and `image 2` faces right.
**Variant `orient-right`:** append `"facing right in profile, side view"` to build; add `"all subjects facing right in profile"` to img2img.
**Cascade check:** after build sweep, eyeball the base sprite row — do all 12 objects now face right? If yes, re-run the img2img baselines on the oriented bases and compare to the original baselines — does composition quality improve?

---

## Appendix B — Variant matrix (reference, not execution order)

Execution order is governed by the phase plan above. This table is here for visual reference of which hypotheses touch which pipelines.

| Pipeline    | baseline | simple-rel | flowing | subject-first | transformation | image-refs | terse | action-first | full-prose | texture-rich | light-none | light-diffused | style-mood-suffix | orient-right |
|-------------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| build       | ✓ |   | ✓ | ✓ |   |   |   | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| destruction | ✓ | ✓ |   | ✓ | ✓ |   | ✓ |   | ✓ |   |   | ✓ |   | ✓ |
| carry       | ✓ | ✓ |   | ✓ | ✓ | ✓ | ✓ |   | ✓ |   |   | ✓ |   | ✓ |
| ride        | ✓ | ✓ |   | ✓ | ✓ | ✓ | ✓ |   | ✓ |   |   | ✓ |   | ✓ |
| combine     | ✓ | ✓ |   | ✓ | ✓ | ✓ | ✓ |   | ✓ | ✓ |   | ✓ |   | ✓ |
