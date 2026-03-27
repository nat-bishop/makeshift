# LLM-generated behavior systems for game objects: a research reference

**The core challenge — making LLM-generated game objects act, not just exist — sits at the intersection of several active research areas, but no production system has solved it end-to-end.** GROMIT (UC Berkeley, UIST 2024 Best Paper) is the closest direct precedent, achieving 30–85% success rates generating Unity behaviors at runtime via GPT-4. The research converges on a clear architecture: LLMs should generate structured JSON specifications (not code), selecting from predefined behavior vocabularies, validated through constrained decoding and post-generation constraint satisfaction. GOAP-style flat action definitions and event-condition-action rules represent the sweet spot for reliable LLM generation, while Godot 4's LimboAI addon provides the runtime infrastructure to interpret these specifications. The biggest gap in the literature is precisely the problem stated: structured behavioral specification generation for game entities, as distinct from narrative generation, level design, or agent control.

---

## 1. Prior art: who has tried this and what happened

### GROMIT is the most directly relevant system

GROMIT (Jennings et al., UC Berkeley, UIST 2024) is a **Runtime Behavior Generation (RBG) system** for Unity3D that uses GPT-4 to generate game behaviors at runtime when players trigger interactions with no predefined output. The system generates JSON containing C# MonoBehavior code plus metadata (name, emoji display, plaintext description). Three demo scenarios tested different generation modes: a fully generative sandbox, a partially generative escape room, and an adventure game with generative spell combinations. The adventure game generated **156 functional spells** with an average processing time of **5.6 seconds** per generation.

Reliability handling in GROMIT follows a pragmatic pattern. When generated code fails to compile, the system re-prompts GPT-4 with the compilation error for iterative fixing. Rather than relying solely on prompt engineering, GROMIT programmatically detects consistent LLM failure patterns — GPT-4 reliably omits import statements and class names — and auto-injects defaults before compilation. Success rates varied dramatically by scenario: **85% in the sandbox demo but only 30% in a traffic simulation** requiring spatial reasoning. The paper explicitly identifies the need for "guardrail systems" as future work and notes that the RBG space is "under-explored." Developer interviews (n=13) revealed a split: some saw runtime generation as revolutionary, others as fundamentally incompatible with game design workflows requiring testing and iteration.

### Voyager proved the skill library pattern

Voyager (Wang et al., 2023, NeurIPS Workshop) is the first LLM-powered embodied lifelong learning agent in Minecraft, demonstrating that GPT-4 can build an **ever-growing library of executable behavioral code** indexed by natural language descriptions. Its three-component architecture — automatic curriculum, skill library, and iterative prompting — achieved **3.3× more unique items discovered** and **15.3× faster tech tree progression** versus prior state-of-the-art. Skills are stored as JavaScript functions (using the mineflayer API) and retrieved via embedding similarity when facing new tasks. Complex skills compose simpler ones, creating a hierarchical behavior library.

The iterative prompting mechanism is Voyager's key reliability innovation: generate code → execute in Minecraft → collect environment feedback and execution errors → feed back to GPT-4 → refine code, with self-verification confirming task completion before committing a skill to the library. If stuck after 4 rounds, the curriculum proposes a new task. **GPT-3.5 performed 5.7× worse than GPT-4**, highlighting model capability as a hard constraint. The skill library concept — executable specifications indexed by description, composable, and transferable to new environments — is directly applicable to a behavior specification library for game objects.

### Scribblenauts defined the problem space before LLMs existed

Scribblenauts (5th Cell, 2009) remains the canonical pre-LLM example of this exact problem: generating behavioral specifications for game objects from text input. The **Objectnaut engine** maintained a hierarchical property database of **22,802 objects**, each with physical characteristics, AI behavior rules, and interaction rules. Properties inherited through a taxonomy — all mammals share "organic flesh" — enabling massive content scaling.

The critical lesson from Scribblenauts comes from designer Liz England, who revealed the "mathwashing" reality: despite the sophisticated inheritance system, objects were **"hand authored 1 by 1 with lots of crunch."** Five team members spent six months researching dictionaries to build the database. Testing every interaction was impossible due to combinatorial explosion, so the team focused on fine-tuning item properties for roughly 80% of development time. The "mongoose vs. cobra" anecdote illustrates balance challenges: making the mongoose defeat cobras without making it overpowered against everything else. For an LLM-based successor, the Objectnaut hierarchy (physical characteristics → AI behavior → interaction rules) provides a proven schema, but the hand-authoring bottleneck is exactly what LLM generation should eliminate.

