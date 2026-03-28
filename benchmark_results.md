# LLM Model Benchmark Results (Novel Prompts Only)

All 10 prompts are NOT in the system prompt examples. Each test was run individually (sequential, not batched) to get accurate timing.

**Note:** Earlier tests of Qwen 9B and 9B-FP8 were invalid — docker compose wasn't reading `.env` from the project root (fixed by adding `--env-file .env` to the COMPOSE variable in Makefile). The 9B results from before the fix were all running the same 9B BF16 model regardless of what `.env` said.

---

## Summary Table

| Config | Avg Time | Avg Bhv | Bhv Rate | Unique Actions | Notes |
|--------|----------|---------|----------|----------------|-------|
| **Gemini Flash Lite** | **2.55s** | **1.6** | **10/10** | ATTRACT, ADD_TAGS, PATROL, SPAWN_PROJ, MOVE, DEAL_DMG | Cloud, best quality |
| **35B-FP8 instruct (t=0.7)** | **2.01s** | 1.4 | 10/10 | APPLY_FORCE, DEAL_DMG, SPAWN_PROJ, MOVE, EXPLODE | Fastest, reliable |
| **35B-FP8 reasoning (t=1.0)** | 2.28s | 1.0 | 6/10 | ATTRACT, MOVE_AWAY, ON_TAG_ADDED, SPAWN_PROJ, ADD_TAGS | Most creative when it fires, but unreliable |
| **35B-FP8 thinking mode** | 5.83s | 1.1 | 6/10 | ATTRACT, ADD_TAGS, MOVE, DEAL_DMG | 3x slower, no quality gain |

---

## Gemini 3.1 Flash Lite Preview (cloud, presence_penalty=0)

| # | Prompt | Time | Tags | #Bhv | Behaviors | Size |
|---|--------|------|------|------|-----------|------|
| 1 | rubber duck | 2.73s | FLEXIBLE, LIGHT, FLOATING | 1 | ALWAYS→MOVE_TOWARD "The duck bobs along the water." | tiny |
| 2 | cursed mirror | 3.27s | SOLID, RIGID, REFLECTIVE, GLOWING | 1 | ON_PROXIMITY→ATTRACT "The mirror pulls you in..." | medium |
| 3 | angry bee swarm | 2.15s | LIVING, LIGHT, FLAMMABLE | 2 | ALWAYS→MOVE_TOWARD(high); ON_CONTACT→DEAL_DAMAGE | small |
| 4 | tesla coil | 2.05s | SOLID, RIGID, CONDUCTING, ELECTRIC | 1 | ON_PROXIMITY→SPAWN_PROJECTILE(high) "A bolt of electricity arcs out!" | medium |
| 5 | sentient cactus | 2.19s | LIVING, SOLID, SHARP, RIGID | 2 | ALWAYS→MOVE_TOWARD; ON_CONTACT→DEAL_DAMAGE "pricked by a sharp spine!" | small |
| 6 | lava lamp | 3.42s | SOLID, GLOWING, HEAT_SOURCE | 1 | ALWAYS→MOVE_TOWARD(low) "The lamp glows and shifts..." | small |
| 7 | haunted lantern | 2.54s | FLOATING, GLOWING, COLD, LIVING | 2 | ALWAYS→MOVE_TOWARD; ON_CONTACT→DEAL_DAMAGE "Cold spectral energy!" | small |
| 8 | slime blob | 2.62s | LIVING, LIQUID, FLEXIBLE, CORROSIVE | 2 | ALWAYS→MOVE_TOWARD(low); ON_CONTACT→ADD_TAGS(STICKY) | small |
| 9 | clockwork spider | 2.19s | LIVING, SOLID, RIGID, SHARP | 2 | ALWAYS→PATROL; ON_PROXIMITY→DEAL_DAMAGE | small |
| 10 | poison dart frog | 2.31s | LIVING, TOXIC, FLEXIBLE | 2 | ALWAYS→MOVE_TOWARD; ON_CONTACT→DEAL_DAMAGE | tiny |

**Avg: 2.55s | 1.6 bhv | 3.5 tags | 10/10 behavior rate**

---

## Qwen3.5-35B-A3B-FP8 — Instruct Mode (temp=0.7, top_p=0.8, thinking=off)

