# Eval: baseline

**2026-03-31 05:33 UTC** | Model: `Qwen/Qwen3.5-35B-A3B-FP8` | Judge: `google-gla:gemini-3-flash-preview` | 80 cases | Variant: `baseline`

## Scores

| Metric | Mean |
|--------|------|
| Validity | 1.00 |
| Faithfulness | 0.84 |
| Gameplay Quality | 0.83 |
| Sprite Prompt | 0.97 |

## Reliability

| Stat | Value |
|------|-------|
| First-try success | 90% (72/80) |
| Avg retries | 0.14 |
| Max retries | 2 |
| Total retries | 11 |

**Retry reasons:**

- (2x) `LIQUID and SOLID cannot coexist. Remove one.`
- (2x) `FLAMMABLE and HEAT_SOURCE cannot coexist. Remove one.`
- (1x) `Name "Deep Sea Shock Jelly" has 4 words. Use 1-3 words maximum.`
- (1x) `Invalid behavior 'ON_TIMER -> MOVE_TOWARD -> CONTACT_BODY, power=medium': 1 vali...`
- (1x) `Invalid behavior 'ALWAYS -> MOVE_AWAY -> SELF, power=medium': 1 validation error...`
- (1x) `Invalid behavior 'ON_PROXIMITY -> ADD_TAGS(FIXED) -> SELF, power=low': Unknown t...`
- (1x) `Invalid behavior 'ON_CONTACT -> ADD_TAGS(ANCHOR) -> SELF, power=low': Unknown ta...`
- (1x) `Invalid behavior 'ON_TAG_ADDED(GOLD) -> ADD_TAGS(CARRYING) -> SELF, power=medium...`
- (1x) `Invalid behavior 'ON_CONTACT -> ADD_TAGS(ON_BACK) -> CONTACT_BODY, power=low': U...`

## Programmatic Metrics

| Metric | Value |
|--------|-------|
| Interaction Surface (avg) | 9.3 / 53 rules (min 1, max 25) |
| LIVING w/o movement | 4 / 16 LIVING objects |
| Visual desc length | 73 / 119 / 226 chars (min / median / max) |

**LIVING without movement:** acid spider, friendly dog, electric jellyfish, lasso vine

## Scores by Category

| Category | Validity | Faithfulness | Gameplay Quality | Sprite Prompt | n |
|----------|----------|--------------|------------------|---------------|---|
| abstract | 1.00 | 0.85 | 0.95 | 1.00 | 5 |
| adversarial | 1.00 | 0.90 | 0.87 | 1.00 | 13 |
| consumable | 1.00 | 0.88 | 0.88 | 1.00 | 2 |
| creature | 1.00 | 0.75 | 0.75 | 0.93 | 15 |
| defensive | 1.00 | 1.00 | 0.75 | 1.00 | 2 |
| environment | 1.00 | 0.75 | 1.00 | 1.00 | 1 |
| mundane | 1.00 | 0.84 | 0.88 | 0.97 | 8 |
| nature | 1.00 | 0.83 | 0.83 | 1.00 | 3 |
| problem | 1.00 | 1.00 | 0.83 | 1.00 | 3 |
| trap | 1.00 | 0.81 | 0.75 | 0.94 | 4 |
| traversal | 1.00 | 0.80 | 0.85 | 0.95 | 5 |
| utility | 1.00 | 0.94 | 0.86 | 0.97 | 9 |
| vehicle | 1.00 | 0.75 | 0.81 | 0.88 | 4 |
| weapon | 1.00 | 0.71 | 0.75 | 1.00 | 6 |

## Distribution

### Tags

| Tag | Count | Pct | |
|-----|-------|-----|---|
| SOLID | 61/80 | 76% | `███████████████░░░░░` |
| RIGID | 33/80 | 41% | `████████░░░░░░░░░░░░` |
| HEAVY | 19/80 | 24% | `████░░░░░░░░░░░░░░░░` |
| LIVING | 16/80 | 20% | `████░░░░░░░░░░░░░░░░` |
| LIGHT | 16/80 | 20% | `████░░░░░░░░░░░░░░░░` |
| FLEXIBLE | 15/80 | 19% | `███░░░░░░░░░░░░░░░░░` |
| GLOWING | 14/80 | 18% | `███░░░░░░░░░░░░░░░░░` |
| BREAKABLE | 11/80 | 14% | `██░░░░░░░░░░░░░░░░░░` |
| HEAT_SOURCE | 11/80 | 14% | `██░░░░░░░░░░░░░░░░░░` |
| HOSTILE | 11/80 | 14% | `██░░░░░░░░░░░░░░░░░░` |
| FLOATING | 9/80 | 11% | `██░░░░░░░░░░░░░░░░░░` |
| LIQUID | 7/80 | 9% | `█░░░░░░░░░░░░░░░░░░░` |
| FLAMMABLE | 7/80 | 9% | `█░░░░░░░░░░░░░░░░░░░` |
| BOUNCY | 7/80 | 9% | `█░░░░░░░░░░░░░░░░░░░` |
| WIND_SOURCE | 6/80 | 8% | `█░░░░░░░░░░░░░░░░░░░` |
| SHARP | 5/80 | 6% | `█░░░░░░░░░░░░░░░░░░░` |
| COLD | 5/80 | 6% | `█░░░░░░░░░░░░░░░░░░░` |
| WET | 4/80 | 5% | `█░░░░░░░░░░░░░░░░░░░` |
| ELECTRIC | 4/80 | 5% | `█░░░░░░░░░░░░░░░░░░░` |
| TOXIC | 4/80 | 5% | `█░░░░░░░░░░░░░░░░░░░` |
| HOT | 3/80 | 4% | `░░░░░░░░░░░░░░░░░░░░` |
| EXPLOSIVE | 3/80 | 4% | `░░░░░░░░░░░░░░░░░░░░` |
| GAS | 3/80 | 4% | `░░░░░░░░░░░░░░░░░░░░` |
| REFLECTIVE | 3/80 | 4% | `░░░░░░░░░░░░░░░░░░░░` |
| STICKY | 2/80 | 2% | `░░░░░░░░░░░░░░░░░░░░` |
| MOLTEN | 2/80 | 2% | `░░░░░░░░░░░░░░░░░░░░` |
| MAGNETIC | 2/80 | 2% | `░░░░░░░░░░░░░░░░░░░░` |
| FROZEN | 2/80 | 2% | `░░░░░░░░░░░░░░░░░░░░` |
| SLIPPERY | 1/80 | 1% | `░░░░░░░░░░░░░░░░░░░░` |
| CORROSIVE | 1/80 | 1% | `░░░░░░░░░░░░░░░░░░░░` |
| CONDUCTING | 1/80 | 1% | `░░░░░░░░░░░░░░░░░░░░` |
| INSULATING | 1/80 | 1% | `░░░░░░░░░░░░░░░░░░░░` |

### Sizes

| Size | Count | Pct |
|------|-------|-----|
| small | 40/80 | 50% |
| large | 20/80 | 25% |
| medium | 11/80 | 14% |
| huge | 6/80 | 8% |
| tiny | 3/80 | 4% |

### Behaviors Per Object

| Count | Objects | Pct |
|-------|---------|-----|
| 0 | 29/80 | 36% |
| 1 | 35/80 | 44% |
| 2 | 15/80 | 19% |
| 3 | 1/80 | 1% |

### Triggers

| Type | Count |
|------|-------|
| ALWAYS | 18 |
| ON_PROXIMITY | 18 |
| ON_CONTACT | 13 |
| ON_TAG_ADDED | 9 |
| ON_CREATE | 5 |
| ON_DAMAGED | 4 |
| ON_DESTROY | 1 |

### Actions

| Type | Count |
|------|-------|
| ADD_TAGS | 21 |
| MOVE_TOWARD | 18 |
| EXPLODE | 7 |
| SPAWN_PROJECTILE | 6 |
| APPLY_FORCE | 5 |
| ATTRACT | 3 |
| MOVE_AWAY | 3 |
| REMOVE_TAGS | 2 |
| HEAL | 2 |
| SELF_DESTRUCT | 1 |

### Targets

| Type | Count |
|------|-------|
| SELF | 18 |
| CONTACT_BODY | 16 |
| NEAREST_LIVING | 15 |
| NEAREST_OBJECT | 10 |
| NEAREST_PLAYER | 9 |

## Cases

### rock
**Tags:** SOLID, RIGID, HEAVY | **Size:** medium
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 5

