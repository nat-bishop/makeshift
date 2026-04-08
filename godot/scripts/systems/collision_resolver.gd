extends Node

## V3 Collision Resolver: pairwise cache lookup replaces rule engine.
## Effects are applied inline — no separate EffectExecutor.
## 6 fields per pair: damage_a, damage_b, state_change_a/b, force_b (signed), continuous.

const CL = preload("res://scripts/data/collision_layers.gd")

const MAX_CASCADE_DEPTH: int = 3
const CASCADE_RADIUS: float = 96.0
const DEFAULT_STATE_DURATION: float = 10.0
const FORCE_SCALE: float = 5.0  # Multiply 0-100 LLM force to impulse magnitude

# State encoding: 0=none, 1-4=add, 5-8=remove
const STATE_NAMES: Array[String] = [
	"", "burning", "frozen", "wet", "electrified"
]
const NUM_STATES: int = 4


func resolve_collision(body_a: Node, body_b: Node, cascade_depth: int = 0, _resolved: Dictionary = {}, from_field: bool = false) -> void:
	if cascade_depth == 0:
		_resolved = {}

	if cascade_depth > MAX_CASCADE_DEPTH:
		return

	var name_a: String = _get_name(body_a)
	var name_b: String = _get_name(body_b)
	if name_a.is_empty() or name_b.is_empty():
		return

	# Per-chain dedup
	var dedup_key: String = InteractionCache.pair_key(name_a, name_b)
	if dedup_key in _resolved:
		return
	_resolved[dedup_key] = true

	# Pairwise cache lookup
	var entry: Dictionary = InteractionCache.lookup_pairwise(name_a, name_b)
	if entry.is_empty():
		return  # Uncached = nothing happens

	# Field ticks should only fire continuous interactions
	if from_field and not entry.get("continuous", false):
		return

	# Map A/B to sorted order (cache key convention: lexicographic)
	var sorted_a: String = name_a.to_lower() if name_a.to_lower() <= name_b.to_lower() else name_b.to_lower()
	var target_a: Node = body_a if _get_name(body_a).to_lower() == sorted_a else body_b
	var target_b: Node = body_b if target_a == body_a else body_a

	# Record states before for cascade detection
	var states_a_before: Array = _get_states(target_a).duplicate()
	var states_b_before: Array = _get_states(target_b).duplicate()

	# --- Apply effects inline ---

	var dmg_a: int = entry.get("damage_a", 0)
	var dmg_b: int = entry.get("damage_b", 0)
	var destroyed_a: bool = dmg_a >= 100
	var destroyed_b: bool = dmg_b >= 100

	# Damage (apply non-lethal damage first, defer destruction to end)
	if not destroyed_a and dmg_a > 0:
		WorldMutations.apply_damage(target_a, float(dmg_a))
	if not destroyed_b and dmg_b > 0:
		WorldMutations.apply_damage(target_b, float(dmg_b))

	# State changes — skip destroyed objects
	if not destroyed_a:
		_apply_state_change(target_a, entry.get("state_change_a", 0))
	if not destroyed_b:
		_apply_state_change(target_b, entry.get("state_change_b", 0))

	# Force — skip destroyed objects
	var force_b: int = entry.get("force_b", 0)
	if force_b != 0 and not destroyed_b:
		var from_pos: Vector2 = target_a.global_position if target_a is Node2D else Vector2.ZERO
		var to_pos: Vector2 = target_b.global_position if target_b is Node2D else Vector2.ZERO
		var force_dir: Vector2 = (to_pos - from_pos).normalized()
		var magnitude: float = absf(float(force_b))
		if force_b < 0:  # pull = toward A
			force_dir = -force_dir
		WorldMutations.apply_impulse(target_b, force_dir, magnitude * FORCE_SCALE)
		if not destroyed_a and target_a is RigidBody2D and target_b is RigidBody2D:
			var ratio: float = target_b.mass / maxf(target_a.mass, 0.001)
			WorldMutations.apply_impulse(target_a, -force_dir, magnitude * FORCE_SCALE * ratio)

	# Destruction last — after all other effects
	if destroyed_a:
		_destroy(target_a)
	if destroyed_b:
		_destroy(target_b)

	# Cascade on state changes
	if cascade_depth < MAX_CASCADE_DEPTH:
		var states_a_after: Array = _get_states(target_a)
		var states_b_after: Array = _get_states(target_b)
		if not _arrays_equal(states_a_before, states_a_after):
			_cascade_to_neighbors(target_a, cascade_depth + 1, _resolved)
		if not _arrays_equal(states_b_before, states_b_after):
			_cascade_to_neighbors(target_b, cascade_depth + 1, _resolved)


func _apply_state_change(target: Node, change: int) -> void:
	if change == 0:
		return
	if change >= 1 and change <= NUM_STATES:
		WorldMutations.apply_add_state(target, STATE_NAMES[change], DEFAULT_STATE_DURATION)
	elif change >= NUM_STATES + 1 and change <= NUM_STATES * 2:
		WorldMutations.apply_remove_state(target, STATE_NAMES[change - NUM_STATES])


func _destroy(target: Node) -> void:
	if target.has_method("take_damage"):
		target.take_damage(99999.0)
	elif is_instance_valid(target):
		target.queue_free()


func _get_name(body: Node) -> String:
	if body.has_method("get_object_name"):
		return body.get_object_name()
	return ""


func _get_states(body: Node) -> Array:
	if body.has_method("get_states"):
		return body.get_states()
	return []


func _cascade_to_neighbors(body: Node, cascade_depth: int, _resolved: Dictionary) -> void:
	if body is not Node2D:
		return
	if body.has_method("get_cascade_neighbors"):
		for neighbor in body.get_cascade_neighbors():
			if is_instance_valid(neighbor):
				resolve_collision(body, neighbor, cascade_depth, _resolved)
		return
	_cascade_via_space_query(body, cascade_depth, _resolved)


func _cascade_via_space_query(body: Node2D, cascade_depth: int, _resolved: Dictionary) -> void:
	if not body.is_inside_tree():
		return
	var space_state := body.get_world_2d().direct_space_state
	var query := PhysicsShapeQueryParameters2D.new()
	var circle := CircleShape2D.new()
	circle.radius = CASCADE_RADIUS
	query.shape = circle
	query.transform = Transform2D(0, body.global_position)
	query.collision_mask = CL.OBJECTS
	query.exclude = [body.get_rid()] if body is PhysicsBody2D else []
	for result in space_state.intersect_shape(query, 32):
		var neighbor: Node = result.get("collider", null)
		if neighbor != null and neighbor != body and is_instance_valid(neighbor):
			resolve_collision(body, neighbor, cascade_depth, _resolved)


func _arrays_equal(a: Array, b: Array) -> bool:
	if a.size() != b.size():
		return false
	var sa: Array = a.duplicate()
	var sb: Array = b.duplicate()
	sa.sort()
	sb.sort()
	return sa == sb
