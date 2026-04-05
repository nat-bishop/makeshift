class_name SubstancePhysics

# Read substance_profile from blueprint → resolve physics properties.
# State-derived defaults: solid (gravity=1.0, damping=0.5), liquid (1.0, 2.0),
# gas (-0.2, 4.0), energy (0.0, 0.0).

const STATE_DEFAULTS: Dictionary = {
	"solid": {"gravity": 1.0, "damping": 0.5},
	"liquid": {"gravity": 1.0, "damping": 2.0},
	"gas": {"gravity": -0.2, "damping": 4.0},
	"energy": {"gravity": 0.0, "damping": 0.0},
}


static func resolve_physics(blueprint: Dictionary) -> Dictionary:
	var profile: Dictionary = blueprint.get("substance_profile", {})

	if profile.is_empty():
		return {
			"mass": 1.0,
			"gravity": 1.0,
			"friction": 0.5,
			"bounce": 0.0,
			"damping": 0.5,
		}

	# Read from pre-computed profile (backend already applied element + tag modifiers)
	return {
		"mass": profile.get("mass", 1.0),
		"gravity": profile.get("gravity", 1.0),
		"friction": profile.get("friction", 0.5),
		"bounce": profile.get("bounce", 0.0),
		"damping": profile.get("damping", 0.5),
	}


static func apply_tag_modifiers(physics: Dictionary, current_tags: Array) -> Dictionary:
	## Apply runtime tag modifiers to physics. Mirrors backend resolve_profile() tag block.
	var result: Dictionary = physics.duplicate()

	if "HEAVY" in current_tags:
		result["mass"] = result["mass"] + 5.0
		result["friction"] = maxf(result["friction"], 0.7)
	if "LIGHT" in current_tags:
		result["mass"] = result["mass"] * 0.15
		result["damping"] = 1.5
	if "BREAKABLE" in current_tags:
		pass  # Durability modifier, not physics
	if "BOUNCY" in current_tags:
		result["bounce"] = 0.9
		result["friction"] = minf(result["friction"], 0.2)
	if "STICKY" in current_tags:
		result["friction"] = maxf(result["friction"], 2.0)
		result["bounce"] = 0.0
	if "FLYING" in current_tags:
		result["gravity"] = 0.0
		result["damping"] = 2.0

	return result
