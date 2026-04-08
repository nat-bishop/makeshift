# Inside the Objectnaut: How Scribblenauts Built a Dictionary-Driven World

**Scribblenauts' object system was both less algorithmic and more hand-crafted than anyone assumed** — and that reality is the single most important lesson for anyone building an LLM-based sandbox today. Between 2009 and 2013, 5th Cell shipped four games running on a custom data-driven engine called "Objectnaut," designed by technical director Marius Fahlbusch. The engine let designers assign physical properties, AI behaviors, and interaction rules to each of roughly 22,000+ dictionary entries. What the press called an elegant inheritance system was, in designer Liz England's words, "hand authored 1 by 1 & lots of crunch." This report synthesizes every available primary source — England's 2017 Twitter thread, the 2022 Designer Notes podcast, the PRACTICE 2018 talk, developer interviews with creative director Jeremiah Slaczka, reverse-engineering data, wiki documentation of the Object Editor, and community exploit analysis — into a reference document organized around the seven areas most relevant to LLM-based reimplementation.

---

## 1. The object schema: prototype inheritance with ten property tabs

The closest public documentation of Scribblenauts' internal schema is the **Object Editor** shipped with Scribblenauts Unlimited (2012). Producer Brittany Aubert confirmed it is "a modified version of the development tools 5th Cell used to create the objects in the series." It exposed **ten property tabs**, each mapping to a distinct slice of an object record:

