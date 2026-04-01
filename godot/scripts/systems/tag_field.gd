extends Node

## Per-object field component. Attaches an Area2D to detect nearby objects and
## applies field-rule interactions: continuous forces per physics frame, and
## periodic rule evaluation via timers routed through CollisionResolver.
## Range and mode come from FieldConfig (tag-level), not from individual rules.

const CL = preload("res://scripts/data/collision_layers.gd")

var _owner_body: RigidBody2D
var _field_area: Area2D
var _periodic_timer: Timer
var _has_periodic: bool = false
var _has_continuous: bool = false
var _prev_field_tags: Array = []

# Pre-cached at _rebuild() time so _physics_process avoids per-frame rule lookups
var _cached_continuous: Array = []  # [{rule, range_px, req_b, blocked_by}]
var _max_periodic_range: float = 0.0  # for per-tag distance filtering in periodic tick

# Generalized slow tracking: bodies we've slowed so we can restore on exit
var _slow_damped: Dictionary = {}  # body instance_id -> original linear_damp
var _slow_players: Dictionary = {}  # player instance_id -> true (entry/exit tracking)
var _slow_factor: float = 0.25  # default; overridden by APPLY_SLOW effect
var _slow_range_px: float = 0.0  # cached in _rebuild()
var _has_slow: bool = false


func _exit_tree() -> void:
	_restore_all_slow()


func init_field(owner: RigidBody2D, tags: Array) -> void:
	_owner_body = owner
	_rebuild(tags)


func on_tags_changed(tags: Array) -> void:
	_rebuild(tags)


func _rebuild(tags: Array) -> void:
	# Collect current field tags
	var current_field_tags: Array = []
	for tag in tags:
		if FieldConfig.is_field_tag(tag):
			current_field_tags.append(tag)
	current_field_tags.sort()

	# Short-circuit if field tags haven't changed
	if current_field_tags == _prev_field_tags:
		return
	_prev_field_tags = current_field_tags

	_cached_continuous.clear()
	_has_periodic = false
	_has_continuous = false
	_has_slow = false
	_slow_range_px = 0.0
	_max_periodic_range = 0.0

	var max_range: float = 0.0
	var periodic_tags: Array = []

	for tag in current_field_tags:
		var r: float = FieldConfig.get_range_px(tag)
		if r > max_range:
			max_range = r
		if FieldConfig.is_continuous(tag):
			_has_continuous = true
		else:
			periodic_tags.append(tag)
			_has_periodic = true
			if r > _max_periodic_range:
				_max_periodic_range = r

	# Pre-resolve continuous FIELD rules from the owner's tags
	if _has_continuous:
		var owner_tags: Array = tags
		var all_rules: Array = RuleEngine.find_matching_rules(owner_tags, owner_tags)
		for rule in all_rules:
			if rule.get("trigger_mode", "CONTACT") != "FIELD":
				continue
			var req_a: Array = rule.get("tags_required_a", [])
			# Determine which emitting tag this rule belongs to
			var emitting_tag: String = ""
			for t in req_a:
				if FieldConfig.is_field_tag(t) and FieldConfig.is_continuous(t) and t in owner_tags:
					emitting_tag = t
					break
			if emitting_tag == "":
				continue
			# Check if this rule has APPLY_SLOW effects
			var has_slow_effect: bool = false
			for effect in rule.get("effects", []):
				if effect is Dictionary and effect.get("effect_type", "") == "APPLY_SLOW":
					has_slow_effect = true
					_has_slow = true
					_slow_range_px = FieldConfig.get_range_px(emitting_tag)
					var sf: float = effect.get("slow_factor", 0.25)
					if sf > 0.0:
						_slow_factor = sf
					break
			_cached_continuous.append({
				"rule": rule,
				"range_px": FieldConfig.get_range_px(emitting_tag),
				"req_b": rule.get("tags_required_b", []),
				"blocked_by": rule.get("tags_blocked_by", []),
				"bidirectional": rule.get("bidirectional", false),
				"req_a": req_a,
				"has_slow": has_slow_effect,
			})

	# If slow was removed, restore all damped bodies
	if not _has_slow:
		_restore_all_slow()

	# Create or update Area2D
	if max_range > 0.0:
		_ensure_area(max_range)
	elif _field_area != null:
		_field_area.queue_free()
		_field_area = null

	# Manage periodic timer (reuse if already exists)
	if _has_periodic:
		if _periodic_timer == null:
			_periodic_timer = Timer.new()
			_periodic_timer.wait_time = FieldConfig.PERIODIC_INTERVAL
			_periodic_timer.one_shot = false
			_periodic_timer.timeout.connect(_on_periodic_tick)
			add_child(_periodic_timer)
			call_deferred("_on_periodic_tick")
			_periodic_timer.start()
	elif _periodic_timer != null:
		_periodic_timer.stop()
		_periodic_timer.queue_free()
		_periodic_timer = null

	# Toggle physics process for continuous fields
	set_physics_process(_has_continuous)
	if _owner_body != null:
		_owner_body.can_sleep = not _has_continuous


func _ensure_area(radius: float) -> void:
	if _field_area == null:
		_field_area = Area2D.new()
		_field_area.name = "FieldArea"
		_field_area.collision_layer = 0
		_field_area.collision_mask = CL.OBJECTS | CL.PLAYER
		_field_area.monitoring = true
		_field_area.monitorable = false
		var shape_node := CollisionShape2D.new()
		var circle := CircleShape2D.new()
		circle.radius = radius
		shape_node.shape = circle
		_field_area.add_child(shape_node)
		_owner_body.add_child(_field_area)
	else:
		var shape_node: CollisionShape2D = _field_area.get_child(0)
		if shape_node != null and shape_node.shape is CircleShape2D:
			shape_node.shape.radius = radius


