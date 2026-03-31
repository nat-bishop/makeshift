extends Node

## Executes autonomous behaviors on a GameObject.
## Attached as a child node when the blueprint includes behaviors.
## Uses BehaviorMaps for categorical→numeric value resolution.

const CL = preload("res://scripts/data/collision_layers.gd")

# Tick trigger types processed in _physics_process, ordered by priority (highest first).
# ON_HEALTH_LOW is event-fired from game_object.take_damage(), not polled here.
const _TICK_TRIGGERS: Array = ["ON_PROXIMITY", "ALWAYS"]

var _owner_body: RigidBody2D
var _behaviors: Array = []
var _behaviors_by_trigger: Dictionary = {}  # trigger_name -> [behavior_indices]
var _cooldowns: Dictionary = {}  # behavior_index -> last_fire_time
var _target_cache: Dictionary = {}  # behavior_index -> cached target Node
var _timers: Dictionary = {}  # behavior_index -> Timer
var _one_shot_fired: Dictionary = {}  # behavior_index -> bool (for ONCE intervals)
var _patrol_direction: float = 1.0  # 1.0 = right, -1.0 = left
var _patrol_distance: float = 0.0
const PATROL_MAX_DISTANCE: float = 200.0
const TARGET_UPDATE_INTERVAL: float = 0.3
const MAX_BEHAVIOR_ERRORS: int = 5
const MAX_EXPLOSION_RESULTS: int = 32
# Actions that work without a resolved target
const _TARGET_FREE_ACTIONS := ["PATROL", "EXPLODE", "SELF_DESTRUCT"]

var _target_update_timer: float = 0.0
var _behavior_errors: Dictionary = {}  # behavior_index -> consecutive error count
var _disabled_behaviors: Dictionary = {}  # behavior_index -> true

var _projectile_scene: PackedScene


func _owner_name() -> String:
	return _owner_body.blueprint.get("name", "?")


func init_behaviors(behaviors: Array, owner: RigidBody2D) -> void:
	_owner_body = owner
	_behaviors = behaviors
	_projectile_scene = preload("res://scenes/projectile/projectile.tscn")

	# Build trigger index and handle init-time triggers
	for i in range(_behaviors.size()):
		var b: Dictionary = _behaviors[i]
		var trigger: String = b.get("trigger", "")

		Log.debug("BehaviorExecutor: Behavior %d trigger=%s action=%s for '%s'" % [
			i, trigger, b.get("action", "?"), _owner_name()])

		if trigger not in _behaviors_by_trigger:
			_behaviors_by_trigger[trigger] = []
		_behaviors_by_trigger[trigger].append(i)

		if trigger == "ON_TIMER":
			_setup_timer(i, b)
		elif trigger == "ON_CREATE":
			_execute_behavior(i, null)

	# Disable _physics_process if no tick-driven behaviors exist
	var has_tick_behaviors := false
	for tick_trigger in _TICK_TRIGGERS:
		if tick_trigger in _behaviors_by_trigger:
			has_tick_behaviors = true
			break
	if not has_tick_behaviors:
		set_physics_process(false)
	else:
		# Sleeping bodies ignore velocity changes and forces —
		# disable sleep so tick-driven behaviors can move the object.
		_owner_body.can_sleep = false

	Log.info("BehaviorExecutor: Initialized %d behaviors for '%s'" % [
		_behaviors.size(), _owner_name()])


func fire_trigger(trigger_name: String, event_body: Node = null) -> void:
	for i in _behaviors_by_trigger.get(trigger_name, []):
		if i in _disabled_behaviors:
			continue
		_try_execute(i, event_body)


func on_tag_added(tag: String) -> void:
	for i in _behaviors_by_trigger.get("ON_TAG_ADDED", []):
		if i in _disabled_behaviors:
			continue
		if _behaviors[i].get("trigger_tag", "") == tag:
			Log.debug("BehaviorExecutor: ON_TAG_ADDED matched tag=%s behavior %d on '%s'" % [
				tag, i, _owner_name()])
			_try_execute(i, null)


