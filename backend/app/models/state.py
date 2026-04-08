"""V3 interaction states — closed vocabulary of 4 states applied at runtime.

Each state has a distinct gameplay mechanic:
  BURNING: DOT damage, spreads via cascade
  FROZEN: immobilize + brittle (2x incoming damage)
  WET: reduces friction, amplifies ELECTRIFIED via re-eval
  ELECTRIFIED: DOT damage, chains to WET objects via cascade
"""

from enum import IntEnum


class State(IntEnum):
    BURNING = 1
    FROZEN = 2
    WET = 3
    ELECTRIFIED = 4


# Directed: adding the key state removes all states in its value list.
# e.g. adding BURNING removes FROZEN and WET, but adding WET only removes BURNING.
STATE_REMOVES: dict[State, list[State]] = {
    State.BURNING: [State.FROZEN, State.WET],
    State.FROZEN: [State.BURNING],
    State.WET: [State.BURNING],
}

STATE_NAMES: dict[int, str] = {s.value: s.name.lower() for s in State}

# Human-readable labels for LLM prompts, generated from enum to prevent drift
_ADD_LABELS = {s: s.name.lower().replace("_", " ") for s in State}
_REMOVE_LABELS = {s: "remove " + s.name.lower().replace("_", " ") for s in State}

STATE_CHANGE_PROMPT = " ".join(
    ["0=none"]
    + [f"{s.value}={_ADD_LABELS[s]}" for s in State]
    + [f"{s.value + len(State)}={_REMOVE_LABELS[s]}" for s in State]
)

STATE_LIST_PROMPT = " ".join(f"{s.value}={_ADD_LABELS[s]}" for s in State)


def get_contradicted(adding: State, existing: set[State]) -> set[State]:
    """Return which existing states must be removed when adding `adding`."""
    return existing & set(STATE_REMOVES.get(adding, []))


def decode_state_change(code: int) -> tuple[str, State] | None:
    """Decode a 0-8 state change code.

    Returns ("add", State) for 1-4, ("remove", State) for 5-8, None for 0 or invalid.
    """
    n = len(State)
    if code <= 0 or code > 2 * n:
        return None
    if code <= n:
        return ("add", State(code))
    return ("remove", State(code - n))
