"""Tests for V3 state system."""

from app.models.state import State, STATE_REMOVES, STATE_NAMES, get_contradicted


def test_state_enum_has_7_values():
    assert len(State) == 7


def test_state_names_map():
    assert STATE_NAMES[1] == "on_fire"
    assert STATE_NAMES[7] == "molten"


def test_directed_contradictions_on_fire():
    """Adding on_fire removes frozen AND wet."""
    existing = {State.FROZEN, State.WET, State.POISONED}
    removed = get_contradicted(State.ON_FIRE, existing)
    assert removed == {State.FROZEN, State.WET}


def test_directed_contradictions_wet():
    """Adding wet removes ONLY on_fire, not frozen."""
    existing = {State.ON_FIRE, State.FROZEN}
    removed = get_contradicted(State.WET, existing)
    assert removed == {State.ON_FIRE}


def test_directed_contradictions_frozen():
    """Adding frozen removes on_fire and molten."""
    existing = {State.ON_FIRE, State.MOLTEN, State.POISONED}
    removed = get_contradicted(State.FROZEN, existing)
    assert removed == {State.ON_FIRE, State.MOLTEN}


def test_directed_contradictions_molten():
    """Adding molten removes frozen."""
    existing = {State.FROZEN, State.POISONED}
    removed = get_contradicted(State.MOLTEN, existing)
    assert removed == {State.FROZEN}


def test_no_contradictions_for_poisoned():
    """Poisoned has no contradictions."""
    existing = {State.ON_FIRE, State.FROZEN, State.WET}
    removed = get_contradicted(State.POISONED, existing)
    assert removed == set()


def test_no_contradictions_when_none_present():
    existing = {State.POISONED, State.CORRODED}
    removed = get_contradicted(State.ON_FIRE, existing)
    assert removed == set()


def test_state_removes_keys():
    """Only 4 states have contradiction entries."""
    assert set(STATE_REMOVES.keys()) == {
        State.ON_FIRE, State.FROZEN, State.WET, State.MOLTEN,
    }