### Generative Agents showed emergent behavior from memory architecture

The Stanford Generative Agents paper (Park et al., UIST 2023) demonstrated that 25 agents in a Sims-like environment could produce emergent social behaviors — autonomously organizing a Valentine's Day party from a single user suggestion — through a memory → reflection → planning architecture. Everything is represented as **natural language**: observations stored with timestamps and importance scores, retrieved by recency/importance/relevance, periodically synthesized into higher-level reflections, then used for top-down plan generation.

For behavioral specification generation, the key insight is that natural language as a universal state representation enables extraordinary flexibility but **does not scale to real-time games** — each interaction requires at least one LLM query. The GROMIT authors cite this directly as a limitation. The memory/reflection architecture is more relevant to persistent NPC behavior over hours than to defining the behavioral spec of a newly-spawned game object.

### Other notable projects and their contributions

**Mark Riedl's STORY2GAME** (Georgia Tech, 2025) uses LLMs to generate interactive fiction through a multi-stage pipeline where actions are annotated with **preconditions and effects** — a structured intermediate representation bridging narrative intent and executable code. This precondition/effect pattern is highly relevant to GOAP-style behavior definitions. **VGDL-based game generation** (Hu et al., IEEE CoG 2024) uses the Video Game Description Language, with its four components (SpriteSet, LevelMapping, InteractionSet, TerminationSet), as a structured output format that constrains LLM generation to a verifiable schema. The **"Craft an Iron Sword"** paper (Microsoft Research, WordPlay 2022) was an early proof-of-concept using Codex to power Minecraft NPCs generating both dialogue and executable JavaScript.

The NPC behavior industry is converging on a pattern of **constrained generation** — personality prompts plus structured action APIs — rather than fully open-ended generation. Inworld.ai provides personality/knowledge control but leaves world interaction to developers. Gigax+Cubzh uses fine-tuned Mistral-7B to output structured actions from a predefined vocabulary.

**Flagged gaps:** "SpatialGen" could not be confirmed as a specific named project. Yolanda Gil's research (USC ISI) focuses on scientific workflows and knowledge capture — tangential to game AI at best. WordPlay is a recurring ACL/EMNLP workshop series, not a single Stanford project. A 2025 WordPlay paper titled "Real-Time World Crafting: Generating Structured Game Behaviors from Natural Language with Large Language Models" appears directly relevant but was not fully accessible.

---

## 2. DSL design: what LLMs can and cannot generate reliably

### Constrained decoding has largely solved the syntax problem

The technical landscape for ensuring LLMs produce valid structured output has matured rapidly. **Constrained decoding** — modifying token probabilities at each generation step to mathematically guarantee schema compliance — is now available from all major providers and open-source frameworks. OpenAI's Structured Outputs (August 2024) achieve **100% schema compliance** via internal constrained decoding. Anthropic launched strict structured outputs in November 2025 for Claude models. Google Gemini supports JSON Schema enforcement through its API.

On the open-source side, **Guidance** (Microsoft) uses Earley's algorithm for context-free grammar parsing, achieving ~50μs per token overhead and 50% faster inference via KV cache reuse. **Outlines** (dottxt) compiles constraints into finite-state machines with precomputed vocabulary indexes, integrated into vLLM and Hugging Face TGI. **XGrammar** (CMU/MLC) achieves <40μs/token for JSON Schema, **up to 100× faster than Outlines**, and is now vLLM's default structured generation engine. The **Instructor** library takes a complementary validation-and-retry approach using Pydantic models, working with any API without requiring logit access.

The JSONSchemaBench benchmark (Geng et al., 2025) found conformance rates of **95–99%** for well-supported engines, with constrained decoding actually speeding generation by 50% (by skipping tokens with only one valid continuation) and improving downstream task accuracy by up to 4%.

### Format restrictions can degrade reasoning quality

