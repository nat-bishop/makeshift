class_name SubstancePhysics

# Read substance_profile from blueprint → resolve physics properties.
# State-derived defaults: solid (gravity=1.0, damping=0.5), liquid (1.0, 2.0),
# gas (-0.2, 4.0), energy (0.0, 0.0).
# Tag modifiers: HEAVY, LIGHT, BOUNCY, STICKY, FLYING (same values as backend).

const STATE_DEFAULTS: Dictionary = {
	"solid": {"gravity": 1.0, "damping": 0.5},
	"liquid": {"gravity": 1.0, "damping": 2.0},
	"gas": {"gravity": -0.2, "damping": 4.0},
	"energy": {"gravity": 0.0, "damping": 0.0},
}


static func resolve_physics(blueprint: Dictionary) -> Dictionary:
	var profile: Dictionary = blueprint.get("substance_profile", {})

	if profile.is_empty():
		# Fallback: no V2 data, use defaults
		return {
			"mass": 1.0,
			"gravity": 1.0,
			"friction": 0.5,
			"bounce": 0.0,
			"damping": 0.5,
		}

	# Read from pre-computed profile (backend already applied element + tag modifiers)
	var mass: float = profile.get("mass", 1.0)
	var friction: float = profile.get("friction", 0.5)
	var bounce: float = profile.get("bounce", 0.0)
	var state: String = profile.get("state", "solid")

	# Gravity and damping: use profile values if set, else state defaults
	var gravity: float = profile.get("gravity", -1.0)
	var damping: float = profile.get("damping", -1.0)

	if gravity < -0.5:  # sentinel -1.0 = use state default
		gravity = STATE_DEFAULTS.get(state, STATE_DEFAULTS["solid"])["gravity"]
	if damping < -0.5:
		damping = STATE_DEFAULTS.get(state, STATE_DEFAULTS["solid"])["damping"]

	return {
		"mass": mass,
		"gravity": gravity,
		"friction": friction,
		"bounce": bounce,
		"damping": damping,
	}