func _physics_process(delta: float) -> void:
	# Update target cache periodically
	_target_update_timer += delta
	if _target_update_timer >= TARGET_UPDATE_INTERVAL:
		_target_update_timer = 0.0
		_update_target_cache()

	# Process tick triggers in priority order (highest priority first).
	# Movement is exclusive: only the highest-priority movement action runs.
	var movement_applied := false
	var best_movement_priority := 999

	for trigger_type in _TICK_TRIGGERS:
		var priority: int = BehaviorMaps.MOVEMENT_RANK.get(trigger_type, 99)
		for i in _behaviors_by_trigger.get(trigger_type, []):
			if i in _disabled_behaviors:
				continue
			var b: Dictionary = _behaviors[i]
			var resolved_target: Node = null

			# Check trigger-specific activation conditions
			if trigger_type == "ON_PROXIMITY":
				resolved_target = _resolve_target(i, null)
				if resolved_target == null or not is_instance_valid(resolved_target) or not (resolved_target is Node2D):
					continue
				var range_px: float = BehaviorMaps.RANGE_PX.get(b.get("range", "MEDIUM"), 128.0)
				var dist: float = _owner_body.global_position.distance_to(resolved_target.global_position)
				if dist > range_px:
					continue

			# Movement exclusivity: skip lower-priority movement if one already ran
			var action: String = b.get("action", "")
			var is_movement: bool = action in BehaviorMaps.MOVEMENT_ACTIONS
			if is_movement and movement_applied and priority >= best_movement_priority:
				continue

			if _try_execute(i, resolved_target):
				if is_movement:
					movement_applied = true
					best_movement_priority = priority


func _try_execute(behavior_index: int, pre_resolved_target: Node = null) -> bool:
	var b: Dictionary = _behaviors[behavior_index]
	var trigger: String = b.get("trigger", "")
	var action: String = b.get("action", "")

	# Movement actions skip cooldown — velocity-based movement needs per-frame
	# application and is self-limiting via max_speed.
	var skip_cooldown: bool = (
		action in BehaviorMaps.MOVEMENT_ACTIONS
		or trigger == "ALWAYS"
		or trigger == "ON_CREATE"
		or trigger == "ON_DESTROY"
	)

	if not skip_cooldown:
		var interval_key: String = b.get("interval", "MEDIUM")
		var cooldown: float = BehaviorMaps.INTERVAL_SECONDS.get(interval_key, 1.5)
		var now: float = Time.get_ticks_msec() / 1000.0
		if behavior_index in _cooldowns:
			if now - _cooldowns[behavior_index] < cooldown:
				return false
		_cooldowns[behavior_index] = now

	return _execute_behavior(behavior_index, pre_resolved_target, action)


