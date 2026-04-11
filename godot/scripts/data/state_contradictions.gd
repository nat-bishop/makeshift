class_name StateContradictions
extends RefCounted

## Directed state contradictions: adding the key removes all values.
## e.g. adding "burning" removes both "frozen" and "wet",
## but adding "wet" only removes "burning".
## "electrified" has no contradictions — can stack with anything.

## Canonical state ID → name mapping. Single source of truth for GDScript.
const STATE_NAMES: Array[String] = ["", "burning", "frozen", "wet", "electrified"]

const REMOVES: Dictionary = {
	"burning": ["frozen", "wet"],
	"frozen": ["burning"],
	"wet": ["burning"],
}


static func get_removals(adding: String) -> Array:
	## Returns the list of states that must be removed when adding `adding`.
	return REMOVES.get(adding, [])