### wooden chair
**Tags:** SOLID, RIGID, HEAVY | **Size:** medium
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 0.50 | Gameplay Quality 0.75 | Sprite Prompt 0.75 | Surface 5
> **Faithfulness (0.50):** The design misses key properties of a 'wooden chair'. The name 'Rusty Chair' suggests metal rather than wood, and it is missing core physical tags like FLAMMABLE and BREAKABLE which are essential for wooden objects in a physics sandbox. While it correctly identifies SOLID and RIGID, the lack of expected material behaviors and the thematic shift make it a partial capture of the concept.
> **Gameplay Quality (0.75):** The design correctly uses tags from the valid list to create interaction surfaces (RIGID and HEAVY both trigger multiple rules). However, it misses the FLAMMABLE tag for a wooden object, which is specifically cited in the rubric as a minor missed opportunity (0.75). It also misses the BREAKABLE tag, which would allow it to interact with many more systems (SHARP, EXPLOSIVE, etc.).
> **Sprite Prompt (0.75):** The description specifies the shape (slat backrest, legs), materials (wooden, metal reinforcement), and color (brown legs). It is consistent with the tags SOLID, RIGID, and HEAVY. However, there is a slight mismatch/gap between the name 'Rusty Chair' and the visual description, as the description mentions metal reinforcement but fails to describe the 'rusty' visual quality or the color of the metal and the rest of the chair, which would be important for a sprite.

### bucket of water
**Tags:** LIQUID, WET | **Size:** small
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 8
> **Faithfulness (0.75):** The design captures the core concept well with an appropriate name and a detailed visual description. The tags "LIQUID" and "WET" accurately reflect the water content. However, the design is missing the "SOLID" and "RIGID" tags which are essential to represent the bucket (the container) in a physics sandbox. This is a minor omission regarding the physical nature of the object.
> **Gameplay Quality (0.75):** The design successfully uses the LIQUID and WET tags to enable core water-based interactions such as extinguishing fire, freezing, and soaking other objects. However, it misses the opportunity to tag the 'bucket' itself—as a galvanized metal pail, it lacks tags like RIGID, HEAVY, or CONDUCTING, which would have enabled interactions with magnets, crushing, or structural physics. This is a minor missed opportunity for fuller emergent gameplay.
> **Retries:** 1 — `LIQUID and SOLID cannot coexist. Remove one.`

### banana
**Tags:** SOLID, FLEXIBLE, SLIPPERY | **Size:** small
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 2
> **Gameplay Quality (0.75):** The design captures the core essence of a banana with the SLIPPERY tag, which creates a specific interaction with HEAVY objects. It also uses FLEXIBLE to interact with SHARP objects. However, it misses the opportunity to make the object BREAKABLE (so it could be crushed or cut) or FLAMMABLE (as it is organic matter), which are standard interaction surfaces for such an object in a physics sandbox.

### glass bottle
**Tags:** SOLID, RIGID, BREAKABLE | **Size:** small
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 10

### hot coal
**Tags:** SOLID, HEAT_SOURCE, HOT, GLOWING | **Size:** small
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 10

### giant boulder
**Tags:** SOLID, HEAVY, LIVING | **Size:** huge
- `ALWAYS -> MOVE_TOWARD -> NEAREST_LIVING, power=high`
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 12
> **Faithfulness (0.75):** The design captures the core concept well. The name, visual description, and core tags (SOLID, HEAVY) match the prompt. The behavior effectively implements the "crushing anything in its path" requirement by making it move toward living entities. However, the 'LIVING' tag is contradictory for a boulder, which is an inanimate object. 'HOSTILE' would have been a more appropriate tag to pair with the aggressive behavior.
> **Gameplay Quality (0.75):** The design captures the core concept using the HEAVY tag to trigger the 'Crush' interaction with BREAKABLE objects. The use of the LIVING tag is a clever way to enable autonomous movement via behaviors, while also creating interaction surfaces where the boulder can be affected by poison, electricity, or heat. However, it misses a key interaction: the prompt says it 'crushes anything,' but without the HOSTILE or SHARP tags, it has no interaction rule to damage other LIVING objects. Additionally, choosing RIGID over SOLID would have provided more interaction surfaces (like Hard Bounce and Structural Corrosion) according to the provided rules.

### tiny pebble
**Tags:** SOLID, LIGHT, BREAKABLE | **Size:** tiny
- `ON_PROXIMITY -> ATTRACT -> NEAREST_OBJECT, power=low`
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 9
> **Faithfulness (0.75):** The design captures the core concept well. The name and visual description are perfect for 'the world's smallest pebble'. The tags (SOLID, LIGHT, BREAKABLE) are all appropriate and chosen from the allowed list. The only minor issue is the attraction behavior, which isn't typically associated with a pebble, though it may be a creative attempt to represent how very small particles interact with surfaces (like static).

### fire sword
**Tags:** SOLID, RIGID, SHARP, HEAT_SOURCE | **Size:** small
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 14
> **Faithfulness (0.75):** The design captures the core concept of a "Fire Sword" well. The tags SOLID, RIGID, SHARP, and HEAT_SOURCE are all accurate. However, the design missed the tags HOT and GLOWING, both of which are directly supported by the visual description ("glows with an inner orange heat"). The behaviors list is empty, which is acceptable if the tags handle the interactions.

### sword
**Tags:** SOLID, RIGID, SHARP | **Size:** small
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 6
> **Faithfulness (0.75):** The design captures the core concept of a sword perfectly with appropriate tags (SOLID, RIGID, SHARP). However, there is a minor inconsistency: the visual description mentions the blade is "glowing faintly," but the GLOWING tag was not included despite being a valid tag option.
> **Gameplay Quality (0.75):** The design correctly identifies the primary function of a sword using the SHARP tag, which enables several automatic interactions like cutting and laceration. It also correctly includes RIGID for structural integrity and bouncing. However, there are minor missed opportunities: 1) A 'Steel' sword should ideally have the CONDUCTING tag to interact with electricity, magnetism, and heat/cold conduction. 2) The visual description mentions the sword is 'glowing', but the GLOWING tag is missing. These omissions limit the emergent gameplay slightly, matching the 0.75 criteria.

### time bomb
**Tags:** SOLID, RIGID, ELECTRIC, EXPLOSIVE | **Size:** small
- `ON_CREATE -> ADD_TAGS(ELECTRIC) -> SELF, power=medium`
- `ON_TAG_ADDED(ELECTRIC) -> EXPLODE -> SELF, power=high`
**Scores:** Validity 1.00 | Faithfulness 0.50 | Gameplay Quality 0.50 | Sprite Prompt 1.00 | Surface 14
> **Faithfulness (0.50):** The design fails to implement the core "time" aspect of the "time bomb." While the visual description mentions a countdown timer, the behaviors dictate an immediate explosion upon creation (ON_CREATE -> ADD_TAGS -> ON_TAG_ADDED -> EXPLODE), which contradicts the user's request for a bomb that blows up "after a few seconds." In a physics sandbox, an instant explosion where a delay is expected is a significant functional gap.
> **Gameplay Quality (0.50):** The design fails on several levels regarding the 'Time Bomb' prompt. First, it fails the core requirement of being a 'time' bomb, as there is no timing logic or delay in the behaviors; it would explode instantly. Second, it violates the key principle that behaviors should not duplicate what tags already do. The object has both ELECTRIC and EXPLOSIVE tags, which according to the interaction rules ('Electrical Detonation'), already cause a detonation automatically. The behavior 'ON_TAG_ADDED(ELECTRIC) -> EXPLODE' is therefore redundant. Additionally, the object is given the ELECTRIC tag in its base tags AND has a behavior to add it 'ON_CREATE', which is also redundant. While the tags chosen provide good interaction surfaces, the implementation of the logic is poor.

### homing missile
**Tags:** SOLID, RIGID, HEAVY, FLAMMABLE | **Size:** small
- `ALWAYS -> MOVE_TOWARD -> NEAREST_LIVING, power=high`
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 0.50 | Sprite Prompt 1.00 | Surface 8
> **Faithfulness (0.75):** The design captures the core concept of a heat-seeking missile very well, especially with the 'MOVE_TOWARD -> NEAREST_LIVING' behavior which directly addresses the player's request. The name and visual description are also spot-on. The only minor issue is the choice of tags and behaviors regarding the missile's payload; while the player focused on the homing aspect, a 'missile' should ideally have the EXPLOSIVE tag (which is available) and a behavior to explode on contact, rather than just being FLAMMABLE.
> **Gameplay Quality (0.50):** The design fails to include the 'EXPLOSIVE' tag, which is the defining characteristic of a missile. Without it, the object will not detonate or cause blast damage upon impact. Furthermore, it lacks any tag-based interaction to deal damage to the targets it chases (e.g., 'HOSTILE', 'HEAT_SOURCE', or 'SHARP'), meaning it will simply bump into enemies without hurting them. While the behavior correctly handles the 'heat-seeking' movement, the tags miss the primary interaction surface of a missile.