func _execute_behavior(behavior_index: int, pre_resolved_target: Node = null, action: String = "") -> bool:
	var b: Dictionary = _behaviors[behavior_index]
	if action.is_empty():
		action = b.get("action", "")

	# Use pre-resolved target if provided, otherwise resolve fresh
	var target: Node = pre_resolved_target if pre_resolved_target != null else _resolve_target(behavior_index, null)

	# Null target is normal (target died, not spawned yet) — not an error.
	if action not in _TARGET_FREE_ACTIONS:
		if target == null or not is_instance_valid(target):
			return false

	var success := true

	match action:
		"MOVE_TOWARD":
			success = _apply_movement(target, b.get("speed", "MEDIUM"), true)
		"MOVE_AWAY":
			success = _apply_movement(target, b.get("speed", "MEDIUM"), false)
		"PATROL":
			_apply_patrol(b.get("speed", "MEDIUM"))
		"DEAL_DAMAGE":
			Log.debug("BehaviorExecutor: DEAL_DAMAGE is deprecated — use damage tags (SHARP, HOSTILE, etc.)")
			success = false
		"APPLY_FORCE":
			success = _apply_force(target, b.get("intensity", "MEDIUM"), false)
		"ATTRACT":
			success = _apply_force(target, b.get("intensity", "MEDIUM"), true)
		"SPAWN_PROJECTILE":
			success = _spawn_projectile(target, b.get("intensity", "MEDIUM"))
		"EXPLODE":
			_apply_explode(b.get("range", "MEDIUM"), b.get("intensity", "MEDIUM"))
		"HEAL":
			success = _apply_heal(target, b.get("intensity", "MEDIUM"))
		"ADD_TAGS":
			success = _apply_tags(target, b.get("tags_to_apply", []), true)
		"REMOVE_TAGS":
			success = _apply_tags(target, b.get("tags_to_apply", []), false)
		"SELF_DESTRUCT":
			WorldMutations.apply_damage(_owner_body, 99999.0)
		_:
			Log.debug("BehaviorExecutor: Unknown action '%s'" % action)
			success = false

	if success:
		_behavior_errors.erase(behavior_index)
		# Skip per-frame movement logs to avoid spam
		if action not in BehaviorMaps.MOVEMENT_ACTIONS:
			var target_name: String = ""
			if target != null and is_instance_valid(target):
				target_name = target.blueprint.get("name", target.name) if "blueprint" in target else target.name
			if target_name != "":
				Log.debug("BehaviorExecutor: '%s' fired %s on '%s'" % [_owner_name(), action, target_name])
			else:
				Log.debug("BehaviorExecutor: '%s' fired %s" % [_owner_name(), action])
	else:
		var count: int = _behavior_errors.get(behavior_index, 0) + 1
		_behavior_errors[behavior_index] = count
		if count >= MAX_BEHAVIOR_ERRORS:
			Log.info("BehaviorExecutor: Disabling behavior %d after %d errors on '%s'" % [
				behavior_index, count, _owner_name()])
			_disabled_behaviors[behavior_index] = true
			_behavior_errors.erase(behavior_index)
			_check_disable_physics_process()

	return success


func _check_disable_physics_process() -> void:
	for trigger in _TICK_TRIGGERS:
		for i in _behaviors_by_trigger.get(trigger, []):
			if i not in _disabled_behaviors:
				return
	set_physics_process(false)




func _resolve_target(behavior_index: int, event_body: Node) -> Node:
	var b: Dictionary = _behaviors[behavior_index]
	var target_type: String = b.get("target", "SELF")

	match target_type:
		"SELF":
			return _owner_body
		"CONTACT_BODY":
			return event_body if event_body != null and is_instance_valid(event_body) else null
		"NEAREST_PLAYER", "NEAREST_LIVING", "NEAREST_OBJECT":
			# Use cached target (updated every 0.3s) to avoid per-frame group scans
			if behavior_index in _target_cache:
				var cached = _target_cache[behavior_index]
				if cached != null and is_instance_valid(cached):
					return cached
			var found := _find_nearest_in_group(_group_for_target(target_type))
			if found == null:
				Log.debug("BehaviorExecutor: Target resolution miss target=%s for '%s'" % [
					target_type, _owner_name()])
			return found
		_:
			Log.debug("BehaviorExecutor: Unknown target type '%s' for '%s'" % [
				target_type, _owner_name()])
			return null


static func _group_for_target(target_type: String) -> String:
	match target_type:
		"NEAREST_PLAYER": return "player"
		"NEAREST_LIVING": return "living"
		"NEAREST_OBJECT": return "game_objects"
		_: return ""


func _find_nearest_in_group(group_name: String) -> Node:
	var nodes := get_tree().get_nodes_in_group(group_name)
	var nearest: Node = null
	var nearest_dist: float = INF
	for node in nodes:
		if node == _owner_body:
			continue
		if not is_instance_valid(node) or not (node is Node2D):
			continue
		var dist: float = _owner_body.global_position.distance_to(node.global_position)
		if dist < nearest_dist:
			nearest_dist = dist
			nearest = node
	return nearest