func _physics_process(_delta: float) -> void:
	if _field_area == null:
		return
	if not is_instance_valid(_owner_body):
		return

	var owner_pos: Vector2 = _owner_body.global_position
	var overlapping: Array = _field_area.get_overlapping_bodies()

	# --- Generalized slow field ---
	if _has_slow:
		_apply_slow_field(owner_pos, overlapping)

	if _cached_continuous.is_empty():
		return

	for entry in _cached_continuous:
		if entry["has_slow"]:
			continue  # APPLY_SLOW handled above, skip force logic
		var range_px: float = entry["range_px"]
		var req_b: Array = entry["req_b"]
		var blocked_by: Array = entry["blocked_by"]
		var rule: Dictionary = entry["rule"]

		for body in overlapping:
			if body == _owner_body or not is_instance_valid(body):
				continue
			if body is not RigidBody2D and body is not CharacterBody2D:
				continue

			# Per-tag range check (center-to-center approximation)
			var dist: float = owner_pos.distance_to(body.global_position)
			if dist > range_px * 1.5:  # generous margin for shape overlap
				continue

			var body_tags: Array = TagColors.get_body_tags(body)
			if body_tags.is_empty():
				continue

			# Check B-side tag match
			if not _has_all(body_tags, req_b):
				continue
			if not blocked_by.is_empty() and _has_any(body_tags, blocked_by):
				continue

			_apply_force_effects(rule, body)


func _apply_force_effects(rule: Dictionary, body: Node2D) -> void:
	for effect in rule.get("effects", []):
		if effect is not Dictionary:
			continue
		if effect.get("effect_type", "") != "APPLY_FORCE":
			continue
		var magnitude: float = effect.get("force_magnitude", 0.0)
		var direction: Vector2 = (body.global_position - _owner_body.global_position).normalized()
		WorldMutations.apply_continuous_force(body, direction, magnitude)


func _on_periodic_tick() -> void:
	if _field_area == null or not is_instance_valid(_owner_body):
		return
	var owner_pos: Vector2 = _owner_body.global_position
	for body in _field_area.get_overlapping_bodies():
		if body == _owner_body or not is_instance_valid(body):
			continue
		if not TagColors.is_taggable(body):
			continue
		# Per-tag range check for periodic fields
		var dist: float = owner_pos.distance_to(body.global_position)
		if dist > _max_periodic_range * 1.5:
			continue
		CollisionResolver.resolve_collision(_owner_body, body, 0, "FIELD")



func _has_all(tags: Array, required: Array) -> bool:
	for tag in required:
		if tag not in tags:
			return false
	return true


func _has_any(tags: Array, check: Array) -> bool:
	for tag in check:
		if tag in tags:
			return true
	return false


# --- Generalized slow field ---

func _apply_slow_field(owner_pos: Vector2, overlapping: Array) -> void:
	var currently_in_range: Dictionary = {}  # instance_id -> body

	for body in overlapping:
		if body == _owner_body or not is_instance_valid(body):
			continue
		var dist: float = owner_pos.distance_to(body.global_position)
		if dist > _slow_range_px * 1.5:
			continue
		var bid: int = body.get_instance_id()
		currently_in_range[bid] = body

		if body is RigidBody2D and bid not in _slow_damped:
			_slow_damped[bid] = body.linear_damp
			body.linear_damp = 1.0 / _slow_factor
			body.tree_exiting.connect(_on_slow_body_exiting.bind(bid), CONNECT_ONE_SHOT)

		# Track player entry — only call apply_speed_modifier once on entry, not per frame
		if body is CharacterBody2D and body.has_method("apply_speed_modifier"):
			if bid not in _slow_players:
				_slow_players[bid] = true
				body.apply_speed_modifier(_slow_factor)
				body.tree_exiting.connect(_on_slow_player_exiting.bind(bid), CONNECT_ONE_SHOT)

	# Restore rigid bodies that left the slow field
	var to_restore: Array = []
	for bid in _slow_damped:
		if bid not in currently_in_range:
			to_restore.append(bid)
	for bid in to_restore:
		_restore_slow_body(bid)

	# Restore players that left the slow field
	var players_to_restore: Array = []
	for pid in _slow_players:
		if pid not in currently_in_range:
			players_to_restore.append(pid)
	for pid in players_to_restore:
		_restore_slow_player(pid)


func _restore_slow_body(bid: int) -> void:
	if bid not in _slow_damped:
		return
	var original_damp: float = _slow_damped[bid]
	_slow_damped.erase(bid)
	var body: Object = instance_from_id(bid)
	if body != null and is_instance_valid(body) and body is RigidBody2D:
		body.linear_damp = original_damp


func _on_slow_body_exiting(bid: int) -> void:
	_restore_slow_body(bid)


func _restore_slow_player(pid: int) -> void:
	if pid not in _slow_players:
		return
	_slow_players.erase(pid)
	var body: Object = instance_from_id(pid)
	if body != null and is_instance_valid(body) and body.has_method("clear_speed_modifier"):
		body.clear_speed_modifier()


func _on_slow_player_exiting(pid: int) -> void:
	_restore_slow_player(pid)


func _restore_all_slow() -> void:
	for bid in _slow_damped.keys():
		_restore_slow_body(bid)
	_slow_damped.clear()
	for pid in _slow_players.keys():
		_restore_slow_player(pid)
	_slow_players.clear()