| # | Prompt | Time | Tags | #Bhv | Behaviors | Size |
|---|--------|------|------|------|-----------|------|
| 1 | rubber duck | 2.59s | SOLID, FLEXIBLE, BOUNCY, FLOATING | 1 | ON_CONTACT→APPLY_FORCE "The duck bounces!" | small |
| 2 | cursed mirror | 1.53s | SOLID, RIGID, REFLECTIVE, TOXIC | 1 | ON_CONTACT→DEAL_DAMAGE "The mirror drains your life!" | medium |
| 3 | angry bee swarm | 2.67s | LIVING, LIGHT, TOXIC | 2 | ALWAYS→MOVE_TOWARD(high); ON_CONTACT→DEAL_DAMAGE | medium |
| 4 | tesla coil | 1.80s | SOLID, RIGID, ELECTRIC, GLOWING | 1 | ON_CONTACT→DEAL_DAMAGE "ZAP!" | medium |
| 5 | sentient cactus | 2.09s | LIVING, SOLID, SHARP, FLAMMABLE | 2 | ALWAYS→MOVE_TOWARD; ON_CONTACT→DEAL_DAMAGE "Ouch! Sharp spines!" | small |
| 6 | lava lamp | 2.45s | SOLID, HEAT_SOURCE, FLOATING | 1 | ON_DAMAGED→EXPLODE(high) "The lamp bursts into flames!" | medium |
| 7 | haunted lantern | 1.90s | SOLID, GLOWING, LIVING | 2 | ON_CONTACT→DEAL_DAMAGE; ON_DAMAGED→SPAWN_PROJECTILE "Ghostly wail!" | small |
| 8 | slime blob | 1.65s | LIQUID, FLEXIBLE, STICKY | 1 | ON_CONTACT→APPLY_FORCE "The blob sticks!" | small |
| 9 | clockwork spider | 1.89s | SOLID, RIGID, LIVING | 2 | ALWAYS→MOVE_TOWARD; ON_CONTACT→DEAL_DAMAGE "The gears bite!" | small |
| 10 | poison dart frog | 1.49s | LIVING, TOXIC, LIGHT, GLOWING | 1 | ON_CONTACT→DEAL_DAMAGE "The frog's poison stings!" | tiny |

**Avg: 2.01s | 1.4 bhv | 3.5 tags | 10/10 behavior rate**

---

## Qwen3.5-35B-A3B-FP8 — Reasoning Params (temp=1.0, top_p=0.95, thinking=off)

| # | Prompt | Time | Tags | #Bhv | Behaviors | Size |
|---|--------|------|------|------|-----------|------|
| 1 | rubber duck | 1.69s | FLEXIBLE, BOUNCY, FLOATING | **0** | — | small |
| 2 | cursed mirror | 3.34s | SOLID, RIGID, REFLECTIVE, GLOWING, TOXIC | 2 | ON_CONTACT→ATTRACT; ON_PROXIMITY→DEAL_DAMAGE "A spectral force strikes!" | medium |
| 3 | angry bee swarm | 2.71s | LIVING, LIGHT, FLAMMABLE, TOXIC | 2 | ON_CONTACT→DEAL_DAMAGE; ON_TAG_ADDED(HEAT_SOURCE)→EXPLODE | medium |
| 4 | tesla coil | 2.06s | SOLID, RIGID, ELECTRIC, CONDUCTING | 2 | ON_CONTACT→DEAL_DAMAGE; ON_CREATE→SPAWN_PROJECTILE "Arcs fly!" | large |
| 5 | sentient cactus | 2.04s | LIVING, SOLID, SHARP, STICKY | 2 | ON_CONTACT→DEAL_DAMAGE; ON_DAMAGED→MOVE_AWAY "Ouch! It backs away." | medium |
| 6 | lava lamp | 4.10s | LIQUID, HOT, FLOATING, GLOWING | **0** | — (retry occurred) | small |
| 7 | haunted lantern | 1.67s | SOLID, GLOWING, LIGHT, FLAMMABLE | 1 | ON_CONTACT→DEAL_DAMAGE "A wisp of soul escapes!" | small |
| 8 | slime blob | 1.77s | LIQUID, FLEXIBLE, SLIPPERY | **0** | — | small |
| 9 | clockwork spider | 1.69s | SOLID, RIGID, MAGNETIC, LIGHT | 1 | ALWAYS→MOVE_TOWARD NEAREST_OBJECT | small |
| 10 | poison dart frog | 1.76s | LIVING, TOXIC, GLOWING, FLEXIBLE | **0** | — | small |

**Avg: 2.28s | 1.0 bhv | 3.7 tags | 6/10 behavior rate**

---

## Qwen3.5-35B-A3B-FP8 — Thinking Mode (temp=1.0, top_p=0.95, thinking=on)