func _update_target_cache() -> void:
	for i in range(_behaviors.size()):
		var group := _group_for_target(_behaviors[i].get("target", "SELF"))
		if not group.is_empty():
			_target_cache[i] = _find_nearest_in_group(group)


# --- Action implementations ---

func _get_owner_element_color() -> Color:
	return TagColors.derive_element_color(_owner_body)



func _apply_heal(target: Node, intensity: String) -> bool:
	if target == null or not is_instance_valid(target):
		return false
	var amount: float = BehaviorMaps.INTENSITY_HEAL.get(intensity, 25.0)
	WorldMutations.apply_heal(target, amount)
	if target is Node2D:
		EventBus.effect_applied.emit("HEAL", amount, TagColors.HEAL, target.global_position)
	return true


func _apply_movement(target: Node, speed_tier: String, toward: bool) -> bool:
	if target == null or not is_instance_valid(target) or not (target is Node2D):
		return false

	var diff: Vector2 = target.global_position - _owner_body.global_position
	if diff.length_squared() < 16.0:
		return true  # Close enough — don't oscillate

	var direction: Vector2 = diff.normalized()
	if not toward:
		direction = -direction

	var max_speed: float = BehaviorMaps.SPEED_MAX.get(speed_tier, 120.0)
	var accel: float = max_speed * 5.0
	var dt: float = get_physics_process_delta_time()

	# Set velocity directly — apply_central_force can't overcome ground friction.
	var target_vx: float = direction.x * max_speed
	_owner_body.linear_velocity.x = move_toward(
		_owner_body.linear_velocity.x, target_vx, accel * dt)

	# FLOATING objects: also move vertically
	if _owner_body.gravity_scale <= 0.0:
		var target_vy: float = direction.y * max_speed
		_owner_body.linear_velocity.y = move_toward(
			_owner_body.linear_velocity.y, target_vy, accel * dt)
	return true


func _apply_patrol(speed_tier: String) -> void:
	var max_speed: float = BehaviorMaps.SPEED_MAX.get(speed_tier, 120.0)
	var dt: float = get_physics_process_delta_time()

	_patrol_distance += abs(_owner_body.linear_velocity.x) * dt
	if _patrol_distance >= PATROL_MAX_DISTANCE:
		_patrol_direction *= -1.0
		_patrol_distance = 0.0

	var accel: float = max_speed * 5.0
	var target_vx: float = _patrol_direction * max_speed
	_owner_body.linear_velocity.x = move_toward(
		_owner_body.linear_velocity.x, target_vx, accel * dt)


func _apply_force(target: Node, intensity: String, attract: bool) -> bool:
	if target == null or not is_instance_valid(target) or not (target is Node2D):
		return false

	var direction: Vector2 = (target.global_position - _owner_body.global_position).normalized()
	if attract:
		direction = -direction
	var magnitude: float = BehaviorMaps.INTENSITY_FORCE.get(intensity, 200.0)
	WorldMutations.apply_impulse(target, direction, magnitude)
	return true


func _spawn_projectile(target: Node, intensity: String) -> bool:
	if target == null or not is_instance_valid(target) or not (target is Node2D):
		return false

	var projectile = _projectile_scene.instantiate()
	_owner_body.get_parent().add_child(projectile)
	projectile.global_position = _owner_body.global_position

	var direction: Vector2 = (target.global_position - _owner_body.global_position).normalized()
	var damage: float = BehaviorMaps.INTENSITY_DAMAGE.get(intensity, 20.0)

	# Determine payload tag from parent's tags
	var payload_tag: String = ""
	for parent_tag in _owner_body.tags:
		if parent_tag in BehaviorMaps.PAYLOAD_TAG_MAP:
			payload_tag = BehaviorMaps.PAYLOAD_TAG_MAP[parent_tag]
			break

	projectile.init_projectile(direction, damage, payload_tag, _owner_body)
	return true


