class_name EffectExecutor

## V3: Executes pairwise interaction results on game objects.
## Called by CollisionResolver for each cached pairwise lookup.

const STATES: Array = ["on_fire", "frozen", "wet", "electrified", "poisoned", "corroded", "molten"]
const DYNAMIC_STATE_DURATION: float = 10.0


static func execute_pairwise(result: Dictionary, body_a: Node, body_b: Node) -> bool:
	var states_changed := false

	# Damage
	if result.get("damage_a", 0) > 0:
		var color_b: Color = _derive_element_color(body_b)
		WorldMutations.apply_damage(body_a, float(result["damage_a"]), color_b)
	if result.get("damage_b", 0) > 0:
		var color_a: Color = _derive_element_color(body_a)
		WorldMutations.apply_damage(body_b, float(result["damage_b"]), color_a)

	# State changes
	states_changed = _apply_state_change(result.get("state_change_a", 0), body_a) or states_changed
	states_changed = _apply_state_change(result.get("state_change_b", 0), body_b) or states_changed

	# Force
	if result.get("force_b", 0) > 0:
		if body_a is Node2D and body_b is Node2D:
			var dir: Vector2 = (body_b.global_position - body_a.global_position).normalized()
			if result.get("direction_b", 0) == 1:
				dir = -dir
			WorldMutations.apply_impulse(body_b, dir, result["force_b"] * 5.0)
			# Newton's 3rd law heuristic
			var mass_a: float = body_a.mass if "mass" in body_a else 1.0
			var mass_b: float = body_b.mass if "mass" in body_b else 1.0
			var mass_ratio: float = mass_b / maxf(mass_a, 0.01)
			WorldMutations.apply_impulse(body_a, -dir, result["force_b"] * 5.0 * mass_ratio)

	# Destruction
	if result.get("destroy_a", false) and body_a.has_method("take_damage"):
		body_a.take_damage(99999)
	if result.get("destroy_b", false) and body_b.has_method("take_damage"):
		body_b.take_damage(99999)

	return states_changed


static func _apply_state_change(code: int, body: Node) -> bool:
	if code == 0:
		return false
	if code >= 1 and code <= 7:
		var state_name: String = STATES[code - 1]
		if body.has_method("add_state"):
			body.add_state(state_name, DYNAMIC_STATE_DURATION)
		elif body.has_method("add_tag"):
			body.add_tag(state_name, DYNAMIC_STATE_DURATION)
		return true
	elif code >= 8 and code <= 14:
		var state_name: String = STATES[code - 8]
		if body.has_method("remove_state"):
			body.remove_state(state_name)
		elif body.has_method("remove_tag"):
			body.remove_tag(state_name)
		return true
	return false


static func _derive_element_color(body: Node) -> Color:
	if body.has_method("get_states"):
		var states: Array = body.get_states()
		for s in states:
			if s in StateColors.COLORS:
				return StateColors.get_color(s)
	elif body.has_method("get_tags"):
		var tag_list: Array = body.get_tags()
		for t in tag_list:
			if t in StateColors.COLORS:
				return StateColors.get_color(t)
	return Color.WHITE
