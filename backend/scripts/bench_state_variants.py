#!/usr/bin/env python3
"""A/B test Phase 1 state_on_a/b prompt variants.

The problem: bidirectional "destroy" on predator/prey pairs.
Wolf contacts sheep → state_on_a (what sheep does to wolf) should be "nothing"
but the model says "destroy" because it associates the pair with destruction.

Usage:
    uv run python backend/scripts/bench_state_variants.py
"""

from __future__ import annotations

import asyncio
import io
import sys

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.creator.llm import ask_choice, ask_int, reset_agents

# Test pairs: (a_desc, b_desc, expected_state_on_a, expected_state_on_b)
# a_desc/b_desc match _obj_summary format. A < B lexicographically.
# state_on_a = what B causes on A, state_on_b = what A causes on B
TEST_PAIRS = [
    # Predator/prey — the problem cases
    ("cat (4kg, 25cm, normal, normal-surface, creature)",
     "mouse (0.03kg, 5cm, normal, normal-surface, creature)",
     "nothing", "destroy"),  # cat destroys mouse, mouse does nothing to cat
    ("sheep (60kg, 100cm, normal, normal-surface, creature)",
     "wolf (40kg, 80cm, normal, normal-surface, creature)",
     "destroy", "nothing"),  # wolf(B) destroys sheep(A), sheep does nothing to wolf
    ("dragon (2000kg, 500cm, normal, normal-surface, creature)",
     "sheep (60kg, 100cm, normal, normal-surface, creature)",
     "nothing", ("destroy", "burn")),  # dragon destroys/burns sheep, sheep does nothing to dragon
    ("rabbit (2kg, 25cm, normal, normal-surface, creature)",
     "wolf (40kg, 80cm, normal, normal-surface, creature)",
     "destroy", "nothing"),  # wolf(B) destroys rabbit(A), rabbit does nothing to wolf
    # Non-creature material pairs (should already work)
    ("fire (0.1kg, 40cm, slippery, field 100cm)",
     "wood (3kg, 50cm, normal, normal-surface)",
     "nothing", "burn"),  # fire burns wood, wood does nothing to fire
    ("ice cube (0.3kg, 8cm, slippery)",
     "lava (10kg, 20cm, normal, field 120cm)",
     "destroy", ("cool", "nothing")),  # lava melts ice (destroys), ice cube is too small to destroy lava
    ("glass bottle (0.4kg, 25cm, normal, weak)",
     "sword (2kg, 90cm, normal)",
     "destroy", "nothing"),  # sword destroys glass, glass does nothing to sword
]

# Vocab for all variants
STATE_CHOICES_DESTROY = ("nothing", "burn", "freeze", "wet", "zap",
                         "cool", "warm", "dry", "ground", "destroy")
STATE_CHOICES_KILL = ("nothing", "burn", "freeze", "wet", "zap",
                      "cool", "warm", "dry", "ground", "kill")