func _apply_explode(range_tier: String, intensity: String) -> void:
	var radius: float = BehaviorMaps.RANGE_PX.get(range_tier, 128.0)
	var damage: float = BehaviorMaps.INTENSITY_EXPLODE.get(intensity, 40.0)
	var force: float = BehaviorMaps.INTENSITY_FORCE.get(intensity, 200.0)

	if not _owner_body.is_inside_tree():
		return
	var space_state := _owner_body.get_world_2d().direct_space_state
	var query := PhysicsShapeQueryParameters2D.new()
	var circle := CircleShape2D.new()
	circle.radius = radius
	query.shape = circle
	query.transform = Transform2D(0, _owner_body.global_position)
	query.collision_mask = CL.OBJECTS | CL.PLAYER
	query.exclude = [_owner_body.get_rid()]

	var results: Array = space_state.intersect_shape(query, MAX_EXPLOSION_RESULTS)
	for result in results:
		var body: Node = result.get("collider", null)
		if body == null or body == _owner_body or not is_instance_valid(body):
			continue
		WorldMutations.apply_damage(body, damage)
		if body is Node2D:
			EventBus.effect_applied.emit("DAMAGE", damage, _get_owner_element_color(), body.global_position)
			var dir: Vector2 = (body.global_position - _owner_body.global_position).normalized()
			WorldMutations.apply_impulse(body, dir, force)

	Log.info("BehaviorExecutor: EXPLODE radius=%.0f damage=%.0f on '%s'" % [
		radius, damage, _owner_name()])


func _apply_tags(target: Node, tags_list, add: bool) -> bool:
	if target == null or not is_instance_valid(target):
		return false
	if tags_list == null or not (tags_list is Array):
		return false

	# Snapshot tags before mutation for cascade check
	var tags_before: Array = TagColors.get_body_tags(target).duplicate()

	if add:
		for tag in tags_list:
			WorldMutations.apply_add_tag(target, tag, BehaviorMaps.DYNAMIC_TAG_DURATION)
	else:
		for tag in tags_list:
			WorldMutations.apply_remove_tag(target, tag)

	# Cascade only if tags actually changed (mirrors CollisionResolver logic).
	# Start at depth 1 since the behavior mutation itself is the first step.
	var tags_after: Array = TagColors.get_body_tags(target)
	if tags_before != tags_after and target.has_method("get_cascade_neighbors"):
		for neighbor in target.get_cascade_neighbors():
			if is_instance_valid(neighbor):
				CollisionResolver.resolve_collision(target, neighbor, 1)

	return true


func _setup_timer(behavior_index: int, behavior: Dictionary) -> void:
	var interval_key: String = behavior.get("interval", "MEDIUM")
	var seconds: float = BehaviorMaps.INTERVAL_SECONDS.get(interval_key, 1.5)
	var is_once: bool = BehaviorMaps.INTERVAL_IS_ONCE.get(interval_key, false)

	var timer := Timer.new()
	timer.wait_time = seconds
	timer.one_shot = is_once
	timer.timeout.connect(_on_timer_fired.bind(behavior_index))
	add_child(timer)
	timer.start()
	_timers[behavior_index] = timer
	Log.debug("BehaviorExecutor: Timer created for behavior %d interval=%.1fs one_shot=%s on '%s'" % [
		behavior_index, seconds, is_once, _owner_name()])


func _on_timer_fired(behavior_index: int) -> void:
	if behavior_index in _disabled_behaviors:
		return
	if behavior_index in _one_shot_fired:
		return
	Log.debug("BehaviorExecutor: Timer fired behavior %d on '%s'" % [
		behavior_index, _owner_name()])
	_try_execute(behavior_index, null)

	var b: Dictionary = _behaviors[behavior_index]
	var interval_key: String = b.get("interval", "MEDIUM")
	if BehaviorMaps.INTERVAL_IS_ONCE.get(interval_key, false):
		_one_shot_fired[behavior_index] = true
		Log.debug("BehaviorExecutor: One-shot behavior %d completed on '%s'" % [
			behavior_index, _owner_name()])
