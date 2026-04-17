"""LLM prompts for the per-pair behavior evaluation pipeline.

Consumed by `app.engine.behavior`:
  - Stage 1 fan-out: `STAGE1_QUESTIONS` (movement + priority, all subject x target pairs)
  - Stage 2 per-pair: `ACTION_QUESTION` + conditional `AMOUNT_QUESTION`,
    `STATE_ACTION_QUESTION`, `STATE_ID_QUESTION`, `DELIVERY_QUESTION`,
    and `PROJECTILE_NAME_QUESTION` (only when delivery=projectile)
  - Pre-screening: `screen_pairs_prompt()`

Each `Question` embeds its own system instructions, user-message template,
and answer shape (choice/int/float/text). Context strings like `{subject}` and
`{target}` are interpolated at call time by `run_questions()`.
"""

from __future__ import annotations

from app.creator.question_graph import Question

# ---------------------------------------------------------------------------
# Stage 1: movement + priority (parallel across all pairs)
# ---------------------------------------------------------------------------

_MOVEMENT_QUESTION = Question(
    "movement",
    "{subject} → {target} {state_context}",
    "choice",
    default="ignore",
    instructions=(
        "Would this creature move toward or away from the target? "
        "Think about predator/prey, desires, fears, and duties. "
        "approach=move toward (hunt, eat, help, play, investigate), "
        "flee=run away (fear, repulsion, danger), "
        "ignore=no movement reaction (unrelated, or object cannot move). "
        "If the subject cannot move on its own, always use ignore."
    ),
    choices=("approach", "flee", "ignore"),
    choice_map=(("approach", 0), ("flee", 1), ("ignore", 2)),
)

_PRIORITY_QUESTION = Question(
    "priority",
    "{subject} → {target} {state_context}",
    "choice",
    default="ignore",
    instructions=(
        "How strongly does this creature react to the target? "
        "ignore=no interest, mild=slight interest, moderate=clear drive, "
        "driven=high priority. For reactive objects that always act on contact, "
        "use moderate or driven."
    ),
    choices=("ignore", "mild", "moderate", "driven"),
    choice_map=(("ignore", 0), ("mild", 1), ("moderate", 2), ("driven", 3)),
)

# Active subjects: both movement + priority (parallel).
STAGE1_QUESTIONS: list[Question] = [_MOVEMENT_QUESTION, _PRIORITY_QUESTION]

# Inactive subjects: priority only — they can't move, so movement is forced to ignore (2).
# Saves one LLM call per pair and eliminates the "approach with MoveSpeed=0" contradiction.
STAGE1_INACTIVE_QUESTIONS: list[Question] = [_PRIORITY_QUESTION]


# ---------------------------------------------------------------------------
# Stage 2: composite action pipeline (per pair)
# ---------------------------------------------------------------------------

ACTION_QUESTION = Question(
    "action",
    "{subject} → {target}",
    "choice",
    default="nothing",
    instructions=(
        "Subject's current intent: {movement_label}, priority {priority}. "
        "What does the subject do to the target when nearby? "
        "A fleeing subject usually does 'nothing' or a defensive action; "
        "a reactive subject (ignore + priority>0) typically triggers a single "
        "decisive effect on contact (contact damage, explosion, drain). "
        "nothing=no effect, attack=damage/harm, heal=repair/help, "
        "consume=eat/absorb/destroy, push=knock away/blow with force."
    ),
    choices=("nothing", "attack", "heal", "consume", "push"),
    choice_map=(
        ("nothing", 0),
        ("attack", 1),
        ("heal", 2),
        ("consume", 3),
        ("push", 4),
    ),
)

AMOUNT_QUESTION = Question(
    "amount",
    "{subject} will {action_verb} {target}.",
    "int",
    0,
    100,
    20,
    instructions=(
        "How intense is this action? 0-100. "
        "5=negligible, 15=light, 30=moderate, 50=serious, 75=devastating, 100=maximum. "
        "For healing: 15=patch up, 30=treat, 50=major surgery, 75=full restore."
    ),
)

STATE_ACTION_QUESTION = Question(
    "state_action",
    "{subject} will {action_verb} {target}.",
    "choice",
    default="nothing",
    instructions=(
        "Does this interaction also cause an elemental state change?"
        "{subject_states} "
        "A subject that embodies an element usually imparts it (ignite); "
        "an opposing element usually removes it (cleanse). "
        "nothing=no state effect, ignite=apply a state, cleanse=remove a state."
    ),
    choices=("nothing", "ignite", "cleanse"),
    choice_map=(("nothing", 0), ("ignite", 1), ("cleanse", 2)),
)

STATE_ID_QUESTION = Question(
    "state_id",
    "{subject} will {state_verb} a state on {target}.",
    "choice",
    default="burn",
    instructions=(
        "Which elemental state?{subject_states} "
        "Pick the state that best matches the subject's own nature when possible. "
        "burn=fire/heat, freeze=ice/cold, wet=water/liquid, zap=electricity."
    ),
    choices=("burn", "freeze", "wet", "zap"),
    choice_map=(("burn", 1), ("freeze", 2), ("wet", 3), ("zap", 4)),
)

DELIVERY_QUESTION = Question(
    "delivery",
    "{subject} will {action_verb} {target}.",
    "choice",
    default="contact",
    instructions=(
        "Does the subject deliver this action by direct contact, or by launching "
        "a projectile (arrow, bullet, missile, fireball, thrown rock, etc.)? "
        "Pick projectile only when the subject naturally has a way to fire something "
        "at range — a helicopter, archer, wizard, gun-toting robot, or sentry turret. "
        "Bites, slashes, slams, rams, and most melee creatures use contact. "
        "contact=close-range hit, projectile=fire something at the target."
    ),
    choices=("contact", "projectile"),
    choice_map=(("contact", 0), ("projectile", 1)),
)

PROJECTILE_NAME_QUESTION = Question(
    "projectile_name",
    "What does {subject} fire at {target}? "
    "Reply with a 1-3 word name for the projectile only. "
    "Examples: helicopter -> missile, archer -> arrow, fire wizard -> fireball, "
    "ice mage -> ice dart, sentry -> bullet, robot -> laser bolt.",
    "text",
    max_tokens=20,
    default="bolt",
)


# ---------------------------------------------------------------------------
# Pre-screening (plain ask_text, no Question wrapper)
# ---------------------------------------------------------------------------


def screen_pairs_prompt(new_obj_summary: str, scene_numbered: str, new_obj_name: str) -> str:
    """Build the bidirectional screening prompt for `screen_pairs`.

    Args:
        new_obj_summary: Compact summary of the newly added object
            (produced by `engine.behavior._obj_summary`).
        scene_numbered: Newline-separated "1. <summary>\\n2. <summary>\\n..."
            listing of existing scene objects.
        new_obj_name: Bare name of the new object, used in the question body.
    """
    return (
        f"New object: {new_obj_summary}.\n"
        f"Scene objects:\n{scene_numbered}\n"
        f"Which would have interesting interactions with {new_obj_name} (in either direction)? "
        f"Think about: material reactions (burning, melting, conducting, dissolving), "
        f"creature instincts (hunting, fleeing, feeding), "
        f"folklore/fiction relationships, "
        f"and tools or forces acting on objects. "
        f"Reply with just the numbers separated by commas, or 'none'."
    )
