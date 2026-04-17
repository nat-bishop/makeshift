"""Cross-language parity: every int value in godot/scripts/data/Enums.cs must
match the corresponding Python source of truth. Label strings intentionally
differ (Godot member names, LLM prompt labels, blueprint display labels each
serve different audiences) — only the wire contract is verified mechanically.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from app.models.state import State
from app.prompts.behavior import ACTION_QUESTION, STAGE1_QUESTIONS, STATE_ACTION_QUESTION
from app.prompts.creation import ALL_CREATION_QUESTIONS

if TYPE_CHECKING:
    from app.creator.question_graph import Question

MOVEMENT_QUESTION = next(q for q in STAGE1_QUESTIONS if q.key == "movement")

ENUMS_CS = Path(__file__).resolve().parents[2] / "godot" / "scripts" / "data" / "Enums.cs"


def _parse_godot_enums() -> dict[str, dict[str, int]]:
    """Return {EnumName: {MemberName: IntValue}} parsed from Enums.cs."""
    text = ENUMS_CS.read_text(encoding="utf-8")
    result: dict[str, dict[str, int]] = {}
    for enum_match in re.finditer(r"public enum (\w+)\s*\{([^}]+)\}", text, re.DOTALL):
        name = enum_match.group(1)
        members: dict[str, int] = {}
        for m in re.finditer(r"(\w+)\s*=\s*(\d+)", enum_match.group(2)):
            members[m.group(1)] = int(m.group(2))
        result[name] = members
    return result


GODOT = _parse_godot_enums()


def _values(q: Question) -> set[int]:
    return {v for _, v in q.choice_map}


def test_parity_movement() -> None:
    assert set(GODOT["Movement"].values()) == _values(MOVEMENT_QUESTION)


def test_parity_action_kind() -> None:
    assert set(GODOT["ActionKind"].values()) == _values(ACTION_QUESTION)


def test_parity_state_action() -> None:
    assert set(GODOT["StateAction"].values()) == _values(STATE_ACTION_QUESTION)


def test_parity_state_id() -> None:
    # Godot StateId includes None=0 as a sentinel; the Python State IntEnum
    # defines only the real states (1-4). Compare nonzero parts for strictness,
    # and verify the Godot set is exactly Python values plus {0}.
    godot = set(GODOT["StateId"].values())
    py = {s.value for s in State}
    assert godot == py | {0}, f"Godot={godot}, Python|{{0}}={py | {0}}"


def test_parity_choice_fields() -> None:
    """Affordance, Durability, SpeedTier, Surface — each backed by a
    prompts/creation.py Question.choice_map."""
    by_key = {q.key: q for q in ALL_CREATION_QUESTIONS}
    pairs = [
        ("Affordance", "affordance"),
        ("Durability", "durability"),
        ("SpeedTier", "speed"),
        ("Surface", "surface"),
    ]
    for godot_name, py_key in pairs:
        godot_vals = set(GODOT[godot_name].values())
        py_vals = _values(by_key[py_key])
        assert godot_vals == py_vals, f"{godot_name}: Godot={godot_vals}, Python={py_vals}"