### rubber ball from hell
**Tags:** SOLID, BOUNCY, HOSTILE, LIGHT | **Size:** small
- `ON_CONTACT -> ADD_TAGS(HOSTILE) -> CONTACT_BODY, power=high`
**Scores:** Validity 1.00 | Faithfulness 0.50 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 5
> **Faithfulness (0.50):** The design captures the theme of a possessed ball well through its name, visual description, and the HOSTILE tag. However, it completely fails to implement the "bouncing around faster and faster" mechanic requested in the input. Additionally, the behavior "ON_CONTACT -> ADD_TAGS(HOSTILE) -> CONTACT_BODY" implies that the ball makes its target hostile, which does not accurately reflect the input "if it hits you it really hurts" (which usually implies damage or knockback).
> **Gameplay Quality (0.75):** The design effectively uses the tag system, particularly the HOSTILE tag to handle the 'hurting' aspect via the automatic Attack/Strike rules. The use of a behavior to ADD_TAGS(HOSTILE) to objects it contacts is a very creative way to represent 'possession' as a spreading infection, which fits the theme perfectly. However, it misses the opportunity to implement the 'bouncing faster and faster' mechanic described in the prompt, which could have been achieved with an APPLY_FORCE behavior. This qualifies as a minor missed opportunity in an otherwise good design.

### firework
**Tags:** SOLID, EXPLOSIVE, HEAT_SOURCE | **Size:** small
- `ON_CREATE -> EXPLODE -> SELF, power=high`
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 11

### explosive barrel
**Tags:** SOLID, RIGID, HEAVY, EXPLOSIVE | **Size:** medium
- `ON_TAG_ADDED(HEAT_SOURCE) -> EXPLODE -> SELF, power=high`
- `ON_TAG_ADDED(ELECTRIC) -> EXPLODE -> SELF, power=high`
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 9
> **Gameplay Quality (0.75):** The design is good and clearly defines the object's identity. The tags chosen (SOLID, RIGID, HEAVY, EXPLOSIVE) create several interaction surfaces including detonation, crushing, and sliding. However, it scores 0.75 rather than 1.0 due to a few missed opportunities: the barrel lacks the BREAKABLE tag, which would allow it to interact with SHARP, CORROSIVE, and other HEAVY objects. Additionally, the behaviors provided are redundant because the 'Detonation' and 'Electrical Detonation' rules already automatically handle explosions when HEAT_SOURCE or ELECTRIC tags are present.

### glass cannon
**Tags:** SOLID, FLEXIBLE, FLOATING, BREAKABLE, SHARP | **Size:** large
- `ON_DAMAGED -> SELF_DESTRUCT -> SELF`
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 0.50 | Sprite Prompt 0.75 | Surface 13
> **Faithfulness (0.75):** The design captures the core concept well, including the floating, shattering, and sharp properties. The visual description also aligns with the "pretty" requirement. However, the tag 'FLEXIBLE' is contradictory for a crystal ball that shatters; 'RIGID' would have been the correct choice. The behavior 'ON_DAMAGED -> SELF_DESTRUCT' covers the shattering mechanic, though 'ON_COLLISION' might have been a closer fit for 'bumps into it'. Overall, it's a strong design with one incorrect tag.
> **Gameplay Quality (0.50):** The design misses the key emergent interaction provided in the rules: "Shrapnel: EXPLOSIVE + SHARP". The prompt describes an object that shatters and cuts everything nearby, which is perfectly modeled by those two tags, but the output omitted EXPLOSIVE. Additionally, the output used the tag FLEXIBLE for a crystal ball (which should be RIGID) and invented a behavior syntax (SELF_DESTRUCT) rather than using the provided categories (like EXPLODE or ADD_TAGS).
> **Sprite Prompt (0.75):** The visual description is excellent, providing clear details on shape (sphere), material (translucent crystal), and color (blue and violet swirling light). It effectively captures the 'pretty' aspect of the prompt. However, it receives a 0.75 because the 'FLEXIBLE' tag is a direct contradiction to the material 'crystal' and the 'BREAKABLE' nature of the object. Additionally, the description mentions swirling light but the 'GLOWING' tag is missing from the tags list.

### sticky honey trap
**Tags:** LIQUID, STICKY | **Size:** large
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 5
> **Faithfulness (0.75):** The design captures the core concept well. The name, visual description, and tags (LIQUID, STICKY) accurately reflect the 'honey' and 'stuck' aspects of the prompt. The size category correctly interprets 'big glob'. The only minor issue is the empty behaviors list; since the player explicitly described the trapping mechanism ('anything that walks into it gets completely stuck'), a corresponding behavior would have been ideal to reinforce the implementation, though the STICKY tag partially covers this.
> **Gameplay Quality (0.75):** The design correctly uses the tag system to create emergent interactions. The 'LIQUID' tag allows for interesting gameplay via the 'Soak' rule (making victims WET, thus susceptible to electricity and freezing), and the 'STICKY' tag handles the physics interaction requested in the prompt. However, it is rated a 0.75 because it misses a key interaction opportunity: 'FLAMMABLE'. Honey is sugar-based and generally considered flammable in game logic; by only having the 'LIQUID' tag, this object would actually extinguish fires (Rule 3), which is a missed opportunity for emergent gameplay (setting the trap on fire). Additionally, using an 'ADD_TAGS(STICKY)' behavior would have better captured the lingering nature of honey.
> **Retries:** 1 — `LIQUID and SOLID cannot coexist. Remove one.`

### death flower
**Tags:** SOLID, FLAMMABLE, TOXIC, GLOWING, BREAKABLE | **Size:** small
- `ON_DESTROY -> SPAWN_PROJECTILE -> NEAREST_LIVING, power=high`
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 14
> **Faithfulness (0.75):** The design captures the core concept well, including the name, appearance, and physical properties (tags). The behavior correctly triggers on destruction and involves poisoning/damage. However, it uses a projectile targeting the 'nearest living' entity rather than a cloud that 'poisons everything in the area' as requested, which is a minor mechanical mismatch.

### acid spider
**Tags:** LIVING, LIGHT, TOXIC | **Size:** tiny
- `ON_PROXIMITY -> SPAWN_PROJECTILE -> NEAREST_PLAYER, power=medium`
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 11
> **Faithfulness (0.75):** The design captures the core concept well, especially the behavior which perfectly matches the trigger and action described. The tags LIVING and LIGHT are appropriate for a "little spider". However, it missed some relevant tags from the provided list: HOSTILE (since it attacks), CORROSIVE (as it uses acid), and GLOWING (as specified in the visual description). Additionally, TOXIC is used which is close to acid, but CORROSIVE is usually more specific. These are minor omissions.
> **Gameplay Quality (0.75):** The design is solid and correctly uses the behavior system to implement the 'spitting' mechanic. It uses the LIVING and TOXIC tags appropriately for a venomous creature. However, it misses two key opportunities for emergent gameplay: 1) It uses TOXIC instead of CORROSIVE, which is the specific tag for acid in this system (and would allow it to interact with RIGID or BREAKABLE objects). 2) The visual description mentions it glows, but it lacks the GLOWING tag, which would have triggered the Bioluminescent Lure interaction.
> **Note:** LIVING object with no movement behaviors

### friendly dog
**Tags:** LIVING, LIGHT, HOSTILE | **Size:** small
- `ON_CONTACT -> ADD_TAGS(HOSTILE) -> NEAREST_OBJECT, power=medium`
**Scores:** Validity 1.00 | Faithfulness 0.25 | Gameplay Quality 0.50 | Sprite Prompt 0.50 | Surface 12
> **Faithfulness (0.25):** The design directly contradicts the player's core request. While it captures the 'dog' aspect (LIVING, LIGHT tags, visual description), it includes the 'HOSTILE' tag and a behavior that spreads hostility, which is the exact opposite of 'friendly'.
> **Gameplay Quality (0.50):** The design is fundamentally contradictory to the input 'friendly dog' by including the 'HOSTILE' tag and a behavior that spreads hostility to other objects on contact. This turns a 'friendly dog' with a 'wagging tail' into a source of generic combat/damage. It also misses basic physical tags like 'SOLID' or 'RIGID' that would define its presence in a physics sandbox, and relies on the 'generic damage' trap of using the HOSTILE tag without complementary interactive tags like 'HOT', 'TOXIC', or 'SHARP'.
> **Sprite Prompt (0.50):** The visual description clearly specifies color and shape, but it significantly contradicts the 'HOSTILE' tag by describing a dog with a 'wagging tail.' Additionally, there is an internal contradiction between the text description ('medium-sized') and the 'size_category' field ('small').
> **Note:** LIVING object with no movement behaviors

### lava monster
**Tags:** LIVING, MOLTEN, HEAT_SOURCE, HOSTILE, SOLID | **Size:** large
- `ALWAYS -> MOVE_TOWARD -> NEAREST_LIVING, power=high`
- `ON_PROXIMITY -> ADD_TAGS(FLAMMABLE) -> CONTACT_BODY`
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 22