VARIANTS: dict[str, tuple[tuple[str, ...], str, str]] = {
    "A_current": (
        STATE_CHOICES_DESTROY,
        (
            "Two objects make contact in a 2D game. What state does the second cause on "
            "the first? nothing=no effect. burn/freeze/wet/zap=apply that state. "
            "cool=remove burning, warm=remove frozen, dry=remove wet, "
            "ground=remove shocked. destroy=object is fully consumed. Return one word."
        ),
        (
            "Two objects make contact in a 2D game. What state does the first cause on "
            "the second? nothing=no effect. burn/freeze/wet/zap=apply that state. "
            "cool=remove burning, warm=remove frozen, dry=remove wet, "
            "ground=remove shocked. destroy=object is fully consumed. Return one word."
        ),
    ),
    "B_explicit_direction": (
        STATE_CHOICES_DESTROY,
        (
            "Two objects make contact in a 2D game. What state does the SECOND object "
            "cause on the FIRST? Consider ONLY the effect of the second on the first, "
            "not the reverse. Most pairs have no effect. "
            "nothing=no effect. burn/freeze/wet/zap=apply that state. "
            "cool=remove burning, warm=remove frozen, dry=remove wet, "
            "ground=remove shocked. destroy=object is fully consumed. Return one word."
        ),
        (
            "Two objects make contact in a 2D game. What state does the FIRST object "
            "cause on the SECOND? Consider ONLY the effect of the first on the second, "
            "not the reverse. Most pairs have no effect. "
            "nothing=no effect. burn/freeze/wet/zap=apply that state. "
            "cool=remove burning, warm=remove frozen, dry=remove wet, "
            "ground=remove shocked. destroy=object is fully consumed. Return one word."
        ),
    ),
    "C_kill_word": (
        STATE_CHOICES_KILL,
        (
            "Two objects make contact in a 2D game. What state does the second cause on "
            "the first? nothing=no effect. burn/freeze/wet/zap=apply that state. "
            "cool=remove burning, warm=remove frozen, dry=remove wet, "
            "ground=remove shocked. kill=object is fully consumed. Return one word."
        ),
        (
            "Two objects make contact in a 2D game. What state does the first cause on "
            "the second? nothing=no effect. burn/freeze/wet/zap=apply that state. "
            "cool=remove burning, warm=remove frozen, dry=remove wet, "
            "ground=remove shocked. kill=object is fully consumed. Return one word."
        ),
    ),
    "D_nothing_bias": (
        STATE_CHOICES_DESTROY,
        (
            "Two objects make contact in a 2D game. What state does the second cause on "
            "the first? Answer nothing unless there is a clear elemental or physical effect. "
            "nothing=no effect. burn/freeze/wet/zap=apply that state. "
            "cool=remove burning, warm=remove frozen, dry=remove wet, "
            "ground=remove shocked. destroy=fully consumed by the other object. "
            "Return one word."
        ),
        (
            "Two objects make contact in a 2D game. What state does the first cause on "
            "the second? Answer nothing unless there is a clear elemental or physical effect. "
            "nothing=no effect. burn/freeze/wet/zap=apply that state. "
            "cool=remove burning, warm=remove frozen, dry=remove wet, "
            "ground=remove shocked. destroy=fully consumed by the other object. "
            "Return one word."
        ),
    ),
    "E_old_style_ints_as_words": (
        STATE_CHOICES_DESTROY,
        (
            "Two objects make contact in a 2D game. Determine what state the second object "
            "causes on the first. "
            "burn/freeze/wet/zap APPLY a new state. "
            "cool/warm/dry/ground REMOVE an existing state "
            "(e.g. water removes burning → cool). "
            "destroy=object is fully consumed. nothing=no state change. "
            "Use burn/freeze/wet/zap to add a state. Use cool/warm/dry/ground only to cancel "
            "an existing state. Return one word."
        ),
        (
            "Two objects make contact in a 2D game. Determine what state the first object "
            "causes on the second. "
            "burn/freeze/wet/zap APPLY a new state. "
            "cool/warm/dry/ground REMOVE an existing state "
            "(e.g. water removes burning → cool). "
            "destroy=object is fully consumed. nothing=no state change. "
            "Use burn/freeze/wet/zap to add a state. Use cool/warm/dry/ground only to cancel "
            "an existing state. Return one word."
        ),
    ),
}

# --- Variant F: named-target prompts (different prompt template per question) ---
# Instead of "what does second cause on first", ask "what happens to {target}?"
# This requires a different bench since prompts differ structurally.

VARIANT_F_INSTR_A = (
    "Two objects make contact in a 2D game. What happens to the first object? "
    "nothing=no effect. burn/freeze/wet/zap=apply that state. "
    "cool=remove burning, warm=remove frozen, dry=remove wet, "
    "ground=remove shocked. destroy=object is fully consumed. Return one word."
)
VARIANT_F_INSTR_B = (
    "Two objects make contact in a 2D game. What happens to the second object? "
    "nothing=no effect. burn/freeze/wet/zap=apply that state. "
    "cool=remove burning, warm=remove frozen, dry=remove wet, "
    "ground=remove shocked. destroy=object is fully consumed. Return one word."
)

VARIANT_G_INSTR_A = (
    "Two objects make contact in a 2D game. What effect does {b} have on {a}? "
    "nothing=no effect. burn/freeze/wet/zap=apply that state. "
    "cool=remove burning, warm=remove frozen, dry=remove wet, "
    "ground=remove shocked. destroy=fully consumed. Return one word."
)
VARIANT_G_INSTR_B = (
    "Two objects make contact in a 2D game. What effect does {a} have on {b}? "
    "nothing=no effect. burn/freeze/wet/zap=apply that state. "
    "cool=remove burning, warm=remove frozen, dry=remove wet, "
    "ground=remove shocked. destroy=fully consumed. Return one word."
)

# Variant H: A/B labels with "Only consider A's ability to affect B. Ignore what B would do to A."
VARIANT_H_INSTR_ON_B = (
    "Object A touches object B in a 2D game. "
    "What effect does A cause ON B? "
    "Only consider A's ability to affect B. Ignore what B would do to A. "
    "nothing=no effect. burn/freeze/wet/zap=apply that state. "
    "cool=remove burning, warm=remove frozen, dry=remove wet, "
    "ground=remove shocked. destroy=fully consumed. Return one word."
)
VARIANT_H_INSTR_ON_A = (
    "Object A touches object B in a 2D game. "
    "What effect does B cause ON A? "
    "Only consider B's ability to affect A. Ignore what A would do to B. "
    "nothing=no effect. burn/freeze/wet/zap=apply that state. "
    "cool=remove burning, warm=remove frozen, dry=remove wet, "
    "ground=remove shocked. destroy=fully consumed. Return one word."
)

