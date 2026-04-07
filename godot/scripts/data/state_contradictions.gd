class_name StateContradictions

const CONTRADICTIONS: Dictionary = {
	"on_fire": ["frozen", "wet"],
	"frozen": ["on_fire", "molten"],
	"wet": ["on_fire"],
	"molten": ["frozen"],
}

static func get_contradictions(state: String) -> Array:
	return CONTRADICTIONS.get(state, [])