A critical tension exists in the literature. The "Let Me Speak Freely" paper (arXiv 2408.02442) found that **format restrictions degrade LLM reasoning by 10–15%** on tasks like GSM8K and logical reasoning — more relaxed prompts yield better results. However, JSONSchemaBench and the Outlines team show constrained decoding *improves* performance by up to 4% on structured tasks. The resolution appears to be task-dependent: for extraction and classification, constrained decoding helps; for complex reasoning, it hurts.

The practical recommendation for behavioral spec generation is a **two-step approach**: let the LLM reason freely about what behaviors an object should have (chain-of-thought in natural language), then format the result into structured JSON. This NL-to-Format pipeline preserves reasoning quality while guaranteeing syntactic validity.

### The Anka paper provides the strongest empirical evidence on DSL design

The Anka paper (arXiv 2512.23214) offers the clearest empirical guidance on designing DSLs for LLM generation. Despite **zero training exposure** to the Anka DSL, Claude 3.5 Haiku achieved **99.9% parse success** and 95.8% overall task accuracy across 100 benchmark problems — with a **40 percentage point accuracy advantage over Python** on multi-step pipeline tasks. The design principles that made this possible directly contradict what makes DSLs easy for human programmers:

- **Explicit, constrained syntax** where each operation has exactly one canonical form
- **Reduced flexibility** — fewer valid patterns means fewer error opportunities
- **Explicit state management** rather than implicit variable tracking
- Features that "might annoy human programmers" substantially improve LLM accuracy

The "How to Constrain Your Dragon" approach (Andreas Mülder, itemis) offers a practical implementation: **transform the DSL into a JSON Schema, let the LLM generate structured JSON output, then serialize back into DSL**. This achieves 100% syntactically correct DSL code by leveraging native provider structured outputs.

### Complexity determines reliability in a clear hierarchy

Research on LLM-generated behavior trees, combined with structured output benchmarks, reveals a clear complexity-reliability tradeoff:

| Complexity level | Expected reliability | Key risk |
|---|---|---|
| Flat trigger→response pairs | >99% with constrained decoding | Limited expressiveness |
| Sequential action lists | 90–95% | Hallucinated actions |
| Simple state machines (3–5 states) | 70–85% | Missing transitions, stuck states |
| Behavior trees (shallow) | 60–80% depending on model | Structural errors, wrong node types |
| Complex nested BTs with parallel/fallback | <50% without fine-tuning | Logic incoherency, defaulting to sequences |

The BTGenBot project (Politecnico di Milano, IROS 2024) found that fine-tuned 7B models can produce functional behavior trees, but the LLM-as-BT-Planner study (TU Munich) showed GPT-3.5 scoring only **1/10 logical coherency on full BT generation** versus GPT-4's perfect 10/10. A key finding from the OpenReview paper on boosting BT generation: **LLMs often fail to generate proper BT structures (fallback/parallel nodes) and default to sequential action lists.**

**JSON is the recommended representation format.** It has universal constrained decoding support, massive training data representation, excellent validation tooling (Pydantic, Zod), and strict typing. YAML saves ~18–50% tokens but has no constrained decoding support from major providers and suffers from whitespace-sensitivity parse errors. XML is the most verbose option (~80% more tokens) and consistently performs worst in LLM benchmarks.

---

## 3. Game behavior representations ranked by LLM-friendliness

### GOAP action definitions are the best fit for LLM generation

**Goal-Oriented Action Planning**, pioneered in F.E.A.R. (Jeff Orkin, GDC 2006), represents behaviors as flat, declarative data structures: each action has a name, preconditions (what must be true), effects (what changes), and a cost. An A* planner finds the cheapest action sequence to reach a goal state. F.E.A.R.'s FSM had only **three states** — Goto, Animate, and UseSmartObject — with all behavioral complexity handled by the planner.

GOAP is exceptionally LLM-friendly for several reasons. Actions are **independent, flat data structures** — adding a new action cannot break existing ones. The world state is a conjunction of key-value pairs mapping perfectly to JSON. The LLM only needs to define building blocks; the runtime planner handles sequencing. Different entity types can share goals but have different action sets — a dragon and a cannon both have "attack_target" as a goal but different available actions.

For the described game, an LLM-generated GOAP spec might look like:
```json
{
  "goals": [{"name": "attack_enemies", "state": {"target_damaged": true}, "priority": "high"}],
  "actions": [
    {"name": "breathe_fire", "preconditions": {"has_target": true, "distance": "close"},
     "effects": {"target_damaged": true, "area_burning": true}, "cost": 3},
    {"name": "fly_toward", "preconditions": {"has_target": true, "distance": "far"},
     "effects": {"distance": "close"}, "cost": 1}
  ]
}
```

