extends Node

const CL = preload("res://scripts/data/collision_layers.gd")

const MAX_CASCADE_DEPTH: int = 3
const CASCADE_RADIUS: float = 96.0


func resolve_and_notify(body_a: Node, body_b: Node, cascade_depth: int = 0, trigger_mode_filter: String = "", resolved: Dictionary = {}) -> void:
	## V3: Resolve pairwise interactions via cached lookup.
	if cascade_depth == 0:
		resolved = {}

	if cascade_depth > MAX_CASCADE_DEPTH:
		return

	var name_a: String = _get_body_name(body_a)
	var name_b: String = _get_body_name(body_b)
	if name_a.is_empty() or name_b.is_empty():
		return

	# Per-chain dedup
	var id_a: String = _get_body_id(body_a)
	var id_b: String = _get_body_id(body_b)
	var dedup_key: String
	if id_a < id_b:
		dedup_key = "%s:%s:%s" % [id_a, id_b, trigger_mode_filter]
	else:
		dedup_key = "%s:%s:%s" % [id_b, id_a, trigger_mode_filter]

	if dedup_key in resolved:
		return
	resolved[dedup_key] = true

	# V3: Lookup pairwise result from Backend cache
	var pair_result: Dictionary = Backend.get_pairwise(name_a, name_b)
	if pair_result.is_empty():
		return  # uncached = nothing happens

	# Map to lexicographic A/B order
	var sorted_names: Array = [name_a.to_lower(), name_b.to_lower()]
	sorted_names.sort()
	var a_body: Node = body_a if name_a.to_lower() == sorted_names[0] else body_b
	var b_body: Node = body_b if name_b.to_lower() == sorted_names[1] else body_a

	Log.debug("CollisionResolver: V3 pairwise hit for %s vs %s" % [name_a, name_b])

	var states_changed: bool = EffectExecutor.execute_pairwise(pair_result, a_body, b_body)

	# Cascade if states changed
	if states_changed and cascade_depth < MAX_CASCADE_DEPTH:
		_cascade_to_neighbors(a_body, cascade_depth + 1, resolved)
		_cascade_to_neighbors(b_body, cascade_depth + 1, resolved)


func _cascade_to_neighbors(body: Node, cascade_depth: int, resolved: Dictionary) -> void:
	if body is not Node2D:
		return

	if body.has_method("get_cascade_neighbors"):
		var neighbors = body.get_cascade_neighbors()
		for neighbor in neighbors:
			if not is_instance_valid(neighbor):
				continue
			resolve_and_notify(body, neighbor, cascade_depth, "", resolved)
		return

	_cascade_via_space_query(body, cascade_depth, resolved)


func _cascade_via_space_query(body: Node2D, cascade_depth: int, resolved: Dictionary) -> void:
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

	var results: Array = space_state.intersect_shape(query, 32)
	for result in results:
		var neighbor: Node = result.get("collider", null)
		if neighbor == null or neighbor == body:
			continue
		if not is_instance_valid(neighbor):
			continue
		resolve_and_notify(body, neighbor, cascade_depth, "", resolved)


func _get_body_name(body: Node) -> String:
	if body.has_method("get_blueprint"):
		return body.get_blueprint().get("name", "")
	return ""


func _get_body_id(body: Node) -> String:
	if body.has_method("get_object_id"):
		return body.get_object_id()
	return str(body.get_instance_id())
