"""V3 interaction states — closed vocabulary of 7 states applied at runtime."""

from enum import IntEnum


class State(IntEnum):
    ON_FIRE = 1
    FROZEN = 2
    WET = 3
    ELECTRIFIED = 4
    POISONED = 5
    CORRODED = 6
    MOLTEN = 7


# Directed: adding the key state removes all states in its value list.
# e.g. adding ON_FIRE removes FROZEN and WET, but adding WET only removes ON_FIRE.
STATE_REMOVES: dict[State, list[State]] = {
    State.ON_FIRE: [State.FROZEN, State.WET],
    State.FROZEN: [State.ON_FIRE, State.MOLTEN],
    State.WET: [State.ON_FIRE],
    State.MOLTEN: [State.FROZEN],
}

STATE_NAMES: dict[int, str] = {s.value: s.name.lower() for s in State}

# Human-readable labels for LLM prompts, generated from enum to prevent drift
_ADD_LABELS = {s: s.name.lower().replace("_", " ") for s in State}
_REMOVE_LABELS = {s: "remove " + s.name.lower().replace("_", " ") for s in State}

STATE_CHANGE_PROMPT = " ".join(
    [f"0=none"]
    + [f"{s.value}={_ADD_LABELS[s]}" for s in State]
    + [f"{s.value + 7}={_REMOVE_LABELS[s]}" for s in State]
)

STATE_LIST_PROMPT = " ".join(f"{s.value}={_ADD_LABELS[s]}" for s in State)


def get_contradicted(adding: State, existing: set[State]) -> set[State]:
    """Return which existing states must be removed when adding `adding`."""
    return existing & set(STATE_REMOVES.get(adding, []))


def decode_state_change(code: int) -> tuple[str, State] | None:
    """Decode a 0-14 state change code.

    Returns ("add", State) for 1-7, ("remove", State) for 8-14, None for 0 or invalid.
    """
    if code <= 0 or code > 14:
        return None
    if code <= 7:
        return ("add", State(code))
    return ("remove", State(code - 7))
