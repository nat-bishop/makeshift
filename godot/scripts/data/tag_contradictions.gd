class_name TagContradictions

## Runtime mirror of backend TAG_CONTRADICTIONS (backend/app/models/tags.py).
## Used by WorldMutations to auto-remove contradictory tags when adding new ones.

const PAIRS: Array[Array] = [
	["FROZEN", "MOLTEN"],
	["FROZEN", "HOT"],
	["COLD", "HOT"],
	["COLD", "MOLTEN"],
	["HEAVY", "LIGHT"],
	["LIQUID", "RIGID"],
	["GAS", "RIGID"],
	["GAS", "HEAVY"],
	["SOLID", "LIQUID"],
	["SOLID", "GAS"],
	["LIQUID", "GAS"],
	["STICKY", "SLIPPERY"],
	["CONDUCTING", "INSULATING"],
	["REFLECTIVE", "STICKY"],
	["HEAT_SOURCE", "FLAMMABLE"],
	["WET", "MOLTEN"],
	["WET", "HEAT_SOURCE"],
]

static var _lookup: Dictionary = {}  # tag -> Array[String] of contradicting tags


static func _build_lookup() -> void:
	for pair in PAIRS:
		var a: String = pair[0]
		var b: String = pair[1]
		if a not in _lookup:
			_lookup[a] = []
		_lookup[a].append(b)
		if b not in _lookup:
			_lookup[b] = []
		_lookup[b].append(a)


static func get_contradictions(tag: String) -> Array:
	if _lookup.is_empty():
		_build_lookup()
	return _lookup.get(tag, [])
