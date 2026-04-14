# Phase 1 results

Running log of findings per step. See `PLAN.md` for the test plan.

---

## Step 1.1 — H1 simple-rel (2026-04-13)

**Verdict:** partial. H1 wins cleanly on carry, splits on destruction, loses on combine. Ride is a tradeoff.

**Hypothesis:** img2img prompts should describe only the relationship — the reference images already encode visual detail, so re-describing them wastes tokens and can drag FLUX off the reference.

### Per-pipeline

| Pipeline | Winner | Detail |
|---|---|---|
| **carry** | **H1** | Wins on sword, mushroom, jellyfish. Clean hypothesis win — simple "player holding X" beats the baseline's full re-description. |
| **destruction** | **split** | Wins on clockwork, jellyfish. Loses on tree (H1 left the tree unchanged). Tie on sword (both variants failed — sword still visible in output). |
| **ride** | **tradeoff** | H1 preserves the paper-cutout style better than baseline. But H1 changes the rideable object significantly — fidelity cost for style win. Net: probably H1, cautiously. |
| **combine** | **baseline** | Clean loss for H1. The LLM picked literal template text (`"the form of image 2 constructed from image 1"`) with no specifics, and FLUX showed one reference without blending. Baseline's descriptive prompts (`"a flaming sword, steel longsword's blade forged from fire"`) gave FLUX enough guidance to actually merge. |

### Root cause for the failures

Destruction/tree, destruction/sword, and combine all failed for the same reason: **when the prompt is too minimal, FLUX anchors to the reference image and refuses to transform.** Baseline's verbose re-description isn't just noise — it carries transformation force that pushes FLUX off the input silhouette.

H1's premise is half-right:
- ✅ The reference carries shape, color, and material — don't re-describe.
- ❌ But the prompt still needs *transformation force*: explicit language about the target state (verbs like "smash"/"blend"/"merge", or phrases like "completely destroyed, no trace of original shape").

That second half is essentially hypothesis H4 ("img2img prompts describe transformation, not final state") from the plan. The two hypotheses interact: H1 alone is insufficient for pipelines where the transformation is non-trivial.

### What to do with this

- **Adopt H1 for carry and ride** (ride cautiously — watch fidelity in Phase 2 stacking).
- **Don't adopt H1 for combine.** Keep baseline-style descriptive prompts there.
- **Revisit destruction in Phase 2** as a stack: H1 style minimalism + H4 transformation language ("completely destroyed, no trace of original shape"). Expect this to fix the tree/sword failures without losing clockwork/jellyfish.
- **Combine probably needs its own hypothesis** in a later phase — neither minimal-prompt nor current baseline is great. User flagged combine as lower priority for now.

### Data

- 144 FLUX cells total (36 baseline bases + 108 img2img at 2 variants × 18 cases × 3 seeds)
- Wall time: **58 seconds** (~0.4s/cell — much faster than the 6-8s/cell estimate)
- Seeds produce distinct outputs (MD5-verified), so 3-seed averaging is working
- LLM outputs cached per `(variant, case)` so all 3 seeds of one variant share the same text

---

## Step 1.2 — H12 orient-right (2026-04-13)

**Verdict:** **rejected.** Appending `"facing right in profile, side view"` to the build prompt made the base sprites noticeably worse across all 12 objects. Cascade on img2img not worth evaluating given the base-level damage.

**What went wrong:** the directive is too strong — it appears to be overriding or distorting the object's natural form rather than just rotating the camera. Needs a different intervention if we want consistent orientation.

**Original problem still open:** base sprites don't consistently face the same direction, which misaligns `image 1` vs `image 2` in combine and carry/ride. That failure mode is real, H12's fix just made things worse. Candidates for later:
- Try a softer orientation hint (e.g. "left-to-right reading orientation", or append to the visual description rather than the style block)
- Post-process: detect sprite facing direction after generation and mirror to canonical
- Inject orientation at the img2img stage only (let build do whatever, enforce during composition)

Not Phase 1 material. Revisit in a later phase if combine/carry alignment is still a problem after H1 + other fixes.

### Data

- 90 FLUX cells added (36 H12 bases + 54 img2img cascade)
- Wall time: **46 seconds**

---