# Variant I: ACTING/RECEIVING role labeling
VARIANT_I_INSTR = (
    "Two objects touch in a 2D game. You are told which object is ACTING "
    "and which is RECEIVING. Only consider what the acting object can do "
    "to the receiving object. Ignore the reverse. "
    "nothing=no effect. burn/freeze/wet/zap=apply that state. "
    "cool=remove burning, warm=remove frozen, dry=remove wet, "
    "ground=remove shocked. destroy=fully consumed. Return one word."
)


def _matches(got: str, expected: str | tuple[str, ...]) -> bool:
    if isinstance(expected, tuple):
        return got in expected
    return got == expected


async def run_variant(name: str, choices: tuple[str, ...],
                      instr_a: str, instr_b: str, repeat: int) -> tuple[str, int, int, list[str]]:
    correct = 0
    total = 0
    failures = []
    for a_desc, b_desc, exp_a, exp_b in TEST_PAIRS:
        prompt = f"{a_desc} contacts {b_desc}."
        for _ in range(repeat):
            # state_on_a: what B causes on A
            got_a = await ask_choice(prompt, choices, default="nothing", instructions=instr_a)
            total += 1
            if _matches(got_a, exp_a):
                correct += 1
            else:
                failures.append(f"state_on_a: {a_desc.split('(')[0].strip()} vs "
                                f"{b_desc.split('(')[0].strip()}: "
                                f"expected={exp_a}, got={got_a}")
            # state_on_b: what A causes on B
            got_b = await ask_choice(prompt, choices, default="nothing", instructions=instr_b)
            total += 1
            if _matches(got_b, exp_b):
                correct += 1
            else:
                failures.append(f"state_on_b: {a_desc.split('(')[0].strip()} vs "
                                f"{b_desc.split('(')[0].strip()}: "
                                f"expected={exp_b}, got={got_b}")
    return name, correct, total, failures


