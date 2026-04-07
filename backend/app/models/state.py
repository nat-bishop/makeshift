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


def get_contradicted(adding: State, existing: set[State]) -> set[State]:
    """Return which existing states must be removed when adding `adding`."""
    return existing & set(STATE_REMOVES.get(adding, []))