## Step 1.3 — H10 lighting 3-way (2026-04-13)

**Verdict:** **no change, keep baseline.** `light-none`, `light-flat` (baseline), and `light-diffused` are visually indistinguishable across all 12 build cases. Cascade on img2img not meaningfully different either.

**What this tells us:** FLUX-klein at 4 inference steps isn't sensitive enough to lighting-directive differences at our sprite scale to matter. The guide's claim that lighting is the most important element is probably true at higher step counts and/or for photorealistic subjects — for 4-step stylised paper cutout sprites, it's noise. BiRefNet mask quality doesn't appear to be meaningfully driven by lighting language either.

**Keep `"flat lighting"` in the baseline build prompt** (parsimony — no reason to remove it, no reason to elaborate).

### Data

- 180 FLUX cells added (72 H10 bases + 108 img2img cascade × 2 base sets)
- Wall time: **63 seconds**

---

---

## Step 1.4 — H13 paper-as-subject (2026-04-13)

**Verdict:** **shipped `H13.hybrid`.** New hypothesis added mid-session after step 1.1 surfaced a specific failure mode: the baseline build prompt (`"A mixed media collage of {name} made from cut paper..."`) makes FLUX composite paper onto realistic objects instead of rendering the subjects *as* paper. Crystal looked like a real crystal with paper stuck to it. Clockwork, flame, jellyfish had the same problem.

**What changed:** restructure the sentence so paper-ness is an attribute of the subject itself, not an additive material layer. Six variants tested:

| Variant | Framing | Result |
|---|---|---|
| `H13.paper-cutout` | `{name}, a paper cutout: ...` (subject-first) | Best aesthetic (runner-up overall) |
| `H13.sculpted` | `{name} sculpted entirely from cut and torn paper...` | Best depth (runner-up overall) |
| `H13.texture-first` | `{name} with torn-paper edges and construction-paper surfaces...` | OK, not best |
| `H13.craft-artwork` | Explicit `"not painted, not photographic"` negative hint | OK, not best |
| `H13.minimal` | `Paper craft {name}: ...` (short) | Lost some recognizability |
| `H13.hybrid` | paper-cutout framing + sculpted's `"subtle shadows where overlapping layers meet"` | **Winner.** Clean cutout aesthetic + depth. |

The hybrid was proposed after the first pass: paper-cutout won on aesthetic, sculpted won on depth, and the hybrid was a cheap attempt to get both. It worked.

**Shipped:**
- `build_text_to_image_prompt` → H13.hybrid phrasing (`backend/app/prompts/image.py:44-56`)
- `IMG2IMG_STYLE` → updated to match (removed `"mixed media collage style"` additive framing, added `"layered construction paper with visible cut edges and subtle shadows where overlapping layers meet"`). Carries the same paper-as-subject principle into every img2img operation without a separate sweep.

### Data

- 216 FLUX cells added (5 H13 variants × 12 objects × 3 seeds = 180; plus 36 hybrid on second pass)
- Wall time: 61 + 20 = **81 seconds total**

---

## Phase 1 summary

| Hypothesis | Verdict | Shipped |
|---|---|---|
| **H1 simple-rel** | Wins carry, wins ride (style), splits destruction, loses combine | ✅ carry + ride (`CARRY_INSTRUCTION`, `RIDE_INSTRUCTION`, `build_carry_ride_prompt`) |
| **H12 orient-right** | Rejected — makes build sprites worse | ❌ |
| **H10 lighting 3-way** | No difference | ❌ (keep `"flat lighting"`) |
| **H13 paper-as-subject (hybrid)** | Clean win on 4 hardest cases (crystal, clockwork, flame, jellyfish) | ✅ `build_text_to_image_prompt` + `IMG2IMG_STYLE` |

**Phase 1 total:** 630 FLUX cells, ~248 seconds wall time across 4 steps.

**Open problems carried forward:**
1. Combine is weak — neither baseline nor H1 is great. Needs its own hypothesis, not covered by current plan.
2. Destruction fails on objects where the prompt can't overcome the reference (tree stayed a tree, sword stayed a sword). Hypothesis: H1-style minimalism + H4-style transformation language will fix this.
3. Orientation consistency between combined refs is still an issue. H12 was the wrong fix; needs a different approach.