**General** controlled identity and physics: Source Object (the prototype template from which most hidden properties are inherited), Alive (boolean for whether the object has AI), "Objects React To It As If It's A" (a category-identity override that determines how all other AI entities classify this object), Source Audio, Health (integer, **max 1,500**), Apply Gravity (boolean), Weight (numeric), and Buoyancy (float/sink/neutral enum). **Fire** stored combustion behavior: Spawns On Fire, Reaction to Fire (No Damage / Damaged / Explodes), Explosion Type (five tiers from Harmless to Nuclear), and Can Be Set On Fire. **Electricity** tracked conductivity: Generates Electricity, Gets Shocked By Electricity, and When Electrified Shocks Others. **Weapon** defined combat: Weapon Type (None / Bash / Chop / Explode / Throw / Throw Explode / Shoot / Shoot Explode / Cannon), Weapon Damage (integer, **max 100**), Projectile It Shoots (object reference), and Explosion Type. **Container** handled storage: Container Size, Has A Lid, and Object It Contains. **Movement** set locomotion: four movement modes (Walk/Swim/Fly/Hover) with separate sub-settings for When Equipped, When Alive, and When Driven, plus Movement Speed (numeric) and Jump Height (a discrete five-step enum: Can't Jump / Low / Medium / High / Very High). **Equipment** governed wearability: Can Wear Hats and Glasses, Can Sit On Things, Can Pick Things Up, Can Wear Wings and Backpacks, Can Be Sat Upon (equivalent to the "Ridable" adjective), and Equip Options (Hands / Head / Face / Back). **Behavior** contained the AI relationship table (see Section 2). **Special** handled attached child objects: Hanging Objects (spawns three copies as extensions), Storm Emission, and Wheel configuration (object type + count 1–4). **Scripting** offered a trigger→action event system (see Section 2).

### The two-tier category hierarchy

England described the hierarchy directly: "Scribblenauts objects definitely had systems and inheritance. They were placed in a 2-tier hierarchy. Ex: 'Mammal → Water Type → Dolphin.'" Top-level categories included **Tools, People, Food, Buildings, Plants, and Miscellaneous** (which she called "ridiculously useful"). Sub-categories narrowed further — all "Mammal → Water" objects automatically received a "swim underwater" checkbox. Material sub-categories visible in the Object Editor included Metal, Plastic, Fabric, Stone, Wood, Glass, and Paper.

Inheritance set broad defaults. Every mammal-based object received the property "organic flesh," making it edible and convertible to meat without per-object specification. Dimensional auto-rules existed: "If an object was X by Y pixels, automatically set its weight to Z." But England was blunt about limits: **"In a perfect world these systems would inherit across categories and you'd have to do very little hand-authoring to tweak outliers. In practice when you are dealing with cartoon objects — 'stereotypes' — the most important thing is how they are different from each other."**

### Multi-category membership

Objects belonged to multiple categories simultaneously. When entering an object name in the Behavior editor, a list of all categories that object belongs to appeared. **Apple, for example, belonged to 'Food,' 'Fruit,' 'Classroom,' and several others.** This multi-membership was the core mechanism driving emergent behavior — a lion's "Eat" behavior targeted the "Food" category, meaning it would eat anything tagged Food, not just specific prey items. The "Objects React To It As If It's A" field was the critical identity lever: it determined which category slot other objects' AI used when evaluating how to interact with this object.

### Prototype-based inheritance model

Every custom (and presumably every internal) object started from a **Source Object** — a prototype template. Most inaccessible properties were hard-coded to this source. A checkbox toggled whether to inherit behaviors from the source or override them. This is fundamentally a **prototype-based** system, not a class-based one: each object clones from a concrete parent and selectively overrides fields.

**LLM implications:** An LLM could auto-generate initial property sets by mapping a word to likely categories, weight ranges, and behavioral archetypes — replacing much of the six months of dictionary research. But the 10-tab schema shows that the *structured* property space is relatively small (perhaps 40–50 fields). An LLM should generate values for those fields, not replace them with free-text descriptions. The "Objects React To It As" field — the identity override — is a design pattern worth preserving: it decouples an object's name from its behavioral archetype, letting a "zombie firefighter" react as a Zombie rather than a Firefighter.

---

## 2. Nine behavior verbs drove the entire AI system

The Behavior tab exposed a system where alive objects react to **categories of other objects**, not individual entities. The nine documented behavior verbs are:

- **Destroy** — attacks and kills a target (e.g., T. Rex destroys Triceratops)
- **Eat** — consumes a target (e.g., Man eats Cookie)
- **Investigate** — approaches to look at a target (e.g., Alien investigating lifeforms)
- **Follow** — trails a target (e.g., Wolf Pups follow Wolves)
- **Protect** — defends a target (e.g., Adult protects Baby)
- **Use** — interacts functionally with a target (e.g., Scientists use Particle Accelerators)
- **Ride** — mounts a target (e.g., Pilots ride Airplanes)
- **Steal** — takes a target (e.g., Robbers steal Jewels)
- **Run Away** — flees from a target (e.g., Humans flee Monsters)

Each behavior was assigned a target specified by **category, not individual object name**. The runtime resolved which category a nearby object belonged to via the "Objects React To It As" property. This meant a single rule — "all humans eat from category 'Food'" — could propagate across thousands of human-type objects. It also meant every human would eat hamburgers, including the vegetarian.

### Where category-based AI breaks: the cop, the donut, and Cthulhu

England's most cited example of inheritance failure is the **cop problem**: "A cop won't flee from monsters if armed with a gun, right? But if you arm an orphan with a gun, he'd still flee, right? If you put Cthulhu AND a donut in the same space, everyone would flee from there. Except the cop should totally go for the donut, right?" This reveals that **AI priority resolution was brittle** — when multiple behaviors triggered simultaneously (Flee from Monster vs. Eat from Food), the system had no culturally-aware priority mechanism. The cop's donut affinity required a hand-authored exception.

The **mongoose versus cobra** case reveals the balance side of the same problem. A recurring QA bug titled "Mongoose does not defeat cobra" persisted because, as England noted, it was "very difficult to fix without making the mongoose too OP." Any stat change that let the mongoose reliably beat a cobra also let it beat most other creatures.

The **vegetarian eating hamburgers** was the simplest failure mode: hamburgers are tagged "Food," all humans eat Food, and the vegetarian inherited the default human behavior. Fixing it required a per-object exception overriding the inherited eat rule.

### What we know about the AI loop

No primary source documents the exact tick rate, state machine structure, or pathfinding algorithm. However, reverse engineering of Scribblenauts Remix revealed state machine code with classes named `I_State`, `I_StatePlus`, `C_StateManager`, `I_GameState`, and `I_GameStatePlus`, suggesting a formal state machine architecture. The temperature system provides indirect evidence of a simulation tick: "The melting point for humans (IIRC) was 180°F. You could place a campfire near them and they might sweat but never reach that temp… But if you SURROUNDED a person with campfires, the ambient temp would raise over time high enough and they'd catch on fire." This implies **continuous ambient temperature accumulation per tick**, not a one-shot interaction.

The scripting system exposed in the Object Editor confirms a **trigger→action event model** with hard limits: maximum **3 actions per trigger**, maximum **3-second wait**, and triggers that include "is created," "is destroyed," "gets eaten by an object," "touches an object," "reacts to an object," and "is used while equipped." Actions include adding/removing adjectives, creating objects, dealing damage, playing animations, and expressing emotions via speech bubbles.

**LLM implications:** The nine-verb behavior system is a remarkably compact action space. An LLM could dynamically assign behavior-verb-to-category mappings at object creation time (e.g., "what does a vegetarian eat? → category 'Vegetable Food' rather than 'Food'"), solving the exact class of bugs that plagued 5th Cell. But this introduces a **consistency problem**: if the LLM assigns different behaviors on different runs, the game becomes non-deterministic. A hybrid approach — LLM-generated initial mappings baked into a deterministic lookup table — is likely optimal.

---

## 3. Adjectives were property deltas, manually curated from 80,000 candidates

Super Scribblenauts (2010) added the adjective system. England described the sourcing process: **"I did download a public domain dictionary and stripped out everything but adjectives. Left with ~80k words. Which had to be sorted. By hand. Into synonyms and categories. Most were deleted (no time, or too specific — like medical terminology)."** The final game shipped with roughly **10,000 adjectives**, contributing to a total dictionary of 41,000+ words. The combinatorial explosion was staggering: "If you tested 100 combinations PER SECOND, every second, every day, it would take **4,944,752,622,004 years** to test every combination."

### How adjectives modified the schema

Adjectives map directly to the same properties exposed in the Object Editor — they are essentially **pre-configured property bundles**. The wiki taxonomy organizes them into four categories:

**Property adjectives** modify physical stats: size (Microscopic through Colossal, a **5× scale range**), weight, speed, durability, temperature. **Behavior adjectives** modify only AI: Friendly, Hostile, Scared, Aggressive, Tame. **Appearance adjectives** change visuals: colors, materials (Golden adds yellow texture + fire immunity; Wooden adds flammability; Metal increases weight, adds magnet attraction, and grants fire immunity). **Sound adjectives** swap audio profiles (71+ options including Autotuned, Barking, Classical).

Several special adjectives reveal the depth of the system. **Pregnant** makes an object fatter, then spawns a baby version. **Mitotic** causes the object to split into progressively smaller copies. **Omnipotent** grants invincibility, flight, and size increase simultaneously. **Sentient** makes inanimate objects walk around. **Dead** makes living things lie down and become unresponsive.

### Additive, multiplicative, or override?

No primary source explicitly states whether adjective effects are additive, multiplicative, or override-based. The observable evidence suggests a **mixed model**: size adjectives appear to use discrete scale multipliers (Microscopic to Colossal mapping to a 5× range), material adjectives appear to override fire reaction and weight properties entirely (Metal overrides fire reaction to "No Damage"), and behavioral adjectives appear to add or replace behavior rules. The "adding/removing adjectives uses the object like a tool/weapon — it turns green briefly" note from the community suggests adjective application triggers a re-evaluation of the object's property set at runtime, not just a static delta.

### Conflict resolution

Hidden **@adjectives** (accessible only via developer tools or hex editing) included 20 `@lm` adjectives, 11 `@special` adjectives, and others that modify base behaviors at spawn time without being removable. The community documented that "one trigger apparently can't remove adjectives added by another trigger" and "too many adjective changes causes the object to turn red and die" — suggesting the engine had limited tolerance for rapid property-set mutation.

**LLM implications:** An LLM is a natural fit for the adjective-to-property-delta mapping that England did by hand. Given a structured property schema, an LLM could generate the property modifications for any arbitrary adjective ("rusty" → decrease health, change appearance to brown, decrease weapon damage). The key risk is **contradiction detection** — an LLM might assign conflicting properties to "fireproof flammable" without flagging the inconsistency. A validation layer that checks for logical conflicts in generated property sets is essential.

---

## 4. The balancing problem was fundamentally unsolvable — and they knew it

This was the hardest design challenge Scribblenauts faced, and the developers were unusually candid about their partial failure. Slaczka stated the core goal clearly: **"We've tried very hard to balance the game to ensure there are no uber characters. That way people can have fun experimenting without fearing that they aren't using the best object possible to solve a puzzle."**

### The jetpack-and-rope problem

The most notorious balance failure was discovered immediately at launch. Players found that typing "jetpack" and "rope" (or "handcuffs") trivially solved nearly every action level — fly over all obstacles, grab the Starite from distance. This became known as **"the jet pack phenomenon"** and was documented in a viral Giant Bomb forum post titled "Scribblenauts Brought To Its Knees By Just Two Items." The exploit exposed a fundamental truth: **in a system where the player can summon any object, mobility items are inherently overpowered** because they change the player's fundamental traversal ability rather than solving a specific obstacle.

### Other documented exploits

The **vending machine exploit** let players attach handcuffs to a Starite, connect the other end to a vending machine, "fill" the vending machine with the Starite, then empty it next to Maxwell. The **Advanced Mode adjective exploit** allowed players to circumvent the "use different objects each time" constraint by prepending any adjective (the game counted "Small Hat" as different from "Hat" despite spawning the same object). **God** (the entity) had the highest HP in the game at 1,500 and a powerful thunder attack. The **"Cosmic" adjective bypassed invincibility entirely** — a "massive cosmic black hole" could kill an invincible player. The **"Gone" adjective** could delete any object in the game. The **Necronomicon** turned humans into friendly skeleton warriors. Community guides compiled lists of "most overpowered" items including the Zanbato (instant-kills humanoids), Mjolnir, Death (kills through invincibility), and Force Fields (deflects all objects and NPCs).

### Why balance was structurally impossible

Slaczka was remarkably honest about this: **"We had a QA plan that was set up during the middle of development, and we were wondering how we were going to QA this. We found we can't. It's not possible. No human can ever interact with everything. It's not possible. We just kind of hope that it all works and that it doesn't crash and that it doesn't break."** He gave the concrete example: "If you freeze your airplane, take it back in time on a time machine, put an old man on it, come back, and set it on fire, what's going to happen? I don't know. You can't test that."

No evidence of a formal **point-budget system** (like a "10-point stat allocation") was found in any source. The balance approach appears to have been: set broad category-level defaults, then hand-tune individual objects that were obviously too powerful or too weak, and hope that the combinatorial space averaged out. The mongoose-versus-cobra dilemma illustrates the core tradeoff: any stat tweak that fixes one matchup creates ripple effects across hundreds of others.

### How sequels responded

**Super Scribblenauts** sidestepped the jetpack problem by **shifting heavily toward puzzle levels** rather than action levels, where the goal was matching adjective-modified objects to descriptions rather than physically reaching a Starite. **Scribblenauts Unlimited** moved to an open-world with NPC-driven puzzles, but critics noted the broader toolset made puzzles "too easy." The balance problem was never truly solved — it was **designed around**.

England's most relevant reflection on balance difficulty comes from the broader content-authoring challenge: "One of the hardest problems I've run into in game design is where system should end and hand-authoring should begin." Every balance fix was a hand-authored exception, and the exception space was infinite.

**LLM implications:** This section contains the strongest case for LLM-based reimplementation. An LLM could serve as a **real-time balance evaluator** — given a proposed object spawn, predict whether it trivializes the current puzzle based on learned heuristics. More importantly, an LLM could **generate countermeasures dynamically**: if a player summons a jetpack, the puzzle environment could adapt (add a ceiling, add wind, require ground-based interaction). But this introduces the "fairness perception" problem — players need to trust that the game isn't arbitrarily punishing creativity. 5th Cell's biggest lesson here is that **the balance problem is not a bug to fix but a design constraint to accept**: some players will find dominant strategies, and the game's value comes from the creativity of the *rest* of the dictionary, not from preventing exploitation.

---

## 5. The content pipeline was six months of Wikipedia, then hand-tuning

The pipeline had three phases: **word sourcing**, **object instantiation**, and **exception authoring**.

### Phase 1: word sourcing from Wikipedia

England corrected the common narrative: "There was an interview where someone said we scoured dictionaries for words. This wasn't ENTIRELY accurate. It was actually Wikipedia." The rationale was pragmatic: **"It didn't actually matter if an object was accurate. What mattered is that it did what people expected. Wikipedia was best source for that."** Wikipedia also "conveniently categorizes stuff, and includes lots of synonyms of other things people might call a thing from various cultures." Five team members spent **six months** on this research phase, scouring Wikipedia, dictionaries, and encyclopedias. The studio was temporarily **IP-banned from Google** because England used the thesaurus feature so fast that Google's bot detection flagged her.

The critical design principle was **representational over accurate**: "A game like Scribblenauts relies largely on representational, rather than accurate, objects to fulfill player expectations. Since the goal was common consensus — even if that consensus was technically wrong — Wikipedia and Google Image Search actually solved most problems when asking the question, 'What do people visualize when they read this word?'"

### Phase 2: Objectnaut instantiation

Slaczka described the workflow: "We order art for the object, animate it if need be, convert it to get into the DS, plop it in Objectnaut under a category and subcategory, which already gives it a bunch of properties; from there we just tweak it to what we need. **To create an item it doesn't take long at all, few hours. To refine and polish it takes a few more.** The engine handles a lot of the hard work for us; we designed it that way."

Synonym-versus-unique-object classification was a subjective process. England admitted: "Determining what counts as a 'synonym' as opposed to a 'unique object' was a purely subjective undertaking. I personally think most fish look alike, so a fellow designer had to take over the classification of that category from me." The final dictionary had **~22,802 nouns** but only roughly **~4,000 unique visual objects**, since many words were synonyms pointing to the same model.

### Phase 3: the crunch of exceptions

England's core insight — the "mathwashing" revelation — was that **the hand-authoring phase dwarfed the systematic phase**. The development team spent approximately **80% of development time** getting item properties to work before a single level could function. "In the end sure, I didn't have to set the melting point different for each person. But the expectations of players coming into the game meant that every AI, and many other objects, needed tons of custom 'exceptions.'"

The game's representation of people required particular care. After receiving 100+ human sprites from an outsourcer, the team discovered "service workers were almost all women, criminal characters were black, politicians and leaders were white men." Multiple correction passes were required. The word "sambo" entered the game as a synonym for "watermelon" through the Wikipedia-sourcing pipeline and had to be removed.

### Localization as a parallel nightmare

The postmortem by co-founder Joseph Tringali revealed that localization support was built into Objectnaut from the start, but the system was "optimized for previous titles that only had game text." Scribblenauts had both game text and a massive dictionary using **different systems**. Unique dictionaries were maintained for every language across 12 localizations (English, French, Spanish, Brazilian Portuguese, German, Italian, Dutch, UK English, Danish, Finnish, Swedish, Norwegian). "Version control became a nightmare as we tracked dozens of files for both dictionary files and word lists." German and Scandinavian versions had longer words that overflowed character limits, forcing font size reductions and notebook word choices cut from 5 to 3.

**LLM implications:** This section maps the clearest LLM opportunity. The six months of Wikipedia research, synonym grouping, and category assignment could plausibly be compressed to days with an LLM generating initial object records from word embeddings. But England's insight about **representational design** is critical: an LLM trained on encyclopedic text might generate *accurate* object properties rather than *expected* ones. The design goal is "what do people visualize when they read this word?" — which is closer to cultural stereotype than factual accuracy. An LLM's training data likely captures these stereotypes, making it arguably *better* suited for this task than a dictionary. However, the representation-bias problem (gendered service workers, racialized criminals) would be *amplified* by an LLM's training data without explicit bias auditing.

---

## 6. The Objectnaut engine ran a 22,000-word dictionary in 4 megabytes of RAM

### Marius Fahlbusch and the engine architecture

The Objectnaut engine was created by **Marius Fahlbusch**, 5th Cell's technical director and co-founder, who studied at the University of Munich and holds degrees in engineering. Slaczka called him "the reason Scribblenauts was made." Fahlbusch has no known public talks, blog posts, or interviews — he appears to be a very private figure. A LinkedIn recommendation describes him as "one part brilliant and innovative programmer, another part passionate torch-bearer of vision."

The engine was **data-driven by design**: rather than hard-coding behavior, each object was defined by a property record that the engine evaluated at runtime. Slaczka confirmed the scope: "Basically anything that exists, any property, mental or physical you can think of is in this tool." Co-founder Tringali noted that without the Objectnaut engine, the game "wouldn't have released until around 2015 at the earliest."

### DS hardware constraints and the budget meter

The original Scribblenauts ran on the Nintendo DS with severely limited hardware: **ARM946E-S at 67 MHz**, **4 MB PSRAM**, **656 KB VRAM**, **256×192 pixel screens**, and a maximum polygon budget of roughly **2,048 triangles per frame**. To manage memory, the game used a **"Budget Meter"** (visible to the player) that limited the number of simultaneous objects. Vehicles and multi-part objects consumed more budget. The exact DS object limit is not publicly documented, but the Wii U version of Scribblenauts Unlimited (2012) removed the budget meter and supported **up to 60 simultaneous objects**, implying the DS limit was significantly lower — likely in the range of 10–15 complex objects.

Objects were **rendered in 3D but displayed on a 2D plane** — a deliberate simplification so that many objects could share animations without requiring large 2D sprite sheets. The entire original DS ROM was only **~9.7 MB**, remarkable given the content volume.

### The interaction graph: tag-based evaluation, not pairwise lookup

Available evidence indicates the interaction system was **tag/property-based evaluation rather than a static pairwise lookup table**. Interactions resolved at runtime by checking the properties and category memberships of the interacting objects. Fire burned wood because wood had the "flammable" property and fire had the "burns flammable things" rule — not because there was a fire→wood entry in a table. This is confirmed by the Object Editor's structure: behaviors target categories, not individual objects, and the "Objects React To It As" field redirects identity resolution at runtime.

### File format and reverse engineering

The PC version used a **proprietary .p archive format** containing Zlib-compressed files referenced by an `index.bin` at runtime. No filenames are used at runtime — everything is **index-based**. The directory structure mirrored the object hierarchy: `PLATFORM/DATAVECTOR/HUMAN/PLAYER/MAXWELL.VEC`. The most significant reverse-engineering effort is **XorTroll's super-scribblenauts-re project** (https://github.com/XorTroll/super-scribblenauts-re), which includes C++ libraries (`libobjectnaut`) for parsing game formats, documents the file system structure, and provides a CLI tool (`scribbletool`) that can print all fields of an object file, list objects/adjectives by language, and export textures. The documentation site (https://xortroll.github.io/super-scribblenauts-re/) contains specifications for Dictionary files, Object files, Object texture files, Adjective files, Animation files, and Attack files — confirming these as distinct data formats within the Objectnaut system. GMMan's **ScribbleUnpacker** (https://github.com/GMMan/ScribbleUnpacker) handles extraction of the .p archive format for Scribblenauts Unlimited.

The Cutting Room Floor (https://tcrf.net/Scribblenauts_Unlimited) documents hidden developer objects prefixed with `@` (e.g., `@maxwelldummy`, `@CreateATron`, `@Black Magic`) and system objects prefixed with `$` (e.g., `$Starite`, `$MYADJECTIVES`). The mysterious `$MYADJECTIVES` objects suggest a planned custom-adjective feature that was never completed. State machine code classes (`I_State`, `I_StatePlus`, `C_StateManager`, `I_GameState`) were found in the Scribblenauts Remix binary, confirming a formal state machine architecture.

**LLM implications:** The DS-era constraints forced 5th Cell into an extremely efficient data representation — ~22,000 words in under 10 MB. An LLM-based system would face the opposite problem: model size and inference latency rather than storage. The tag-based evaluation pattern is the right architecture to preserve — it scales linearly with object count rather than quadratically (as a pairwise table would). The key technical decision for an LLM sandbox is **when to invoke the LLM** (object creation time only? every interaction tick? only on novel interactions?) and how to cache results into deterministic lookup structures.

---

## 7. What went wrong, what was learned, and what remains unsolvable

### The combinatorial explosion was acknowledged and accepted

From the beginning, 5th Cell knew they could not test everything. Slaczka's candor was unusual for a studio head: "We just kind of hope that it all works and that it doesn't crash." England quantified the Super Scribblenauts adjective combinatorics at **~4.9 trillion years** to exhaustively test at 100 combinations per second. The QA strategy was necessarily heuristic — test the most obvious interactions, rely on category-level inheritance to handle the long tail, and patch what players found post-launch. The Scribblenauts Collection (rerelease) fixed known exploits like the vending machine trick and the Advanced Mode adjective bypass.

### Documented failure modes

Beyond the exploits covered in Section 4, the system produced conceptual failures that reveal architectural limits. The **vegetarian eating hamburgers** was a pure inheritance bug — easily fixed once noticed, but symptomatic of how category-level rules generate culturally wrong defaults. The question **"if you glue steak to a lion, will it eat itself?"** was an actual design conversation during development, illustrating the recursive interaction problem. Emergent behavior sometimes worked brilliantly — Slaczka described flying a helicopter over enemy soldiers who then climbed in the backseat and shot him — but the line between "delightful emergence" and "absurd bug" was impossible to police at scale.

England's reflection on personal bias was unusually honest for a game developer: **"As the main person in charge of the dictionary many of my internal assumptions and oversights went into the final game. It's an odd experience when your personal bias is labeled as a 'bug' by players on a forum."** The fish classification example — "I personally think most fish look alike, so a fellow designer had to take over the classification of that category from me" — shows that even the category hierarchy was shaped by one person's knowledge gaps.

### What England says she'd do differently

When asked directly in the 2017 thread about what she'd change with nine years of hindsight, her answer was characteristically terse: **"Not much, less crunch."** The Design Notes podcast (Episode 73, March 2023) explored this more deeply over three hours, discussing "what is the boiling point of a lion" and "whether system complexity matters if the player can't see it." No transcript exists, but the episode description confirms these topics were central. The PRACTICE 2018 talk "How to Make an Impossible Game: Designing Scribblenauts" (https://www.youtube.com/watch?v=C4n0SyJnfpE) is the most comprehensive single presentation on the design philosophy — also video-only with no public transcript or summary.

England's broader design philosophy, visible across all her sources, centers on the tension between systems and hand-authoring: **"One of the hardest problems I've run into in game design is where system should end and hand-authoring should begin."** The Scribblenauts experience taught her that player expectations are not systematic — they are cultural, contextual, and full of exceptions that no inheritance hierarchy can capture.

### The GDC 2018 microtalk and the "Spectacular Failure" principle

England's GDC 2018 microtalk segment was titled "Designing for Spectacular Failure" (part of the "Playing with Fire" Microtalks session). While the full content is behind the GDC Vault paywall, the title itself encapsulates a key Scribblenauts lesson: **the system should fail in entertaining ways rather than trying to prevent failure**. When a player glues steak to a lion and it eats itself, that's a failure — but it's a *fun* failure that players share and remember. The design goal shifts from "prevent all bugs" to "ensure failures are spectacular rather than boring or broken."

### Key primary sources and where to find them

The five highest-value sources for anyone building on this research are:

- **Liz England's 2017 Twitter thread** — reprinted in full at Kotaku (https://kotaku.com/the-secret-behind-scribblenauts-making-objects-by-hand-1796262472) and covered by Game Developer (https://www.gamedeveloper.com/design/-i-scribblenauts-i-dev-shares-lessons-learned-in-making-its-huge-object-library)
- **Designer Notes Podcast Episode 73** (3 hours, audio only) — https://www.designer-notes.com/designer-notes-73-liz-england/
- **PRACTICE 2018 talk** (video only) — https://www.youtube.com/watch?v=C4n0SyJnfpE
- **Game Developer Postmortem by Joseph Tringali** (November 2009) — https://www.gamedeveloper.com/pc/postmortem-behind-the-scenes-of-i-scribblenauts-i-
- **XorTroll's reverse engineering project** — https://github.com/XorTroll/super-scribblenauts-re and documentation at https://xortroll.github.io/super-scribblenauts-re/

Additional valuable sources include the Scribblenauts Fandom Wiki Object Editor page (https://scribblenauts.fandom.com/wiki/Object_editor), the Object Scripting page (https://scribblenauts.fandom.com/wiki/Object_scripting), the First Person Scholar interview with England (https://www.firstpersonscholar.com/interview-liz-england/), the Destructoid interview with Slaczka (https://www.destructoid.com/interview-jeremiah-miah-slaczka-unscribbles-scribblenauts/), the Engadget interview (https://www.engadget.com/2009-07-10-interview-scribblenauts-creative-director-jeremiah-slaczka.html), the Nintendo World Report interview (http://www.nintendoworldreport.com/interview/19950/scribblenauts-interview-with-jeremiah-slaczka), the TCRF page (https://tcrf.net/Scribblenauts_Unlimited), the @ Method wiki page (https://scribblenauts.fandom.com/wiki/The_%22@%22_Method), the GDC 2010 talk (https://gdcvault.com/play/1012406/5TH-Cell-From-Mobile-to), the GMMan ScribbleUnpacker (https://github.com/GMMan/ScribbleUnpacker), and community exploit documentation on Giant Bomb (https://www.giantbomb.com/scribblenauts/3030-24741/forums/scribblenauts-brought-to-its-knees-by-just-two-ite-263867/) and Speedrun.com (https://www.speedrun.com/scribblenauts_/guides/ezemh).

---

## Conclusion: what an LLM replaces, what it can't, and what new problems it creates

Scribblenauts' deepest lesson is not about any specific technical system — it is that **player expectations are cultural knowledge, not computable rules**. The cop wants the donut. The vegetarian won't eat the hamburger. The mongoose beats the cobra but shouldn't be invincible. No inheritance hierarchy captures these truths; they live in the space between dictionary definitions and shared cultural understanding.

An LLM is, arguably, the first technology that operates natively in that space. It could replace the six months of Wikipedia research, the hand-sorting of 80,000 adjectives, and much of the per-object exception authoring that consumed 80% of Scribblenauts' development time. It could generate the initial property vector for any noun, predict culturally-appropriate behavior rules, and flag likely contradictions in adjective combinations.

But it introduces three problems 5th Cell never faced. **Consistency**: a hand-authored database returns the same result every time; an LLM might assign different properties to "lion" on different runs, creating a non-deterministic game world. **Balance regression**: every LLM-generated object is a new potential exploit vector with no QA history. **Hallucinated properties**: an LLM might assign properties that are plausible-sounding but mechanically incoherent (a "lightweight anvil" that breaks physics expectations).

The architecture that emerges from this analysis is a **hybrid**: use an LLM as the authoring accelerator (replacing England's pipeline), but bake its outputs into a **deterministic structured database** (preserving Objectnaut's property-tab schema). Use the LLM at creation time, not at runtime. Validate every generated object against mechanical constraints before it enters the world. And embrace England's deepest insight: the system will produce wrong results, and the design goal is to make those failures spectacular rather than silent.