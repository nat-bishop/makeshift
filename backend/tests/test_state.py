"""Tests for V3 state system."""

from app.models.state import (
    STATE_NAMES,
    STATE_REMOVES,
    State,
    decode_state_change,
    get_contradicted,
)


def test_state_enum_has_4_values():
    assert len(State) == 4


def test_state_names_map():
    assert STATE_NAMES[1] == "burning"
    assert STATE_NAMES[4] == "electrified"


def test_directed_contradictions_burning():
    """Adding burning removes frozen AND wet."""
    existing = {State.FROZEN, State.WET, State.ELECTRIFIED}
    removed = get_contradicted(State.BURNING, existing)
    assert removed == {State.FROZEN, State.WET}


def test_directed_contradictions_wet():
    """Adding wet removes ONLY burning, not frozen."""
    existing = {State.BURNING, State.FROZEN}
    removed = get_contradicted(State.WET, existing)
    assert removed == {State.BURNING}


def test_directed_contradictions_frozen():
    """Adding frozen removes burning."""
    existing = {State.BURNING, State.ELECTRIFIED}
    removed = get_contradicted(State.FROZEN, existing)
    assert removed == {State.BURNING}


def test_no_contradictions_for_electrified():
    """Electrified has no contradictions — can stack with anything."""
    existing = {State.BURNING, State.FROZEN, State.WET}
    removed = get_contradicted(State.ELECTRIFIED, existing)
    assert removed == set()


def test_no_contradictions_when_none_present():
    existing = {State.ELECTRIFIED}
    removed = get_contradicted(State.BURNING, existing)
    assert removed == set()


def test_state_removes_keys():
    """Only 3 states have contradiction entries."""
    assert set(STATE_REMOVES.keys()) == {
        State.BURNING,
        State.FROZEN,
        State.WET,
    }


# --- decode_state_change ---


def test_decode_zero():
    assert decode_state_change(0) is None


def test_decode_add_all():
    for s in State:
        result = decode_state_change(s.value)
        assert result == ("add", s)


def test_decode_remove_all():
    for s in State:
        result = decode_state_change(s.value + len(State))
        assert result == ("remove", s)


def test_decode_invalid():
    assert decode_state_change(-1) is None
    assert decode_state_change(9) is None
    assert decode_state_change(100) is None


def test_decode_contradiction_integration():
    """Decode BURNING (code 1) then check contradictions."""
    result = decode_state_change(1)
    assert result is not None
    action, state = result
    assert action == "add"
    contradicted = get_contradicted(state, {State.FROZEN, State.WET, State.ELECTRIFIED})
    assert contradicted == {State.FROZEN, State.WET}