The primary disadvantage is debugging — GOAP plans can be surprising, and Crystal Dynamics built extensive debugging tools for their Tomb Raider implementation. The GDC 2015 talk "GOAP: Ten Years Old and No Fear!" details how multiple studios (Monolith for Shadow of Mordor, Crystal Dynamics for Tomb Raider) evolved the original F.E.A.R. approach.

### Event-condition-action rules provide the simplest reliable option

Flat ECA rules, modeled on the Warcraft 3 trigger editor pattern (Event → Condition → Action), represent the highest-reliability option for LLM generation. Each rule is a simple conditional: `{event: "on_collision", condition: {other_has_tag: "flammable"}, action: "ignite_other"}`. These map trivially to JSON schemas with constrained vocabularies, and validation is straightforward — check that all referenced events, conditions, and actions exist in the game's vocabulary.

The WC3 trigger editor proved this pattern scales to complex game logic — entire custom game modes were built from ECA rules — while remaining accessible to non-programmers. The limitation is expressiveness: sophisticated multi-step behaviors or state-dependent decision-making require either many rules or a more powerful representation.

### Behavior trees work but require careful scoping

Multiple 2024–2025 papers validate LLM generation of behavior trees. The "Agents Play Thousands of 3D Video Games" paper (March 2025) uses an iterative LLM→BT→gameplay→reflection→improved BT pipeline. BTGenBot fine-tuned 7B models to generate BTs from natural language. The key constraint is that **LLMs reliably generate simple, shallow trees but struggle with complex nesting and non-sequential control flow**.

For a practical system, the approach should be: define a library of leaf node types (pre-built BTAction and BTCondition subclasses), then have the LLM specify which nodes to compose and their tree structure. This keeps the LLM's task within its reliable capability range — selecting and arranging known components rather than inventing new logic.

### Utility AI and FSMs have specific limitations

