extends Node

const CL = preload("res://scripts/data/collision_layers.gd")

var _cooldowns: Dictionary = {}  # "objA_id:objB_id" -> timestamp
const COOLDOWN_TIME: float = 0.5
const MAX_CASCADE_DEPTH: int = 3
const CASCADE_RADIUS: float = 96.0
const COOLDOWN_CLEANUP_INTERVAL: float = 5.0

var _effect_executor: Node
var _cleanup_timer: float = 0.0
var _sticky_joints: Dictionary = {}  # pair_key -> PinJoint2D


func _ready() -> void:
	_effect_executor = preload("res://scripts/systems/effect_executor.gd").new()
	add_child(_effect_executor)


func _process(delta: float) -> void:
	_cleanup_timer += delta
	if _cleanup_timer >= COOLDOWN_CLEANUP_INTERVAL:
		_cleanup_timer = 0.0
		_cleanup_cooldowns()


func resolve_collision(body_a: Node, body_b: Node, cascade_depth: int = 0, trigger_mode_filter: String = "") -> void:
	if cascade_depth > MAX_CASCADE_DEPTH:
		Log.debug("CollisionResolver: Cascade depth exceeded for %s vs %s" % [body_a.name, body_b.name])
		return

	# Build cooldown key from sorted IDs
	var id_a: String = _get_body_id(body_a)
	var id_b: String = _get_body_id(body_b)
	var pair_key: String
	if id_a < id_b:
		pair_key = "%s:%s" % [id_a, id_b]
	else:
		pair_key = "%s:%s" % [id_b, id_a]

	# Check cooldown
	var now: float = Time.get_ticks_msec() / 1000.0
	if pair_key in _cooldowns:
		if now - _cooldowns[pair_key] < COOLDOWN_TIME:
			return

	# Get tags from bodies
	var tags_a: Array = _get_body_tags(body_a)
	var tags_b: Array = _get_body_tags(body_b)

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
		if trigger_mode_filter == "" and not tags_a.is_empty() and not tags_b.is_empty():
			Log.debug("CollisionResolver: No rules matched for %s %s vs %s %s" % [body_a.name, tags_a, body_b.name, tags_b])
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

	# Set cooldown
	_cooldowns[pair_key] = now

	# Create sticky joint if applicable (only on direct contact, not cascade)
	if cascade_depth == 0:
		_check_sticky_joint(body_a, body_b, tags_a, tags_b, pair_key)

	# Check for cascade
	if any_cascade_eligible and cascade_depth < MAX_CASCADE_DEPTH:
		var tags_a_after: Array = _get_body_tags(body_a)
		var tags_b_after: Array = _get_body_tags(body_b)
		var a_changed: bool = not _arrays_equal(tags_a_before, tags_a_after)
		var b_changed: bool = not _arrays_equal(tags_b_before, tags_b_after)

		if a_changed:
			Log.debug("CollisionResolver: Tags changed on %s, cascading at depth %d" % [body_a.name, cascade_depth + 1])
			_cascade_to_neighbors(body_a, cascade_depth + 1)
		if b_changed:
			Log.debug("CollisionResolver: Tags changed on %s, cascading at depth %d" % [body_b.name, cascade_depth + 1])
			_cascade_to_neighbors(body_b, cascade_depth + 1)


func _check_sticky_joint(body_a: Node, body_b: Node, tags_a: Array, tags_b: Array, pair_key: String) -> void:
	if pair_key in _sticky_joints:
		return
	if "STICKY" not in tags_a and "STICKY" not in tags_b:
		return
	if body_a is not RigidBody2D or body_b is not RigidBody2D:
		return
	var joint := PinJoint2D.new()
	joint.node_a = body_a.get_path()
	joint.node_b = body_b.get_path()
	joint.softness = 0.1
	body_a.add_child(joint)
	_sticky_joints[pair_key] = {"joint": joint, "body_a": body_a, "body_b": body_b}
	body_a.tree_exiting.connect(_on_sticky_body_freed.bind(pair_key))
	body_b.tree_exiting.connect(_on_sticky_body_freed.bind(pair_key))
	Log.debug("CollisionResolver: Created sticky joint between %s and %s" % [body_a.name, body_b.name])


func _on_sticky_body_freed(pair_key: String) -> void:
	if pair_key not in _sticky_joints:
		return
	var entry: Dictionary = _sticky_joints[pair_key]
	var joint: PinJoint2D = entry["joint"]
	if is_instance_valid(joint):
		joint.queue_free()
	# Disconnect stale signal on surviving body
	var body_a: Node = entry["body_a"]
	var body_b: Node = entry["body_b"]
	var cb: Callable = _on_sticky_body_freed.bind(pair_key)
	if is_instance_valid(body_a) and body_a.tree_exiting.is_connected(cb):
		body_a.tree_exiting.disconnect(cb)
	if is_instance_valid(body_b) and body_b.tree_exiting.is_connected(cb):
		body_b.tree_exiting.disconnect(cb)
	_sticky_joints.erase(pair_key)


func _cascade_to_neighbors(body: Node, cascade_depth: int) -> void:
	if body is not Node2D:
		return

	if body.has_method("get_cascade_neighbors"):
		var neighbors = body.get_cascade_neighbors()
		for neighbor in neighbors:
			if not is_instance_valid(neighbor):
				continue
			resolve_collision(body, neighbor, cascade_depth)
		return

	_cascade_via_space_query(body, cascade_depth)


func _cascade_via_space_query(body: Node2D, cascade_depth: int) -> void:
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
		resolve_collision(body, neighbor, cascade_depth)


func _get_body_id(body: Node) -> String:
	if body.has_method("get_object_id"):
		return body.get_object_id()
	return str(body.get_instance_id())


func _get_body_tags(body: Node) -> Array:
	if body.has_method("get_effective_tags"):
		return body.get_effective_tags()
	if body.has_method("get_tags"):
		return body.get_tags()
	return []


func _arrays_equal(a: Array, b: Array) -> bool:
	if a.size() != b.size():
		return false
	var sorted_a: Array = a.duplicate()
	var sorted_b: Array = b.duplicate()
	sorted_a.sort()
	sorted_b.sort()
	return sorted_a == sorted_b


func _cleanup_cooldowns() -> void:
	var now: float = Time.get_ticks_msec() / 1000.0
	var to_remove: Array = []
	for key in _cooldowns:
		if now - _cooldowns[key] > COOLDOWN_TIME:
			to_remove.append(key)
	for key in to_remove:
		_cooldowns.erase(key)
	if not to_remove.is_empty():
		Log.debug("CollisionResolver: Cleaned %d expired cooldowns" % to_remove.size())


func clear_cooldowns() -> void:
	Log.debug("CollisionResolver: All cooldowns cleared")
	_cooldowns.clear()
