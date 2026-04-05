class_name PhysicsComposer

const DEFAULT_MASS: float = 1.0
const DEFAULT_GRAVITY: float = 1.0
const DEFAULT_FRICTION: float = 0.5
const DEFAULT_BOUNCE: float = 0.0
const DEFAULT_DAMPING: float = 0.5

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


static func compose_physics_v2(blueprint: Dictionary) -> Dictionary:
	## Read pre-computed physics from substance_profile in blueprint.
	return SubstancePhysics.resolve_physics(blueprint)


static func get_size_data(size_category: String) -> Dictionary:
	return SIZE_TO_PHYSICS.get(size_category, SIZE_TO_PHYSICS["medium"])