### angry bunny
**Tags:** LIVING, FLAMMABLE, LIGHT, HOSTILE | **Size:** small
- `ON_PROXIMITY -> MOVE_AWAY -> NEAREST_PLAYER, power=medium`
- `ON_TAG_ADDED(HEAT_SOURCE) -> ADD_TAGS(HOSTILE, SHARP) -> SELF, power=low`
**Scores:** Validity 1.00 | Faithfulness 0.25 | Gameplay Quality 0.25 | Sprite Prompt 0.75 | Surface 15
> **Faithfulness (0.25):** The design fails to capture the core behavior requested. The player asked for a bunny that gets angry and charges at the player, but the behavior logic provided says it moves away from the player (MOVE_AWAY) on proximity. Additionally, the trigger for becoming aggressive/sharp is related to a HEAT_SOURCE, which was not mentioned and makes no sense in the context of the prompt. While the visual description tries to bridge the gap, the actual game logic works against the player's intent.
> **Gameplay Quality (0.25):** The design fails to implement the user's request for a bunny that "gets more and more angry" and "eventually just charges." Instead, the behavior logic specifies that it should move AWAY from the player on proximity. Additionally, the behavior `ADD_TAGS(HOSTILE)` is redundant because the bunny already has the `HOSTILE` tag in its base tags. While it does include an interesting interaction with `HEAT_SOURCE`, it completely misses the primary behavioral request.
> **Sprite Prompt (0.75):** The description specifies the shape (bunny), material (fluffy fur), and colors (white, red). It matches the tags provided. However, it includes dynamic/situational language ("increasingly red eyes... as it gets closer to the player") which describes an interaction or scene rather than a static visual state, which is slightly contrary to the requirement to describe the object itself and not a scene. This situational detail might confuse a static image generator.

### electric jellyfish
**Tags:** LIVING, ELECTRIC, FLOATING | **Size:** small
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 0.50 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 19
> **Faithfulness (0.50):** The design misses the requested 'glows in the dark' feature in the tags (the 'GLOWING' tag is available but not used). Additionally, the behavior 'shocks anything that gets close to its tentacles' is completely omitted from the behaviors list, which is left empty. While the name and visual description are accurate, these are notable gaps in the functional design of the object.
> **Gameplay Quality (0.75):** The design correctly identifies the core 'ELECTRIC' and 'LIVING' nature of the creature, which triggers the 'Electric Shock' interaction automatically. However, it misses the 'GLOWING' tag which was explicitly requested ('glows in the dark') and would have created an emergent gameplay loop with the 'Bioluminescent Lure' interaction (attracting other living things into the electric tentacles). This is a minor missed opportunity as per the 0.75 rubric criteria.
> **Note:** LIVING object with no movement behaviors
> **Retries:** 1 — `Name "Deep Sea Shock Jelly" has 4 words. Use 1-3 words maximum.`

### wind spirit
**Tags:** LIVING, GAS, WIND_SOURCE, LIGHT, FLOATING | **Size:** small
- `ALWAYS -> MOVE_TOWARD -> NEAREST_OBJECT, power=medium`
- `ON_CREATE -> ADD_TAGS(FLOATING) -> SELF`
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 15

### toxic frog
**Tags:** LIVING, TOXIC, COLD, HOSTILE | **Size:** small
- `ON_PROXIMITY -> ADD_TAGS(TOXIC) -> CONTACT_BODY`
- `ALWAYS -> MOVE_TOWARD -> NEAREST_LIVING, power=medium`
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 16

### mirror golem
**Tags:** SOLID, RIGID, HEAVY, REFLECTIVE | **Size:** large
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 8
> **Faithfulness (0.75):** The design captures the core concept of a Mirror Golem well. The name and visual description are accurate. The tags (SOLID, RIGID, HEAVY, REFLECTIVE) are all appropriate. However, it misses the specific mechanic mentioned in the input—"reflects everything back at you - fire, lightning, whatever you throw at it bounces right back"—by leaving the behaviors list empty and omitting the BOUNCY tag which would represent things "bouncing right back". Additionally, as a 'golem', the LIVING or HOSTILE tags might have been appropriate. Regardless, the core concept is well-represented.
> **Gameplay Quality (0.75):** The design correctly identifies the REFLECTIVE tag to handle the specific examples of fire and lightning reflection mentioned in the prompt. However, it misses the opportunity to use the BOUNCY tag to fulfill the "whatever you throw at it bounces right back" (physical reflection) requirement. Additionally, as a 'golem', it lacks the LIVING or HOSTILE tags and movement behaviors that would make it act as a creature rather than a static object.

### lasso vine
**Tags:** LIVING, FLEXIBLE, STICKY, HOSTILE | **Size:** medium
- `ON_PROXIMITY -> ATTRACT -> NEAREST_OBJECT, power=high`
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 12
> **Gameplay Quality (0.75):** The design is solid and effectively uses the behavior system to implement the 'lasso' mechanic (ATTRACT) which the tag system doesn't handle natively. The use of FLEXIBLE is clever as it provides a built-in defense against SHARP objects (Flex Resist). However, it is a 0.75 because of several missed opportunities for emergent gameplay based on its own visual description. The 'glowing purple sap' and 'thorny protrusions' could have been mapped to GLOWING, TOXIC, and SHARP tags. Specifically, adding GLOWING to a LIVING object would have triggered the 'Bioluminescent Lure' interaction, creating a more complex and automated 'predator' behavior.
> **Note:** LIVING object with no movement behaviors

### cowardly slime
**Tags:** LIVING, FLEXIBLE, LIQUID | **Size:** small
- `ON_PROXIMITY -> MOVE_AWAY -> CONTACT_BODY, power=high`
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 15

### phoenix egg
**Tags:** SOLID, BREAKABLE, FLAMMABLE | **Size:** small
- `ON_DAMAGED -> EXPLODE -> SELF, power=medium`
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 0.50 | Sprite Prompt 1.00 | Surface 11
> **Faithfulness (0.75):** The design captures the core concept well, specifically the "totally normal" appearance and the "bursts into flames" (via EXPLODE) upon being damaged. However, it misses the specific request for a "firebird" to come out, as there is no SPAWN behavior or similar mechanism included to represent the creature. The tags and visual description are appropriate for the "normal" exterior requested.
> **Gameplay Quality (0.50):** The design is mediocre because it completely ignores the "firebird" aspect of the prompt, which is the most defining characteristic requested. It functions as a simple explosive trap, but misses the opportunity to use the tag system for emergent gameplay. Specifically, it uses a behavior to trigger an explosion rather than leveraging the 'EXPLOSIVE' tag and 'HEAT_SOURCE' interaction, and it lacks any tags or behaviors (like ADD_TAGS for HEAT_SOURCE) that would make the "bursting into flames" affect the environment beyond a simple one-time damage event.

### patrol bot
**Tags:** SOLID, RIGID, LIVING, HOSTILE | **Size:** small
- `ALWAYS -> MOVE_TOWARD -> NEAREST_OBJECT`
- `ON_PROXIMITY -> SPAWN_PROJECTILE -> NEAREST_PLAYER, power=high`
**Scores:** Validity 1.00 | Faithfulness 0.50 | Gameplay Quality 0.50 | Sprite Prompt 0.75 | Surface 13
> **Faithfulness (0.50):** The design captures the shooting aspect and the visual description well. However, the movement behavior 'ALWAYS -> MOVE_TOWARD -> NEAREST_OBJECT' directly contradicts the player's request for a robot that 'walks back and forth guarding an area'. Instead of patrolling, this behavior would cause the robot to pursue or get stuck on any nearby object. Additionally, while there is no 'ROBOT' tag, the 'LIVING' tag is a questionable choice for a machine, though 'HOSTILE' is appropriate.
> **Gameplay Quality (0.50):** The design is functional but mediocre. It misses significant opportunities to use the tag system for emergent gameplay. As a robot, it should likely have tags like CONDUCTING or MAGNETIC to interact with electricity and magnets, but instead, it uses a generic set of tags. Furthermore, the behavior 'MOVE_TOWARD -> NEAREST_OBJECT' contradicts the prompt's request for a 'patrol' behavior (which is an available behavior type in the system) and would likely cause the robot to get stuck against wall or random debris rather than guarding an area. It falls into the generic damage/behavior trap.
> **Sprite Prompt (0.75):** The visual description is clear and describes a distinctive object with specific features (boxy shape, treads, glowing red eye, spinning barrel antenna). It follows the 1-2 sentence constraint and describes the object rather than a scene. However, it misses the main body color (only mentioning the red eye) and has minor tag inconsistencies: the description mentions 'glowing' but the 'GLOWING' tag is missing, and 'LIVING' is used for a robot, which is conceptually slightly off, though common in some game systems.
> **Retries:** 1 — `Invalid behavior 'ON_TIMER -> MOVE_TOWARD -> CONTACT_BODY, power=medium': 1 validation error for BehaviorSpec
  Value error, CONTACT_BODY target requires ON_CONTACT, ON_DAMAGED, or ON_PROXIMITY trigger, not ON_TIMER. [type=value_error, input_value={'trigger': <BehaviorTrig..., 'tags_to_apply': None}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/value_error
Expected: TRIGGER -> ACTION -> TARGET
Example: ON_TAG_ADDED(HEAT_SOURCE) -> EXPLODE -> SELF, power=high`