| # | Prompt | Time | Tags | #Bhv | Behaviors | Size |
|---|--------|------|------|------|-----------|------|
| 1 | rubber duck | 5.76s | (4 tags) | 2 | ADD_TAGS(GLOWING) SELF; ON_CONTACT→DEAL_DAMAGE "Squeak!" | small |
| 2 | cursed mirror | 5.91s | GLOWING, TOXIC + 2 more | 2 | ON_PROXIMITY→ATTRACT "Something pulls you closer..."; ON_CONTACT→DEAL_DAMAGE | medium |
| 3 | angry bee swarm | 5.32s | LIVING, LIGHT, SOLID, SHARP, HOT | 2 | ALWAYS→MOVE_TOWARD; ON_CONTACT→DEAL_DAMAGE | small |
| 4 | tesla coil | 4.93s | ELECTRIC, GLOWING, HEAT_SOURCE, SOLID | **0** | — (used full tag budget: cost=10) | medium |
| 5 | sentient cactus | 4.89s | LIVING, SOLID, FLEXIBLE, SHARP | **0** | — (good tags, no behaviors) | medium |
| 6 | lava lamp | 6.84s | (3 tags) | **0** | — | medium |
| 7 | haunted lantern | 5.51s | (4 tags, named "Spectral Lantern") | **0** | — | small |
| 8 | slime blob | 5.89s | (3 tags) | 1 | ON_CONTACT→ADD_TAGS(STICKY) "You get stuck!" | medium |
| 9 | clockwork spider | 6.37s | (5 tags) | 2 | ALWAYS→MOVE; ON_CONTACT→DEAL_DAMAGE "It bites!" | small |
| 10 | poison dart frog | 6.86s | (4 tags) | 2 | ALWAYS→MOVE; ON_CONTACT→DEAL_DAMAGE "You've been poisoned!" | tiny |

**Avg: 5.83s | 1.1 bhv | ~3.8 tags | 6/10 behavior rate**

---

## Analysis

### Speed
```
35B-FP8 instruct (t=0.7)   ████████████ 2.01s
35B-FP8 reasoning (t=1.0)  █████████████░ 2.28s  (+13%)
Gemini Flash Lite           ███████████████░ 2.55s  (+27%)
35B-FP8 thinking mode       ██████████████████████████████████░ 5.83s  (+190%)
```

### Behavior reliability
- **Instruct t=0.7:** 10/10 — always generates at least 1 behavior
- **Gemini Flash Lite:** 10/10 — always generates behaviors
- **Reasoning t=1.0:** 6/10 — 4 objects got zero behaviors (rubber duck, lava lamp, slime blob, frog)
- **Thinking mode:** 6/10 — 4 objects got zero behaviors (tesla coil, cactus, lava lamp, lantern)

### Behavior creativity (when behaviors ARE generated)
The **reasoning params (t=1.0)** produced the most creative behaviors despite being unreliable:
- `ON_TAG_ADDED(HEAT_SOURCE)→EXPLODE` on bees — fire kills the swarm, emergent gameplay
- `ON_DAMAGED→MOVE_AWAY` on cactus — it flinches and retreats when hit
- `ATTRACT` on cursed mirror — same as Gemini's best behavior
- `MAGNETIC` tag on clockwork spider — attracts metal objects

But 40% of the time it just skips behaviors entirely.

### Tag quality
**Reasoning params** often produced the best tags:
- `CONDUCTING` on tesla coil (correct, Gemini also got this)
- `STICKY` on sentient cactus (spines stick to you — creative)
- `MAGNETIC` on clockwork spider (metallic attraction)
- Better budget usage (more tags per object: avg 3.7 vs 3.5)

**Thinking mode** spent time reasoning but often over-allocated tag budget leaving nothing for behaviors (tesla coil: cost=10 tags, 0 behaviors).

### Conclusion

| Use case | Best config |
|----------|-------------|
| **Production (reliability matters)** | 35B-FP8 instruct t=0.7 — fastest, 100% behavior rate |
| **Quality ceiling** | Gemini Flash Lite — best overall creativity + reliability combo |
| **Local quality** | 35B-FP8 instruct t=0.7 — thinking/reasoning modes are strictly worse (slower + less reliable) |

**Thinking mode is not worth it for this task.** It adds ~4s of latency per request and actually reduces behavior reliability. The model overthinks tags and underspends on behaviors. The reasoning params (t=1.0) show flashes of brilliance but are too unreliable at 60% behavior rate. The instruct defaults (t=0.7, top_p=0.8) hit the sweet spot of speed + reliability for structured output generation.