**Utility AI** (Dave Mark's Infinite Axis Utility System) offers smooth behavioral blending through scored response curves, but requires mathematical intuition for curve design — something LLMs struggle with. An LLM could generate reasonable defaults for utility scores, but the fine-tuning that makes utility AI feel good requires human expertise.

**Finite State Machines** suffer from combinatorial explosion of transitions — adding one new state may require updating all existing states. For LLM generation, the risk is missing transitions creating stuck states or extra transitions causing unintended behavior. FSMs are best used for simple lifecycle management (idle/active/dying) rather than complex behavioral logic.

### Mod-friendly systems provide proven data schemas

**RimWorld's XML Def system** is arguably the gold standard for data-driven game modding. XML definitions map 1:1 to C# classes, support inheritance (`ParentName`), and use a `<comps>` system for component-based behavior composition. The `workerClass` pattern lets data reference pre-existing code — exactly the model for LLM-generated behavior, where the LLM generates defs that configure existing behavior systems.

**Dwarf Fortress raw files** use a flat token format (`[CREATURE:DOG]`, `[LARGE_PREDATOR]`, `[NATURAL_SKILL:SWIMMING:3]`) that is exceptionally simple and robust against malformed output. Each token is independent and self-describing. **Factorio's prototype system** is purely parametric — you fill in property values for predefined behavior types — making it highly data-driven but limited to configuring existing entity types rather than defining novel behaviors.

---

## 4. Balancing LLM-generated content requires categorical parameters and budget systems

### LLMs are unreliable at generating precise numbers

The evidence strongly supports having LLMs choose from **categorical tiers rather than exact numbers**. Arize research found that GPT-4 "often assigns the highest score regardless of actual error rates" in numeric scoring tasks. MIT CSAIL demonstrated that LLMs produce biased, non-uniform distributions when asked to generate numbers — "many LLMs struggle to induce target distributions." The NumeroLogic paper explains the underlying mechanism: when a model reads a digit token, it cannot determine its place value until the entire number is processed.

Alignment processes (RLHF, instruction tuning) actually **amplify numerical bias** in LLM-generated scores. Ikigai Labs found LLMs "perform consistently worse than random forest models on regression for all datasets" and are "more influenced by categorical values" than numerical ones. The practical recommendation is clear: use categorical tiers (none/low/medium/high/extreme) for behavioral parameters, with the game engine mapping categories to specific numeric values. This reduces variance, eliminates numerical bias, and makes validation trivial.

### Point-buy budget systems provide the constraint framework

Budget systems for LLM-generated behaviors should follow established game design patterns. Each object receives N "behavior points" based on context (description complexity, tier). Behaviors have pre-assigned costs: "flies" might cost 3 points, "explodes on contact" costs 5, "is flammable" costs 1. The LLM selects behaviors that fit within the budget. Key design elements borrowed from tabletop RPGs (GURPS, D&D 3e point-buy):

- **Non-linear cost scaling** prevents stacking all points into one overpowered ability
- **Multiple separate pools** for different trait types (offensive, defensive, mobility)
- **Negative traits** (vulnerabilities, fragility) refund points, enforcing counterplay
- **Counter-play requirements** as hard constraints: any object above a power threshold must include at least one significant vulnerability

Ian Schreiber's game balance research emphasizes that **closed systems** (where the game fully controls resource flow) are far easier to balance than open ones. For LLM-generated objects, this means a fixed budget per object, not a flexible one.

### Post-generation validation through constraint satisfaction

The LLM output should be treated as an initial "proposal" validated against constraints. The pipeline: parse structured output → compute total behavior cost (reject if over budget) → check each parameter is within tier-appropriate range → verify counter-play constraints → if invalid, either clamp values or re-query with tighter instructions. Research on constraint satisfaction for PCG (Smith, University of Bath, 2023; Sorenson et al., IEEE TCIAIG) shows that finite-domain constraint solvers are effective but have difficulty with numeric data — another argument for categorical parameters.

**Automated simulation-based testing** is an emerging complement: spawn batches of LLM-generated objects, simulate interactions, flag objects that dominate all interactions (win rate above threshold) or have no meaningful interactions. The "Dungeons & Replicants" paper (2023) demonstrates training generative models on real player behavior to create "replicants" that test balance automatically.

### Handling adversarial and edge-case inputs

The action-selector pattern from Beurer-Kellner et al. (2025) provides the strongest defense against prompt injection: the LLM selects from **pre-approved behaviors rather than generating free-form mechanics**. Raw player text should never reach the game engine — always mediated through structured output with constrained vocabulary. For bizarre inputs ("time-traveling explosive pineapple"), hierarchical categorization — first classify into a broad category (tool, creature, vehicle), then apply category-specific behavior templates — mirrors Scribblenauts' Objectnaut hierarchy while leveraging LLM flexibility. Graceful degradation to basic physics objects (solid, gravity-affected, non-interactive) provides a safe fallback.

---

## 5. Godot 4 implementation requires an interpreter layer over LimboAI

### The no-eval constraint shapes the entire architecture

Godot 4 **does not support runtime GDScript evaluation** — confirmed by GitHub Issue #22814, open since 2018 and still unimplemented. Platform constraints (iOS, WebAssembly, consoles) block JIT/AOT approaches. This means an LLM cannot generate GDScript for runtime execution. All behavior must flow through an interpreter layer.

Godot's **Expression class** provides the closest thing to runtime eval: mathematical expressions, boolean logic, built-in method calls, and user method calls on a base instance. Variables can be bound at parse time and values supplied at execution. However, it **lacks control flow** (no if/else, no loops), cannot define variables or functions, and is limited to single expressions. For behavior conditions like `"health < 50 && distance_to_target < 100"`, Expression works well. For anything more complex, the command/interpreter pattern is required.

### LimboAI is the strongly preferred behavior tree addon

**LimboAI** (v1.6.0, MIT license) is a C++ behavior tree and state machine addon supporting Godot 4.2–4.6. Its resource-based architecture is critical for runtime-generated behaviors: `BehaviorTree` resources can be built programmatically via `set_root_task()`, and `BTPlayer` nodes can swap behavior tree instances at runtime via `set_bt_instance()`. The addon includes:

- Combined behavior trees and hierarchical state machines (LimboHSM)
- Advanced blackboard system with scoping, variable mapping, and typed parameters
- `BTSubtree` for modular composition (though subtrees cannot be updated at runtime)
- Visual debugger with real-time tree inspection and per-instance performance monitors
- Custom tasks created by extending BTAction/BTCondition in GDScript

The recommended pattern: pre-define a library of BTAction/BTCondition task types (MoveToward, Attack, Flee, Patrol, EmitParticles, etc.), then have the LLM generate JSON specifying which tasks to compose into a tree. A factory function builds the BehaviorTree resource programmatically from this spec.

**Beehave** (pure GDScript, node-based) is less suitable — its scene-tree architecture makes runtime tree generation harder, and pure GDScript performance is roughly **two orders of magnitude slower** than LimboAI's C++ core for tick processing across many agents.

### Performance demands object pooling and tick budgets

Godot 4 node creation is **~4× slower than Godot 3.5.1** (GitHub Issue #71182), with 8,000+ node creation causing crashes on some platforms. For a 2D sandbox with many LLM-generated objects, essential optimizations include:

- **Object pooling** — pre-create instances, reactivate from pool rather than instantiate/free
- **Tick budgets** — update only a fraction of agents per frame (e.g., 1/3 each frame)
- **AI LOD** — full behavior trees only for nearby/visible objects; distant objects use simplified logic or skip updates
- **Processing toggles** — `set_process(false)` on inactive objects for zero processing cost
- **Area2D with collision layers** for efficient proximity detection via Godot's spatial partitioning
- **Groups** for batch operations (`get_tree().call_group("enemies", "take_damage", 10)`)

GDQuest notes that "even if you have dozens of AI agents animating on-screen and each uses a behavior tree, you don't need an ECS" — but LimboAI's C++ core is essential if scaling to hundreds of active behaviors. The **Aphae project** (GitHub: rsanandres/aphae) provides a reference Godot 4.6 + Ollama architecture with AI-driven agents, procedurally generated personalities, and heuristic fallback when LLM is unavailable.

### The recommended Godot architecture

The full pipeline: **LLM generates structured JSON** behavior spec → Python/FastAPI backend validates against schema + budget constraints → JSON sent to Godot client → **factory function** builds LimboAI BehaviorTree resource from spec, using pre-defined task types → BTPlayer instantiates and runs the tree → **Expression class** evaluates condition strings with bound blackboard variables → Tweens handle visual feedback (particles, animations) → Area2D triggers proximity-based behavior events.

---

## 6. Broader research landscape and identified gaps

### The PCG literature explicitly excludes behavior generation

The most comprehensive recent survey of PCG with LLM integration (Maleki & Zhao, AIIDE 2024, reviewing 207 papers from 2019–2023) **explicitly excludes NPC behavior research**, confirming that structured behavioral specification generation is an under-studied area. The foundational PCGML survey (Summerville et al., 2018) focuses on levels, maps, and narrative content. Gallotta et al.'s "Large Language Models and Games: A Survey and Roadmap" (IEEE Transactions on Games, 2024, 130+ citations) is the first comprehensive survey at the LLM-games intersection and identifies runtime behavior generation as an underexplored area.

The Emergent Mind topic compilation on PCG with LLMs categorizes one approach as "Agent-Based Narrative Scripting: Multi-agent behaviors generated from scene metadata and serialized into structured behavior scripts (BNF grammar, parse and execute) for simulation" — directly paralleling the concept under investigation.

### The "10,000 bowls of oatmeal" problem applies to generated behaviors

Kate Compton's formulation (UCSC) identifies the core risk: generating thousands of technically unique behaviors that all feel like "move toward player, attack when close." **Perceptual uniqueness** — not mathematical uniqueness — is what matters. Emily Short's analysis adds that "the key question in oatmeal-avoidance is whether the generation is connected to anything mechanical." Generated behaviors must create **genuinely different gameplay interactions**, not just vary parameter values. No Man's Sky's 18 quintillion planets feeling samey after hours is the large-scale cautionary example.

### Physics-behavior interaction is a known source of emergent chaos

**Noita** (Nolla Games, 2020) is the definitive case study for adding autonomous behaviors to physics simulation. Its pixel-physics cellular automata combined with spell behaviors creates massive emergent chaos — the community coined **"Noita'd"** for deaths that feel especially unfair or unpredictable. Wood burns creating suffocating smoke; lava + water = rock + steam → condensation → rain; spell behaviors actively harm the caster through physics cascades.

The GDC talk "Exploring the Tech and Design of Noita" (Petri Purho) identifies "Taming the Emergent Chaos" and "Finding the Balance Between Fun and Game-breaking" as primary design challenges. For the described 2D sandbox game — which already has 33 material property tags and ~55 collision rules — adding autonomous behaviors will create a combinatorial explosion: N behaviors × M materials × P physics states. **Testing all emergent combinations is impossible**, exactly as Scribblenauts discovered with its 22,802 objects.

### Fundamental tensions the research reveals

Three genuine disagreements run through the literature:

**Runtime vs. design-time generation.** GROMIT's developer interviews show practitioners split on whether runtime generation is compatible with game design workflows that require testing and balancing. GROMIT's 30% success rate in the traffic scenario versus 85% in the sandbox underscores that reliability depends heavily on domain complexity.

**Constraint strictness vs. creative expression.** More constrained DSLs produce more reliable output (Anka's 99.9% parse success) but limit the range of possible behaviors. The budget system helps — it constrains *power*, not *creativity* — but the tradeoff is real. The oatmeal problem suggests too-tight constraints produce bland sameness, while too-loose constraints produce incoherent chaos.

**LLM spatial and logical reasoning limitations.** The GVGAI-LLM benchmark (2025) found "persistent limitations of LLMs in spatial reasoning and basic planning" with "consistent spatial and logical errors." Voyager demonstrates strong emergent capability in Minecraft. The resolution appears to be abstraction level: LLMs work well when operating on symbolic/categorical descriptions and poorly when reasoning about exact spatial positions or numeric calculations — further supporting the categorical-over-numeric design choice.

---

## 7. Thin areas and research gaps flagged

Several areas lack sufficient published research:

**No system has validated LLM generation of GOAP action definitions at scale.** Despite GOAP's theoretical LLM-friendliness (flat, declarative, independent actions), all LLM+game AI research found focuses on behavior trees, code generation, or narrative. GOAP generation is a novel contribution opportunity with strong theoretical backing but zero empirical validation.

**Validation frameworks for generated behavioral specs do not exist.** GROMIT reports success rates but no standardized evaluation metrics for behavioral correctness, balance, or interestingness. The SemGuard and Astrogator approaches from code validation research provide starting points but haven't been applied to game behavior specifications.

**The behavior-physics interaction problem has no formal treatment.** All knowledge exists in GDC talks, Steam community discussions, and postmortems. No taxonomy of behavior-physics conflicts, no formal model of emergent interaction risk, and no systematic mitigation strategies beyond "test extensively and iterate."

**Real-time latency remains unresolved.** GROMIT's 5.6-second average generation time and Voyager's need to pause the game while waiting for GPT-4 indicate a fundamental tension. For the described system, generation happens at object creation time (acceptable latency) rather than per-frame (impossible), but even creation-time latency affects player experience in a real-time sandbox.

**LLM-specific budget systems are entirely novel.** While point-buy and budget systems are well-documented in tabletop and strategy games, no published research applies budget constraints specifically to LLM-generated game content. The principles transfer strongly but haven't been validated in this domain.

---

## Conclusion

The research points toward a specific, defensible architecture: a **two-step LLM pipeline** (free reasoning → structured JSON output via constrained decoding), generating **GOAP-style action definitions and ECA rules** within a **point-buy budget system** using **categorical parameters**, validated through **constraint satisfaction**, and interpreted at runtime via **LimboAI behavior trees** built programmatically from pre-defined task types in Godot 4. This architecture aligns the highest-reliability LLM generation patterns (flat JSON, constrained vocabulary, categorical choices) with the most LLM-amenable behavior representation (GOAP's independent declarative actions) and the strongest available Godot infrastructure (LimboAI's C++ resource-based trees).

The most important insight cutting across all six topic areas: **the system should constrain the LLM's output space aggressively while preserving creative interpretation of player input**. The LLM's strength is understanding that "fire-breathing dragon" should have flight, fire attacks, and vulnerability to ice. Its weakness is picking the right numbers, generating correct nested logic, and reasoning about emergent physics interactions. Design the DSL to play to the strength and compensate for the weakness — categorical parameters, pre-built behavior vocabulary, budget constraints, and post-generation validation — and the research suggests a viable system is achievable with current technology.