### electric lava golem
**Tags:** SOLID, RIGID, HEAVY, HEAT_SOURCE, ELECTRIC, HOSTILE | **Size:** large
- `ALWAYS -> MOVE_TOWARD -> NEAREST_LIVING, power=medium`
- `ON_CONTACT -> ADD_TAGS(ELECTRIC) -> CONTACT_BODY`
- `ON_TAG_ADDED(HOT) -> SPAWN_PROJECTILE -> NEAREST_PLAYER, power=high`
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 25
> **Faithfulness (0.75):** The design captures the core concept well. The name and visual description perfectly match the player's request for a lava/lightning boss golem. The tags are accurate, although the 'MOLTEN' or 'HOT' tags were omitted. The 'shoots lightning' request is handled via a behavior, though the trigger (ON_TAG_ADDED(HOT)) is somewhat unintuitive for a character already made of lava. Overall, it is a very strong representation of the concept.

### the sun
**Tags:** HEAT_SOURCE, HOT, GLOWING, LIQUID, MOLTEN | **Size:** huge
- `ON_PROXIMITY -> ADD_TAGS(HOT) -> NEAREST_LIVING, power=high`
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 17
> **Faithfulness (0.75):** The design captures the core concept of the sun very well with its name, visual description, and key tags like HEAT_SOURCE, HOT, and GLOWING. However, it includes the tags LIQUID and MOLTEN, which are technically inaccurate as the sun is a plasma (best represented by GAS in the provided list). This is a minor issue in the physical representation.
> **Retries:** 1 — `Invalid behavior 'ALWAYS -> MOVE_AWAY -> SELF, power=medium': 1 validation error for BehaviorSpec
  Value error, MOVE_AWAY needs a target to move toward/away from. SELF is not valid. Use NEAREST_OBJECT, NEAREST_LIVING, NEAREST_PLAYER, or CONTACT_BODY. [type=value_error, input_value={'trigger': <BehaviorTrig..., 'tags_to_apply': None}, input_type=dict]
    For further information visit https://errors.pydantic.dev/2.12/v/value_error
Expected: TRIGGER -> ACTION -> TARGET
Example: ON_TAG_ADDED(HEAT_SOURCE) -> EXPLODE -> SELF, power=high`

### tiny black hole
**Tags:** HEAVY, MAGNETIC, BREAKABLE | **Size:** tiny
- `ON_PROXIMITY -> ATTRACT -> NEAREST_OBJECT, power=high`
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 12
> **Faithfulness (0.75):** The design captures the core concept well. The name and visual description are perfect. The behavior 'ON_PROXIMITY -> ATTRACT' correctly implements the 'sucks everything in' requirement. Among the limited 32 tags, 'HEAVY' is appropriate. 'MAGNETIC' is used as a proxy for attraction which is acceptable given the tag list. 'BREAKABLE' is slightly contradictory as black holes are not typically destructible in that way, but it is a minor issue.

### sadness
**Tags:** LIQUID, COLD, TOXIC, LIGHT, GLOWING | **Size:** small
- `ON_CREATE -> ADD_TAGS(COLD) -> SELF, power=medium`
- `ON_CONTACT -> REMOVE_TAGS(LIVING) -> CONTACT_BODY, power=low`
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 12
> **Gameplay Quality (0.75):** The design uses the tag system effectively to create emergent interactions: it lures creatures (Glowing + Living), poisons them (Toxic + Living), and is susceptible to wind (Light + Wind Source). It also interacts with temperature and fire (Cold, Liquid). The behavior 'REMOVE_TAGS(LIVING)' is a thematic way to handle 'sadness' that complements the toxic tag. However, the behavior 'ADD_TAGS(COLD)' to 'SELF' on create is redundant as the object already possesses the COLD tag.

### indiana jones boulder
**Tags:** SOLID, RIGID, HEAVY, BREAKABLE | **Size:** huge
- `ALWAYS -> MOVE_TOWARD -> NEAREST_PLAYER, power=high`
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 12

### frozen fire
**Tags:** SOLID, FROZEN, HEAT_SOURCE, COLD | **Size:** small
- `ON_CONTACT -> ADD_TAGS(FROZEN) -> CONTACT_BODY, power=medium`
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 14
> **Faithfulness (0.75):** The design effectively captures the oxymoronic concept of "frozen fire" with an appropriate name and a strong visual description. The physical properties for the "frozen" aspect (SOLID, FROZEN, COLD) are well-represented, and the behavior (freezing on contact) fits the theme. However, there are minor tag issues: the HEAT_SOURCE tag contradicts the visual description stating it "emits no heat," and it is missing the GLOWING or LIGHT tags which are standard for fire-based objects.

### a thing
**Tags:** SOLID, RIGID, HOSTILE, LIVING, GLOWING | **Size:** large
- `ALWAYS -> MOVE_TOWARD -> NEAREST_LIVING, power=medium`
- `ON_DAMAGED -> ADD_TAGS(SHARP) -> SELF, power=high`
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 13
> **Gameplay Quality (0.75):** The design is clever and uses the tag system effectively, particularly the ON_DAMAGED behavior which dynamically adds the SHARP tag to change its interaction profile. However, it falls into the 0.75 category due to a missed opportunity: the visual description explicitly mentions a magma core, but the object lacks the HOT or MOLTEN tags, which would have allowed it to interact with the game's thermal/ignition rules. It also lacks the HEAVY tag expected of a boulder.

### indestructible wall
**Tags:** SOLID, RIGID, HEAVY | **Size:** large
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 5
> **Gameplay Quality (0.75):** The design effectively uses the tag system by omitting the BREAKABLE tag, making the wall immune to the majority of destructive interactions (Cut, Crush, Blast Destruction, etc.). It correctly identifies that no behaviors are needed for a static object. However, it misses a minor interaction: the RIGID tag makes the object vulnerable to 'Structural Corrosion' from CORROSIVE objects. To truly be 'literally nothing can break', it should have avoided the RIGID tag or added REFLECTIVE for acid resistance.

### fiar swrod
**Tags:** SOLID, RIGID, SHARP, HEAT_SOURCE | **Size:** small
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 14

### shield request
**Tags:** SOLID, RIGID, HEAVY | **Size:** small
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 5
> **Gameplay Quality (0.75):** The design uses the core physics tags (SOLID, RIGID, HEAVY) correctly to define a functional physics object, matching the rubric's example of a 1.0 design (a rock). However, since the visual description specifies it is a 'metal' buckler, the omission of the CONDUCTING tag is a minor missed opportunity for emergent gameplay (magnetism, electricity, metal-specific corrosion), and the REFLECTIVE tag would have been a great fit for a shield to interact with heat and electric sources. It follows the user's 'nothing fancy' constraint well.

### rambling glowing sword
**Tags:** SOLID, RIGID, SHARP, HEAT_SOURCE, GLOWING | **Size:** huge
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 15

### not heavy floaty thing
**Tags:** SOLID, FLEXIBLE, LIGHT, FLOATING, GLOWING | **Size:** small
- `ALWAYS -> MOVE_TOWARD -> NEAREST_OBJECT, power=low`
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 5

### acid rain cloud
**Tags:** GAS, CORROSIVE, HOT, FLOATING | **Size:** large
- `ON_PROXIMITY -> ADD_TAGS(CORROSIVE) -> CONTACT_BODY`
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 11
> **Faithfulness (0.75):** The design captures the core concept very well. The name and visual description are perfect. Most tags (GAS, CORROSIVE, FLOATING) are highly appropriate. The behavior effectively simulates the "raining" aspect by applying a corrosive effect to nearby bodies. However, the 'HOT' tag is slightly off/irrelevant for standard acid rain compared to more fitting tags like 'TOXIC' or 'WET', which are available in the list. This minor issue aligns with the 0.75 score description.

### ice shield
**Tags:** SOLID, RIGID, COLD, REFLECTIVE | **Size:** large
- `ON_CONTACT -> ADD_TAGS(FROZEN) -> CONTACT_BODY`
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 9

