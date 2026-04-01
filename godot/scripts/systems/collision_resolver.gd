extends Node

const CL = preload("res://scripts/data/collision_layers.gd")

const MAX_CASCADE_DEPTH: int = 3
const CASCADE_RADIUS: float = 96.0

var _effect_executor: Node


func _ready() -> void:
	_effect_executor = preload("res://scripts/systems/effect_executor.gd").new()
	add_child(_effect_executor)


func resolve_and_notify(body_a: Node, body_b: Node, cascade_depth: int = 0, trigger_mode_filter: String = "") -> void:
	## Resolve tag-based rules AND fire ON_CONTACT behavior trigger on body_b.
	## Consolidates the common pattern used by player, game_object, and kick.
	resolve_collision(body_a, body_b, cascade_depth, trigger_mode_filter)
	if body_b.has_method("fire_behavior_trigger"):
		body_b.fire_behavior_trigger("ON_CONTACT", body_a)


func resolve_collision(body_a: Node, body_b: Node, cascade_depth: int = 0, trigger_mode_filter: String = "", _resolved: Dictionary = {}) -> void:
	# Top-level calls get a fresh dedup dict; cascades inherit the parent's.
	# (GDScript default Dictionary is shared across calls — same as Python's mutable default.)
	if cascade_depth == 0:
		_resolved = {}

	if cascade_depth > MAX_CASCADE_DEPTH:
		Log.debug("CollisionResolver: Cascade depth exceeded for %s vs %s" % [body_a.name, body_b.name])
		return

	# Per-chain dedup: same pair can't fire twice in one resolution chain.
	var id_a: String = _get_body_id(body_a)
	var id_b: String = _get_body_id(body_b)
	var pair_key: String
	if id_a < id_b:
		pair_key = "%s:%s:%s" % [id_a, id_b, trigger_mode_filter]
	else:
		pair_key = "%s:%s:%s" % [id_b, id_a, trigger_mode_filter]

	if pair_key in _resolved:
		return
	_resolved[pair_key] = true

	# Get tags from bodies
	var tags_a: Array = TagColors.get_body_tags(body_a)
	var tags_b: Array = TagColors.get_body_tags(body_b)

	if tags_a.is_empty() and tags_b.is_empty():
		return

	# Find matching rules
	var rules: Array = RuleEngine.find_matching_rules(tags_a, tags_b)

	# Filter by trigger mode if requested (e.g., "FIELD" from periodic tick)
	if trigger_mode_filter != "":
		var filtered: Array = []
		for rule in rules:
			if rule.get("trigger_mode", "CONTACT") == trigger_mode_filter:
				filtered.append(rule)
		rules = filtered

	if rules.is_empty():
		return

	Log.debug("CollisionResolver: %d rules matched for %s vs %s" % [rules.size(), body_a.name, body_b.name])

	# Record tags before effects for cascade detection
	var tags_a_before: Array = tags_a.duplicate()
	var tags_b_before: Array = tags_b.duplicate()

	# Execute effects for each rule
	var any_cascade_eligible: bool = false
	for rule in rules:
		_effect_executor.execute(rule, body_a, body_b, cascade_depth)
		if rule.get("cascade_eligible", false):
			any_cascade_eligible = true

	# Check for cascade
	if any_cascade_eligible and cascade_depth < MAX_CASCADE_DEPTH:
		var tags_a_after: Array = TagColors.get_body_tags(body_a)
		var tags_b_after: Array = TagColors.get_body_tags(body_b)
		var a_changed: bool = not _arrays_equal(tags_a_before, tags_a_after)
		var b_changed: bool = not _arrays_equal(tags_b_before, tags_b_after)

		if a_changed:
			Log.debug("CollisionResolver: Tags changed on %s, cascading at depth %d" % [body_a.name, cascade_depth + 1])
			_cascade_to_neighbors(body_a, cascade_depth + 1, _resolved)
		if b_changed:
			Log.debug("CollisionResolver: Tags changed on %s, cascading at depth %d" % [body_b.name, cascade_depth + 1])
			_cascade_to_neighbors(body_b, cascade_depth + 1, _resolved)


func _cascade_to_neighbors(body: Node, cascade_depth: int, _resolved: Dictionary) -> void:
	if body is not Node2D:
		return

	if body.has_method("get_cascade_neighbors"):
		var neighbors = body.get_cascade_neighbors()
		for neighbor in neighbors:
			if not is_instance_valid(neighbor):
				continue
			resolve_collision(body, neighbor, cascade_depth, "", _resolved)
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

	var results: Array = space_state.intersect_shape(query, 32)
	Log.debug("CollisionResolver: Space query found %d neighbors near %s at %s" % [results.size(), body.name, body.global_position])
	for result in results:
		var neighbor: Node = result.get("collider", null)
		if neighbor == null or neighbor == body:
			continue
		if not is_instance_valid(neighbor):
			continue
		resolve_collision(body, neighbor, cascade_depth, "", _resolved)


func _get_body_id(body: Node) -> String:
	if body.has_method("get_object_id"):
		return body.get_object_id()
	return str(body.get_instance_id())


func _arrays_equal(a: Array, b: Array) -> bool:
	if a.size() != b.size():
		return false
	var sorted_a: Array = a.duplicate()
	var sorted_b: Array = b.duplicate()
	sorted_a.sort()
	sorted_b.sort()
	return sorted_a == sorted_b
