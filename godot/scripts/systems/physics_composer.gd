class_name PhysicsComposer

const DEFAULT_MASS: float = 1.0
const DEFAULT_GRAVITY: float = 1.0
const DEFAULT_FRICTION: float = 0.5
const DEFAULT_BOUNCE: float = 0.0

const SIZE_TO_PHYSICS: Dictionary = {
	"tiny": {"sprite": 32, "collision": 16},
	"small": {"sprite": 48, "collision": 32},
	"medium": {"sprite": 64, "collision": 48},
	"large": {"sprite": 96, "collision": 80},
	"huge": {"sprite": 128, "collision": 112},
}

const ELONGATED_FORMS: Array[String] = [
	"sword", "plank", "rope", "ladder", "wand", "torch", "fan",
]

const ROUND_FORMS: Array[String] = [
	"sphere", "ball", "boulder", "wheel",
]


static func compose_physics(tags: Array) -> Dictionary:
	var mass_entries: Array = []
	var gravity_entries: Array = []
	var friction_entries: Array = []
	var bounce_entries: Array = []

	for tag in tags:
		var tag_str: String = str(tag)
		if tag_str not in TagPhysicsMap.TAG_PHYSICS:
			continue
		var props: Dictionary = TagPhysicsMap.TAG_PHYSICS[tag_str]
		var priority: int = props["priority"]

		if props["mass"] >= 0.0:
			mass_entries.append({"priority": priority, "value": props["mass"]})
		if props["gravity"] > -2.0 and props["gravity"] != -1.0:
			gravity_entries.append({"priority": priority, "value": props["gravity"]})
		if props["friction"] >= 0.0:
			friction_entries.append({"priority": priority, "value": props["friction"]})
		if props["bounce"] >= 0.0:
			bounce_entries.append({"priority": priority, "value": props["bounce"]})

	return {
		"mass": _resolve_property(mass_entries, DEFAULT_MASS),
		"gravity": _resolve_property(gravity_entries, DEFAULT_GRAVITY),
		"friction": _resolve_property(friction_entries, DEFAULT_FRICTION),
		"bounce": _resolve_property(bounce_entries, DEFAULT_BOUNCE),
	}


static func _resolve_property(entries: Array, default_value: float) -> float:
	if entries.is_empty():
		return default_value

	# Find highest priority
	var max_priority: int = -1
	for entry in entries:
		if entry["priority"] > max_priority:
			max_priority = entry["priority"]

	# Collect all values at highest priority
	var values: Array = []
	for entry in entries:
		if entry["priority"] == max_priority:
			values.append(entry["value"])

	# Same priority -> average
	var total: float = 0.0
	for v in values:
		total += v
	return total / values.size()


static func get_size_data(size_category: String) -> Dictionary:
	return SIZE_TO_PHYSICS.get(size_category, SIZE_TO_PHYSICS["medium"])


static func shape_from_base_form(base_form: String) -> String:
	if base_form in ELONGATED_FORMS:
		return "capsule"
	elif base_form in ROUND_FORMS:
		return "circle"
	else:
		return "rectangle"