### magnet
**Tags:** SOLID, RIGID, MAGNETIC, GLOWING | **Size:** small
- `ON_CREATE -> SPAWN_PROJECTILE -> NEAREST_OBJECT, power=low`
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 5
> **Faithfulness (0.75):** The design captures the core concept of a magnet with appropriate tags (SOLID, RIGID, MAGNETIC) and a very fitting visual description. The addition of the GLOWING tag matches the visual description provided. The behavior "SPAWN_PROJECTILE" on creation is a bit of a strange interpretation of magnetic force, but it doesn't detract significantly from the overall concept.
> **Gameplay Quality (0.75):** The design correctly identifies the core tag (MAGNETIC) to enable its primary gameplay function (attracting CONDUCTING objects). It also includes SOLID and RIGID for physical presence. However, it misses the CONDUCTING tag, which would allow for more emergent interactions like metal dissolution or heat/cold conduction, especially since magnets are typically metallic. The visual description mentions 'static electricity' but the ELECTRIC tag is missing. Additionally, the behavior (SPAWN_PROJECTILE on create) feels arbitrary and doesn't strongly complement the magnet theme.

### healing mushroom
**Tags:** SOLID, FLEXIBLE, GLOWING | **Size:** small
- `ON_CONTACT -> HEAL -> NEAREST_LIVING`
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 2

### conductor rod
**Tags:** SOLID, RIGID, CONDUCTING | **Size:** small
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 7

### spring trap
**Tags:** SOLID, RIGID, BOUNCY, LIGHT | **Size:** medium
- `ON_CONTACT -> APPLY_FORCE -> CONTACT_BODY, power=high`
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 3

### campfire
**Tags:** SOLID, HEAT_SOURCE, GLOWING | **Size:** small
- `ON_PROXIMITY -> ADD_TAGS(INSULATING) -> CONTACT_BODY, power=low`
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 9
> **Gameplay Quality (0.75):** The tags (HEAT_SOURCE, GLOWING, SOLID) are excellently chosen and create a wide variety of automatic interactions (Ignition, Melting, Extinguish, Evaporation, Luring, etc.). This makes the object highly interactive in a 2D sandbox. The design only loses points because the behavior used (ADD_TAGS(INSULATING)) to represent 'warmth/healing' is less effective and less clear than the available HEAL behavior, and INSULATING doesn't have a specific interaction rule for warmth in the provided list.

### rubber armor
**Tags:** SOLID, FLEXIBLE, INSULATING | **Size:** medium
- `ON_PROXIMITY -> ADD_TAGS(INSULATING) -> CONTACT_BODY`
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 0.50 | Sprite Prompt 1.00 | Surface 1
> **Gameplay Quality (0.50):** The design uses the 'INSULATING' tag as its core mechanic, but according to the provided Interaction Rules, 'INSULATING' does not participate in any of the 53 defined interactions. This makes the object inert in the game's simulation. While the behavior 'ADD_TAGS(INSULATING) -> CONTACT_BODY' is a clever way to simulate wearing armor, it spreads a tag that has no gameplay effect. The use of 'FLEXIBLE' is a good minor interaction (resisting SHARP), but the primary goal of the object (insulating against electricity) is not achieved within the mechanics provided.

### helicopter
**Tags:** SOLID, HEAVY, WIND_SOURCE, LIVING | **Size:** large
- `ALWAYS -> MOVE_TOWARD -> NEAREST_LIVING, power=medium`
- `ON_PROXIMITY -> APPLY_FORCE -> CONTACT_BODY`
**Scores:** Validity 1.00 | Faithfulness 0.50 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 15
> **Faithfulness (0.50):** The design captures the visual and name of a helicopter well, and 'WIND_SOURCE' is a very appropriate tag. However, there are two significant issues: 1) It includes the 'LIVING' tag, which is a categorical error for a machine. 2) It is missing the 'FLOATING' tag (which is in the allowed list), meaning the helicopter would not stay in the air, and the behaviors provided would cause it to move toward targets while dragging along the ground. These issues constitute notable gaps in representing the core concept of a helicopter.

### hot air balloon
**Tags:** GAS, LIGHT, FLOATING | **Size:** large
- `ALWAYS -> MOVE_TOWARD -> NEAREST_OBJECT, power=low`
**Scores:** Validity 1.00 | Faithfulness 0.50 | Gameplay Quality 0.50 | Sprite Prompt 1.00 | Surface 6
> **Faithfulness (0.50):** The design correctly identifies the name, tags, and visual description. However, the behavior provided ('MOVE_TOWARD -> NEAREST_OBJECT') contradicts the player's specific request for the balloon to 'float upward'. Instead of rising vertically, the balloon would track and move toward the nearest object, which is a significant functional error.
> **Gameplay Quality (0.50):** The design misses the core characteristics of a 'Hot Air' balloon—specifically, it lacks the 'HOT' or 'HEAT_SOURCE' tags and the 'FLAMMABLE' tag. Furthermore, the behavior 'MOVE_TOWARD -> NEAREST_OBJECT' directly contradicts the prompt's request for an object that 'slowly floats upward,' instead turning the balloon into a seeker that would likely collide with the ground or nearby walls. While 'FLOATING' and 'LIGHT' are appropriate for interaction with wind and anchors, the overall execution fails the specific prompt requirements and misses the most interesting tag interactions for this specific object.

### jetpack
**Tags:** SOLID, HEAVY, WIND_SOURCE, FLAMMABLE | **Size:** small
- `ON_DAMAGED -> ADD_TAGS(HEAT_SOURCE) -> SELF`
- `ON_TAG_ADDED(HEAT_SOURCE) -> EXPLODE -> SELF`
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 1.00 | Sprite Prompt 0.75 | Surface 9
> **Sprite Prompt (0.75):** The visual description provides clear details about the object's shape (bulky backpack, exhaust pipes, fuel tank) and materials (metallic, thick straps), which align well with the tags (SOLID, HEAVY, WIND_SOURCE). However, it does not explicitly specify a color, which according to the rubric results in a score of 0.75.

### wooden raft
**Tags:** SOLID, FLOATING, RIGID | **Size:** large
- `ALWAYS -> MOVE_TOWARD -> NEAREST_PLAYER, power=low`
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 0.75 | Sprite Prompt 0.75 | Surface 4
> **Gameplay Quality (0.75):** The design correctly identifies the 'FLOATING' and 'RIGID' tags which create meaningful interactions with the environment (e.g., Wind Launch and Weight Anchor). However, as a 'wooden' object, it misses the 'FLAMMABLE' tag, which is a key interaction surface in this system. The behavior 'MOVE_TOWARD PLAYER' is a bit odd for an inanimate raft, but functional.
> **Sprite Prompt (0.75):** The visual description clearly specifies the shape (platform, three logs, flat deck, mast base), materials (rough-hewn logs, rope, wood), and distinctive features. It is consistent with the name and tags. However, it lacks an explicit mention of colors, which places it at 0.75 according to the rubric.

### rope
**Tags:** SOLID, FLEXIBLE | **Size:** small
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 1
> **Faithfulness (0.75):** The design captures the core concept well. The tags 'SOLID' and 'FLEXIBLE' are appropriate for a rope. However, the size category 'small' contradicts the player's request for a 'long' rope, which is a minor mismatch.
> **Gameplay Quality (0.75):** The design correctly identifies the core physical properties of a rope (SOLID and FLEXIBLE), which enables specific interaction rules like 'Flex Resist'. However, it misses a few obvious emergent gameplay opportunities typical for a rope, such as being FLAMMABLE or LIGHT (to interact with wind). The size 'small' for a 'long rope' is justified by the visual description of it being coiled. Overall, it's a solid, functional design with minor missed opportunities for richer interactions.
> **Retries:** 2 — `Invalid behavior 'ON_PROXIMITY -> ADD_TAGS(FIXED) -> SELF, power=low': Unknown tag 'FIXED'. Valid: SOLID, LIQUID, GAS, RIGID, FLEXIBLE, HEAVY, LIGHT, FROZEN, COLD, HOT, MOLTEN, FLAMMABLE, HEAT_SOURCE, ELECTRIC, MAGNETIC, EXPLOSIVE, SHARP, STICKY, SLIPPERY, REFLECTIVE, BOUNCY, BREAKABLE, FLOATING, WIND_SOURCE, CORROSIVE, TOXIC, WET, LIVING, GLOWING, CONDUCTING, INSULATING, HOSTILE
Expected: TRIGGER -> ACTION -> TARGET
Example: ON_TAG_ADDED(HEAT_SOURCE) -> EXPLODE -> SELF, power=high; Invalid behavior 'ON_CONTACT -> ADD_TAGS(ANCHOR) -> SELF, power=low': Unknown tag 'ANCHOR'. Valid: SOLID, LIQUID, GAS, RIGID, FLEXIBLE, HEAVY, LIGHT, FROZEN, COLD, HOT, MOLTEN, FLAMMABLE, HEAT_SOURCE, ELECTRIC, MAGNETIC, EXPLOSIVE, SHARP, STICKY, SLIPPERY, REFLECTIVE, BOUNCY, BREAKABLE, FLOATING, WIND_SOURCE, CORROSIVE, TOXIC, WET, LIVING, GLOWING, CONDUCTING, INSULATING, HOSTILE
Expected: TRIGGER -> ACTION -> TARGET
Example: ON_TAG_ADDED(HEAT_SOURCE) -> EXPLODE -> SELF, power=high`