async def main():
    repeat = 3
    reset_agents()
    result = await ask_int("Reply with 1.", 0, 1, -1)
    if result == -1:
        print("LLM unreachable")
        sys.exit(1)
    reset_agents()

    print(f"Testing Phase 1 state variants (repeat={repeat})...\n")

    for vname, (choices, instr_a, instr_b) in VARIANTS.items():
        reset_agents()
        name, correct, total, failures = await run_variant(
            vname, choices, instr_a, instr_b, repeat
        )
        pct = 100 * correct / total if total else 0
        print(f"{name}: {pct:.0f}% ({correct}/{total})")
        for f in failures:
            print(f"  x {f}")
        print()

    # Variant F: "what happens to the first/second object?"
    reset_agents()
    name, correct, total, failures = await run_variant(
        "F_what_happens_to", STATE_CHOICES_DESTROY,
        VARIANT_F_INSTR_A, VARIANT_F_INSTR_B, repeat
    )
    pct = 100 * correct / total if total else 0
    print(f"{name}: {pct:.0f}% ({correct}/{total})")
    for f in failures:
        print(f"  x {f}")
    print()

    # Variant G: "what effect does {B} have on {A}?" with named objects
    reset_agents()
    correct_g = 0
    total_g = 0
    failures_g = []
    for a_desc, b_desc, exp_a, exp_b in TEST_PAIRS:
        a_name = a_desc.split("(")[0].strip()
        b_name = b_desc.split("(")[0].strip()
        prompt = f"{a_desc} contacts {b_desc}."
        instr_a = VARIANT_G_INSTR_A.format(a=a_name, b=b_name)
        instr_b = VARIANT_G_INSTR_B.format(a=a_name, b=b_name)
        for _ in range(repeat):
            got_a = await ask_choice(prompt, STATE_CHOICES_DESTROY, default="nothing",
                                     instructions=instr_a)
            total_g += 1
            if got_a == exp_a:
                correct_g += 1
            else:
                failures_g.append(f"state_on_a: {a_name} vs {b_name}: "
                                  f"expected={exp_a}, got={got_a}")
            got_b = await ask_choice(prompt, STATE_CHOICES_DESTROY, default="nothing",
                                     instructions=instr_b)
            total_g += 1
            if got_b == exp_b:
                correct_g += 1
            else:
                failures_g.append(f"state_on_b: {a_name} vs {b_name}: "
                                  f"expected={exp_b}, got={got_b}")
    pct_g = 100 * correct_g / total_g if total_g else 0
    print(f"G_named_target: {pct_g:.0f}% ({correct_g}/{total_g})")
    for f in failures_g:
        print(f"  x {f}")
    print()

    # Variant H: "A: mouse, B: cat" labeling with explicit ignore-reverse
    reset_agents()
    correct_h = 0
    total_h = 0
    failures_h = []
    for a_desc, b_desc, exp_a, exp_b in TEST_PAIRS:
        a_name = a_desc.split("(")[0].strip()
        b_name = b_desc.split("(")[0].strip()
        # state_on_b: what A does to B
        prompt_b = f"A: {a_name}, B: {b_name}"
        for _ in range(repeat):
            got_b = await ask_choice(prompt_b, STATE_CHOICES_DESTROY, default="nothing",
                                     instructions=VARIANT_H_INSTR_ON_B)
            total_h += 1
            if _matches(got_b, exp_b):
                correct_h += 1
            else:
                failures_h.append(f"A→B: {a_name}→{b_name}: expected={exp_b}, got={got_b}")
            # state_on_a: what B does to A
            got_a = await ask_choice(prompt_b, STATE_CHOICES_DESTROY, default="nothing",
                                     instructions=VARIANT_H_INSTR_ON_A)
            total_h += 1
            if _matches(got_a, exp_a):
                correct_h += 1
            else:
                failures_h.append(f"B→A: {b_name}→{a_name}: expected={exp_a}, got={got_a}")
    pct_h = 100 * correct_h / total_h if total_h else 0
    print(f"H_ab_label: {pct_h:.0f}% ({correct_h}/{total_h})")
    for f in failures_h:
        print(f"  x {f}")
    print()

    # Variant I: ACTING/RECEIVING role labeling
    reset_agents()
    correct_i = 0
    total_i = 0
    failures_i = []
    for a_desc, b_desc, exp_a, exp_b in TEST_PAIRS:
        a_name = a_desc.split("(")[0].strip()
        b_name = b_desc.split("(")[0].strip()
        for _ in range(repeat):
            # state_on_b: A acts on B
            prompt_ab = f"{a_name} acts on {b_name}. What happens to {b_name}?"
            got_b = await ask_choice(prompt_ab, STATE_CHOICES_DESTROY, default="nothing",
                                     instructions=VARIANT_I_INSTR)
            total_i += 1
            if _matches(got_b, exp_b):
                correct_i += 1
            else:
                failures_i.append(f"A→B: {a_name}→{b_name}: expected={exp_b}, got={got_b}")
            # state_on_a: B acts on A
            prompt_ba = f"{b_name} acts on {a_name}. What happens to {a_name}?"
            got_a = await ask_choice(prompt_ba, STATE_CHOICES_DESTROY, default="nothing",
                                     instructions=VARIANT_I_INSTR)
            total_i += 1
            if _matches(got_a, exp_a):
                correct_i += 1
            else:
                failures_i.append(f"B→A: {b_name}→{a_name}: expected={exp_a}, got={got_a}")
    pct_i = 100 * correct_i / total_i if total_i else 0
    print(f"I_acting_receiving: {pct_i:.0f}% ({correct_i}/{total_i})")
    for f in failures_i:
        print(f"  x {f}")
    print()

    # Variant J: sentence completion — "When X touches Y, the effect on Y is ___"
    VARIANT_J_INSTR = (
        "Complete the sentence with one word describing the physical effect. "
        "If there is no effect, say nothing. "
        "nothing=no effect. burn/freeze/wet/zap=apply that state. "
        "cool=remove burning, warm=remove frozen, dry=remove wet, "
        "ground=remove shocked. destroy=fully consumed."
    )
    reset_agents()
    correct_j = 0
    total_j = 0
    failures_j = []
    for a_desc, b_desc, exp_a, exp_b in TEST_PAIRS:
        a_name = a_desc.split("(")[0].strip()
        b_name = b_desc.split("(")[0].strip()
        for _ in range(repeat):
            # state_on_b: effect of A on B
            prompt_b = f"When {a_name} touches {b_name}, the effect on {b_name} is ___"
            got_b = await ask_choice(prompt_b, STATE_CHOICES_DESTROY, default="nothing",
                                     instructions=VARIANT_J_INSTR)
            total_j += 1
            if _matches(got_b, exp_b):
                correct_j += 1
            else:
                failures_j.append(f"A→B: {a_name}→{b_name}: expected={exp_b}, got={got_b}")
            # state_on_a: effect of B on A
            prompt_a = f"When {b_name} touches {a_name}, the effect on {a_name} is ___"
            got_a = await ask_choice(prompt_a, STATE_CHOICES_DESTROY, default="nothing",
                                     instructions=VARIANT_J_INSTR)
            total_j += 1
            if _matches(got_a, exp_a):
                correct_j += 1
            else:
                failures_j.append(f"B→A: {b_name}→{a_name}: expected={exp_a}, got={got_a}")
    pct_j = 100 * correct_j / total_j if total_j else 0
    print(f"J_sentence_completion: {pct_j:.0f}% ({correct_j}/{total_j})")
    for f in failures_j:
        print(f"  x {f}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
