class_name StateContradictions
extends RefCounted

## Directed state contradictions: adding the key removes all values.
## e.g. adding "burning" removes both "frozen" and "wet",
## but adding "wet" only removes "burning".
## "electrified" has no contradictions — can stack with anything.

const REMOVES: Dictionary = {
	"burning": ["frozen", "wet"],
	"frozen": ["burning"],
	"wet": ["burning"],
}


static func get_removals(adding: String) -> Array:
	## Returns the list of states that must be removed when adding `adding`.
	return REMOVES.get(adding, [])