### bridge
**Tags:** SOLID, RIGID, HEAVY | **Size:** large
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 5
> **Gameplay Quality (0.75):** The design captures the physical essence of a bridge well with SOLID, RIGID, and HEAVY, allowing for interactions like structural corrosion, bouncing, and crushing. However, the input specifies it is a 'wooden' bridge, and the design misses the FLAMMABLE tag, which is explicitly noted in the rubric as a minor missed opportunity (0.75). It could also benefit from the BREAKABLE tag to interact with explosions or heavy impacts.

### trampoline
**Tags:** SOLID, FLEXIBLE, BOUNCY | **Size:** medium
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 2

### ladder
**Tags:** SOLID, RIGID, BREAKABLE | **Size:** large
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 10
> **Gameplay Quality (0.75):** The design captures the essential physical properties of a ladder (SOLID, RIGID, BREAKABLE). However, the visual description explicitly identifies it as a "wooden structure," yet it lacks the FLAMMABLE tag. The rubric specifically identifies a wooden object without FLAMMABLE as an example of a 0.75 score.

### parachute
**Tags:** FLEXIBLE, LIGHT, WET | **Size:** small
- `ON_TAG_ADDED(WET) -> ADD_TAGS(LIGHT) -> SELF, power=low`
- `ON_CONTACT -> REMOVE_TAGS(LIGHT) -> SELF`
**Scores:** Validity 1.00 | Faithfulness 0.25 | Gameplay Quality 1.00 | Sprite Prompt 0.75 | Surface 5
> **Faithfulness (0.25):** The design fails to capture the core functionality requested by the user. While the name and visual description are appropriate for a parachute, the behaviors do not address slowing down a fall. The logic provided (becoming LIGHT only when the WET tag is added) is nonsensical and unrelated to the prompt. Furthermore, the inclusion of the WET tag as a starting property for a parachute is inappropriate, and the design fails to utilize more relevant tags from the provided list, such as FLOATING.
> **Sprite Prompt (0.75):** The description is clear and specifies shape (crumpled bundle, backpack frame), materials (nylon, suspension lines), and colors (multicolored). It is a single sentence and focuses on the object itself. However, it fails to visually represent the 'WET' tag included in the metadata, which is a minor gap.

### giant fan
**Tags:** SOLID, RIGID, WIND_SOURCE | **Size:** large
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 5
> **Gameplay Quality (0.75):** The design correctly identifies the core tag needed for the requested functionality (WIND_SOURCE). It uses the tag system to handle the primary interaction without redundant behaviors. However, it misses a few interaction opportunities suggested by its own visual description: the "heavy base" implies the HEAVY tag, and an industrial metal fan would typically be CONDUCTING and ELECTRIC, which would create more emergent gameplay loops in a physics sandbox.

### torch
**Tags:** SOLID, HEAT_SOURCE, GLOWING | **Size:** small
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 9
> **Gameplay Quality (0.75):** The design correctly identifies the most important functional tags for a burning torch: HEAT_SOURCE (for lighting fires and melting ice) and GLOWING (for illumination and attracting living creatures). However, it misses the FLAMMABLE tag, which is explicitly mentioned in the rubric as a missed opportunity for wooden objects. Without FLAMMABLE, the torch cannot be relit if extinguished and doesn't behave like wood in fire-spreading scenarios. It also lacks basic physical descriptors like BREAKABLE or LIGHT (for wind interaction).
> **Retries:** 2 — `FLAMMABLE and HEAT_SOURCE cannot coexist. Remove one.; FLAMMABLE and HEAT_SOURCE cannot coexist. Remove one.`

### umbrella
**Tags:** SOLID, RIGID, BOUNCY | **Size:** small
- `ON_PROXIMITY -> ADD_TAGS(FLOATING) -> SELF, power=low`
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 2
> **Faithfulness (0.75):** The design captures the core concept of an umbrella shield intended to block items. The name and visual description are very accurate. The tags 'SOLID' and 'RIGID' are appropriate for a protective object, although 'BOUNCY' is a slight creative liberty. The behavior (becoming floating on proximity) is a bit unconventional for a standard umbrella but suggests a gameplay mechanic to help it stay aloft or react to falling objects. Overall, it's a strong design with minor behavioral quirks.

### treasure chest
**Tags:** SOLID, RIGID, BREAKABLE | **Size:** medium
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 0.75 | Sprite Prompt 0.75 | Surface 10
> **Gameplay Quality (0.75):** The design is solid but misses a key interaction opportunity mentioned in the rubric: it is a wooden chest but lacks the FLAMMABLE tag. It also misses CONDUCTING/MAGNETIC for the iron straps and HEAVY for a treasure chest, which would have increased its interaction surface.
> **Sprite Prompt (0.75):** The visual description clearly describes the object's shape (chest), materials (wood, iron), and distinctive features (ornate lock, carvings). It follows the length constraint and focuses on the object without a scene. However, it misses explicit color mentions (e.g., brown wood, grey iron), which places it at the 0.75 level according to the rubric. The tags are valid and consistent with the description.

### tree
**Tags:** SOLID, RIGID, HEAVY, BREAKABLE | **Size:** huge
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 12
> **Faithfulness (0.75):** The design captures the core concept of a big oak tree well. The name and visual description are perfect. The tags provided (SOLID, RIGID, HEAVY, BREAKABLE) are all appropriate. However, it missed two highly relevant tags available in the list: LIVING and FLAMMABLE, which are core characteristics of a tree in a physics sandbox.
> **Gameplay Quality (0.75):** The design includes appropriate physical tags for a large object (SOLID, RIGID, HEAVY, BREAKABLE), allowing for interactions like being chopped down (SHARP + BREAKABLE) or crushing things (HEAVY + BREAKABLE). However, it missed the most crucial interactions for a tree in this system: FLAMMABLE and LIVING. The rubric specifically cites 'a wooden object without FLAMMABLE' as an example of a 0.75 score.

### ice block
**Tags:** SOLID, RIGID, FROZEN, COLD | **Size:** medium
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 9

### puddle
**Tags:** LIQUID, WET | **Size:** small
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 8
> **Faithfulness (0.75):** The design captures the core concept well. The name and visual description are perfect. The tags "LIQUID" and "WET" are accurate. However, it misses the "REFLECTIVE" tag despite the visual description explicitly mentioning it reflects surroundings, and "SLIPPERY" would also be a highly relevant tag for a puddle in a physics sandbox.
> **Gameplay Quality (0.75):** The design is solid and correctly uses the core tags LIQUID and WET, which trigger many interactions (extinguishing, freezing, electrifying, evaporating). However, it misses the SLIPPERY tag, which is a primary gameplay interaction for a puddle on the ground (Heavy Slide). It also mentions reflection in the visual description but omits the REFLECTIVE tag, which would have added interactions with heat and electricity. This makes it a good design with minor missed opportunities.

### pegasus
**Tags:** LIVING, FLEXIBLE, FLAMMABLE, GLOWING, LIGHT | **Size:** large
- `ALWAYS -> MOVE_TOWARD -> NEAREST_LIVING, power=high`
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 14
> **Faithfulness (0.75):** The design captures the core concept of a Pegasus perfectly in its name and visual description. The tags effectively represent its physical and mystical nature (LIVING, FLEXIBLE, GLOWING). However, while the player explicitly asked for an object that "can fly," the design omits the 'FLOATING' tag, which is the standard way to enable flight in a 2D physics sandbox. The behavior allows for movement, but the lack of the floating property is a minor oversight relative to the specific prompt.
> **Gameplay Quality (0.75):** The design uses the tag system effectively to create emergent gameplay. The use of GLOWING on a LIVING creature triggers the 'Bioluminescent Lure' interaction, which fits the majestic visual description perfectly. FLEXIBLE provides a specific physics interaction (Flex Resist) against SHARP objects. The main reason for not being a 1.0 is the missed opportunity with the 'flying' requirement: while the LIGHT tag allows for 'Wind Push', the FLOATING tag would have enabled the 'Wind Launch' interaction, which is more appropriate for a winged creature.

