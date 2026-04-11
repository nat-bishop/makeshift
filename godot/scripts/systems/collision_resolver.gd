extends Node

## Collision resolver: applies force-only pairwise rules from InteractionCache.
## State propagation is handled by StatePropagator (tick-based, separate system).
## Destruction is emergent via essential-state loss in StateManager.

const FORCE_SCALE: float = 5.0  # Multiply LLM force to impulse magnitude


func resolve_collision(body_a: Node, body_b: Node) -> void:
	var name_a: String = _get_name(body_a)
	var name_b: String = _get_name(body_b)
	if name_a.is_empty() or name_b.is_empty():
		return

	var rule: Dictionary = InteractionCache.lookup_collision(name_a, name_b)
	if rule.is_empty():
		# Cache miss: request lazy evaluation from backend
		InteractionCache.request_collision_eval(name_a, name_b)
		return

	# Sort A/B to match cache key convention (lexicographic)
	var sorted_a: String = name_a.to_lower() if name_a.to_lower() <= name_b.to_lower() else name_b.to_lower()
	var target_a: Node = body_a if _get_name(body_a).to_lower() == sorted_a else body_b
	var target_b: Node = body_b if target_a == body_a else body_a

	# Apply force
	var force_b: int = rule.get("force_on_b", 0)
	if force_b != 0:
		_apply_force(target_a, target_b, force_b)


func _apply_force(from_node: Node, to_node: Node, force_value: int) -> void:
	if to_node is not RigidBody2D or from_node is not Node2D:
		return
	var from_pos: Vector2 = (from_node as Node2D).global_position
	var to_pos: Vector2 = (to_node as Node2D).global_position
	var force_dir: Vector2 = (to_pos - from_pos).normalized()
	var magnitude: float = absf(float(force_value))
	if force_value < 0:  # pull = toward source
		force_dir = -force_dir
	WorldMutations.apply_impulse(to_node, force_dir, magnitude * FORCE_SCALE)
	# Equal/opposite force on source if both are RigidBody2D
	if from_node is RigidBody2D:
		var rb_to: RigidBody2D = to_node as RigidBody2D
		var rb_from: RigidBody2D = from_node as RigidBody2D
		var ratio: float = rb_to.mass / maxf(rb_from.mass, 0.001)
		WorldMutations.apply_impulse(from_node, -force_dir, magnitude * FORCE_SCALE * ratio)


func _get_name(body: Node) -> String:
	if body.has_method("get_object_name"):
		return body.get_object_name()
	return ""
