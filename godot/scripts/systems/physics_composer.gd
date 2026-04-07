class_name PhysicsComposer
extends RefCounted

## V3: size tables only. Physics values come from LLM-generated blueprint,
## not from tag-based composition.

const SIZE_TO_PHYSICS: Dictionary = {
	"tiny": {"sprite": 24, "collision": 16},
	"small": {"sprite": 44, "collision": 32},
	"medium": {"sprite": 72, "collision": 56},
	"large": {"sprite": 120, "collision": 96},
	"huge": {"sprite": 192, "collision": 160},
}

const SIZE_MASS_MULTIPLIER: Dictionary = {
	"tiny": 0.25,
	"small": 0.5,
	"medium": 1.0,
	"large": 4.0,
	"huge": 10.0,
}


static func get_size_mass_multiplier(size_category: String) -> float:
	return SIZE_MASS_MULTIPLIER.get(size_category, 1.0)


static func get_size_data(size_category: String) -> Dictionary:
	return SIZE_TO_PHYSICS.get(size_category, SIZE_TO_PHYSICS["medium"])


static func size_from_height(height_cm: int) -> String:
	if height_cm < 10: return "tiny"
	if height_cm < 50: return "small"
	if height_cm < 150: return "medium"
	if height_cm < 400: return "large"
	return "huge"