### pack mule
**Tags:** LIVING, HEAVY, SOLID | **Size:** large
- `ALWAYS -> MOVE_TOWARD -> NEAREST_PLAYER, power=medium`
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 12
> **Gameplay Quality (0.75):** The design is good and fulfills the prompt requirements. It uses LIVING and HEAVY tags which have many interaction surfaces (crushing items, susceptibility to heat/poison/cold). The behavior correctly implements the 'following' requirement. It misses a 1.0 because it doesn't quite address the 'carrying' aspect through the tag system (e.g., using STICKY to keep items attached, or ATTRACT to hold them), and uses SOLID which has fewer interaction rules than RIGID.
> **Retries:** 2 — `Invalid behavior 'ON_TAG_ADDED(GOLD) -> ADD_TAGS(CARRYING) -> SELF, power=medium': Unknown tag 'GOLD'. Valid: SOLID, LIQUID, GAS, RIGID, FLEXIBLE, HEAVY, LIGHT, FROZEN, COLD, HOT, MOLTEN, FLAMMABLE, HEAT_SOURCE, ELECTRIC, MAGNETIC, EXPLOSIVE, SHARP, STICKY, SLIPPERY, REFLECTIVE, BOUNCY, BREAKABLE, FLOATING, WIND_SOURCE, CORROSIVE, TOXIC, WET, LIVING, GLOWING, CONDUCTING, INSULATING, HOSTILE
Expected: TRIGGER -> ACTION -> TARGET
Example: ON_TAG_ADDED(HEAT_SOURCE) -> EXPLODE -> SELF, power=high; Invalid behavior 'ON_CONTACT -> ADD_TAGS(ON_BACK) -> CONTACT_BODY, power=low': Unknown tag 'ON_BACK'. Valid: SOLID, LIQUID, GAS, RIGID, FLEXIBLE, HEAVY, LIGHT, FROZEN, COLD, HOT, MOLTEN, FLAMMABLE, HEAT_SOURCE, ELECTRIC, MAGNETIC, EXPLOSIVE, SHARP, STICKY, SLIPPERY, REFLECTIVE, BOUNCY, BREAKABLE, FLOATING, WIND_SOURCE, CORROSIVE, TOXIC, WET, LIVING, GLOWING, CONDUCTING, INSULATING, HOSTILE
Expected: TRIGGER -> ACTION -> TARGET
Example: ON_TAG_ADDED(HEAT_SOURCE) -> EXPLODE -> SELF, power=high`

### health potion
**Tags:** LIQUID, GLOWING | **Size:** small
- `ON_CONTACT -> HEAL -> NEAREST_LIVING`
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 6
> **Gameplay Quality (0.75):** The design effectively uses the tag system to create emergent gameplay, particularly with the GLOWING tag acting as a lure (GLOWING + LIVING) and the LIQUID tag allowing the potion to interact with heat, cold, and electricity. However, it misses a minor opportunity: the visual description specifies a 'glass vial,' but the object lacks the BREAKABLE or RIGID tags. This means the object won't shatter or behave like a container in the physics engine, which is a standard interaction for potions.

### apple
**Tags:** SOLID, BREAKABLE, WET | **Size:** small
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 11
> **Faithfulness (0.75):** The design captures the core concept of an apple very well. The name and visual description are perfect. Most tags (SOLID, BREAKABLE) are accurate. The 'WET' tag is slightly off as a core physical property of an apple, but it doesn't ruin the design. The size category is correct.

### something to fly
**Tags:** SOLID, FLEXIBLE, FLOATING | **Size:** medium
- `ON_PROXIMITY -> APPLY_FORCE -> NEAREST_LIVING, power=medium`
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 3
> **Gameplay Quality (0.75):** The design effectively uses the tag system to create interaction surfaces for wind (FLOATING) and physical resistance (FLEXIBLE). The behavior (APPLY_FORCE on proximity) is a clever way to implement a flight mechanic that tags alone cannot handle. However, there are minor missed opportunities for more emergent gameplay: the visual description mentions a 'metallic frame' but the object lacks the CONDUCTING tag (which would allow interactions with electricity, magnets, and heat), and it lacks the LIGHT tag despite being described as a 'lightweight fabric wing' (missing the Wind Push interaction).

### gap crosser
**Tags:** SOLID, FLEXIBLE, BOUNCY, LIGHT | **Size:** large
- `ON_TAG_ADDED(SOLID) -> ADD_TAGS(REFLECTIVE) -> SELF, power=medium`
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 3
> **Gameplay Quality (0.75):** The object uses a good set of tags (SOLID, FLEXIBLE, BOUNCY, LIGHT) that create meaningful interaction surfaces (resisting SHARP, reacting to WIND_SOURCE, and bouncing). The behavior logic is slightly flawed because the object starts with the SOLID tag, making the ON_TAG_ADDED(SOLID) trigger redundant or confusing, but the overall design is functional and fits the prompt well.

### lava protection
**Tags:** SOLID, RIGID, REFLECTIVE, HEAVY | **Size:** small
- `ON_CONTACT -> ADD_TAGS(INSULATING) -> CONTACT_BODY, power=medium`
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 8

### helecopter
**Tags:** SOLID, RIGID, HOSTILE, WIND_SOURCE | **Size:** large
- `ALWAYS -> MOVE_TOWARD -> NEAREST_PLAYER, power=high`
- `ON_CONTACT -> APPLY_FORCE -> CONTACT_BODY, power=medium`
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 0.75 | Sprite Prompt 1.00 | Surface 8
> **Faithfulness (0.75):** The design captures the core concept of a helicopter well, using appropriate tags like WIND_SOURCE for the rotors and SOLID/RIGID for the body. The visual description is detailed and consistent. However, the AI assumed the helicopter should be a 'Scrap Helicopter' and 'HOSTILE', which might not align with a player's intent for a generic helicopter (usually a vehicle rather than an enemy), making it a slightly biased interpretation of a single-word prompt.
> **Gameplay Quality (0.75):** The design is strong, particularly the use of the WIND_SOURCE tag which creates excellent emergent gameplay opportunities (dispersing gas, pushing light objects, or launching floating objects) as the helicopter chases the player. The behaviors complement the tags well by providing movement and additional physical impact. However, since it is described as a "rusty metal" scrap helicopter of "large" size, omitting the CONDUCTING and HEAVY tags are minor missed opportunities for further interactions with electricity, magnets, or crushing physics.

### parashoot
**Tags:** SOLID, FLEXIBLE, LIGHT, FLOATING | **Size:** small
- `ON_TAG_ADDED(FLOATING) -> MOVE_AWAY -> NEAREST_PLAYER, power=low`
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 4
> **Faithfulness (0.75):** The design captures the core concept well. The name "Parachute Pack" and the tags "LIGHT", "FLEXIBLE", and especially "FLOATING" directly address the player's request to not fall. The visual description is accurate. The behavior is slightly odd (moving away from the player when floating), which is a minor issue but doesn't negate the functionality provided by the "FLOATING" tag.

### trampoline excited
**Tags:** SOLID, FLEXIBLE, BOUNCY | **Size:** medium
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 2

### rocket enthusiast
**Tags:** SOLID, RIGID, HEAVY, FLAMMABLE | **Size:** large
- `ON_PROXIMITY -> SPAWN_PROJECTILE -> NEAREST_LIVING, power=high`
**Scores:** Validity 1.00 | Faithfulness 0.50 | Gameplay Quality 0.25 | Sprite Prompt 1.00 | Surface 8
> **Faithfulness (0.50):** The design captures the visual and physical properties of a rocket well (name, tags, visual description). However, it completely fails to implement the specific behavior requested by the player ("goes ZOOM straight up"). Instead, it includes a behavior for spawning projectiles at nearby living things, which is unrelated and contradicts the player's intent for movement.
> **Gameplay Quality (0.25):** The design completely fails to address the user's request for a rocket that "goes ZOOM straight up." Instead of movement or force behaviors, it provides a proximity-based projectile behavior, essentially making it a stationary turret rather than a rocket. Furthermore, the HEAVY tag contradicts the requested "ZOOM" functionality, and it misses obvious tag opportunities like EXPLOSIVE or HEAT_SOURCE which would create the emergent gameplay expected for a rocket in this system.

### idk something cool
**Tags:** SOLID, ELECTRIC, GLOWING, LIGHT, BOUNCY | **Size:** small
- `ALWAYS -> MOVE_TOWARD -> NEAREST_OBJECT, power=high`
- `ON_CONTACT -> EXPLODE -> SELF, power=medium`
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 12

### big thing
**Tags:** SOLID, RIGID, HEAVY | **Size:** huge
- *(no behaviors)*
**Scores:** Validity 1.00 | Faithfulness 1.00 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 5

### drone
**Tags:** SOLID, LIVING, LIGHT, WIND_SOURCE, HOSTILE | **Size:** small
- `ALWAYS -> MOVE_TOWARD -> NEAREST_LIVING, power=medium`
- `ON_PROXIMITY -> APPLY_FORCE -> CONTACT_BODY, power=low`
**Scores:** Validity 1.00 | Faithfulness 0.75 | Gameplay Quality 1.00 | Sprite Prompt 1.00 | Surface 14
> **Faithfulness (0.75):** The design captures the core concept of a drone (a small helicopter-like device) very well through the visual description and the use of the WIND_SOURCE tag. However, it includes the LIVING tag, which is incorrect for a mechanical drone. It also assumes the drone is HOSTILE and a "Hunter," which was not part of the user's prompt, though it fits a common game archetype.
