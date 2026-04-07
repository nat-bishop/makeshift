from enum import StrEnum


class State(StrEnum):
    ON_FIRE = "on_fire"
    FROZEN = "frozen"
    WET = "wet"
    ELECTRIFIED = "electrified"
    POISONED = "poisoned"
    CORRODED = "corroded"
    MOLTEN = "molten"


# Directed: adding key auto-removes all values
STATE_CONTRADICTIONS: dict[State, list[State]] = {
    State.ON_FIRE: [State.FROZEN, State.WET],
    State.FROZEN: [State.ON_FIRE, State.MOLTEN],
    State.WET: [State.ON_FIRE],
    State.MOLTEN: [State.FROZEN],
}

# For LLM prompt encoding: state_id 1-7 maps to states in enum order
STATE_BY_ID: dict[int, State] = {i + 1: s for i, s in enumerate(State)}


def decode_state_change(code: int) -> tuple[str, State] | None:
    """Decode 0-14 to (action, state) or None.
    0=none, 1-7=add state, 8-14=remove state."""
    if code == 0:
        return None
    if 1 <= code <= 7:
        return ("add", STATE_BY_ID[code])
    if 8 <= code <= 14:
        return ("remove", STATE_BY_ID[code - 7])
    return None
