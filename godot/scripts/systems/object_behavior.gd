extends Node

## Unified object behavior runtime: per-pair utility-based targeting.
## Handles both active objects (approach/flee) and reactive objects (ignore + priority>0).
## Each subject x target pair has: movement, priority, action, amount, state_action, state_id, force.
## Loaded from InteractionCache at spawn time and on scene changes.

const PERCEPTION_RANGE: float = 500.0
const CONTACT_RANGE: float = 48.0
const FLEE_MULTIPLIER: float = 1.5
const ACTION_COOLDOWN: float = 1.0
const BASE_MOVE_SPEED: float = 200.0
const BASE_FLEE_SPEED: float = 250.0
const MAX_ERRORS: int = 5
const LETHAL_THRESHOLD: int = 100
const INSTANT_KILL_DAMAGE: float = 99999.0
const FORCE_SCALE: float = 5.0
const FORCE_MODIFIER_IMPULSE: float = 40.0  # fixed impulse for knockback modifier

# Speed tier (0-4) → multiplier (mirrors backend SPEED_MULTIPLIER)
const SPEED_MULTIPLIERS: Dictionary = {0: 0.3, 1: 0.6, 2: 1.0, 3: 1.5, 4: 2.0}

# Priority level (0-3) → utility weight (mirrors backend PRIORITY_WEIGHTS)
const PRIORITY_WEIGHTS: Dictionary = {0: 0.0, 1: 25.0, 2: 60.0, 3: 100.0}

var _owner: RigidBody2D
var _owner_name: String
var _is_autonomous: bool = false
var _pairs: Dictionary = {}  # target_name -> behavior dict
var _target_nodes: Dictionary = {}  # target_name -> Node (cached refs)
var _action_timer: float = 0.0
var _error_count: int = 0
var _disabled_logged: bool = false
var current_target_name: String = ""
var current_movement: int = 2      # 2=no target
var current_action: int = 0        # 0=nothing
var current_action_amount: int = 0
var current_best_utility: float = -1.0
var current_target_distance: float = 0.0

# Per-instance speeds computed from speed tier
var _move_speed: float = BASE_MOVE_SPEED
var _flee_speed: float = BASE_FLEE_SPEED


func init_object(owner: RigidBody2D, obj_name: String, speed_tier: int = 2, is_autonomous: bool = false) -> void:
	_owner = owner
	_owner_name = obj_name
	_is_autonomous = is_autonomous
	if is_autonomous:
		var mult: float = SPEED_MULTIPLIERS.get(speed_tier, 1.0)
		_move_speed = BASE_MOVE_SPEED * mult
		_flee_speed = BASE_FLEE_SPEED * mult
	else:
		_move_speed = 0.0
		_flee_speed = 0.0
	EventBus.object_created.connect(_on_object_created)
	EventBus.behavior_updated.connect(_on_behavior_updated)
	call_deferred("_scan_existing")


func _scan_existing() -> void:
	for node in _owner.get_tree().get_nodes_in_group("game_objects"):
		if node == _owner:
			continue
		_try_add_target(node)
	# Also scan the player (separate group, not in game_objects)
	for node in _owner.get_tree().get_nodes_in_group("player"):
		_try_add_target(node)


func _on_object_created(blueprint: Dictionary) -> void:
	# Add the new object by scanning only newly entered nodes
	# (the object enters the group after init_from_blueprint)
	call_deferred("_scan_for_new", blueprint.get("name", ""))


func _scan_for_new(target_name: String) -> void:
	if target_name.is_empty() or target_name in _pairs:
		return
	for node in _owner.get_tree().get_nodes_in_group("game_objects"):
		if node == _owner:
			continue
		if node.has_method("get_object_name") and node.get_object_name() == target_name:
			_try_add_target(node)
			break


func _try_add_target(node: Node) -> void:
	if not node.has_method("get_object_name"):
		return
	var target_name: String = node.get_object_name()
	if target_name.is_empty() or target_name == _owner_name:
		return
	var entry: Dictionary = InteractionCache.lookup_behavior(_owner_name, target_name)
	if not entry.is_empty():
		_pairs[target_name] = entry
		_target_nodes[target_name] = node
		if not node.tree_exiting.is_connected(_on_target_removed):
			node.tree_exiting.connect(_on_target_removed.bind(target_name))


func _on_target_removed(target_name: String) -> void:
	_pairs.erase(target_name)
	_target_nodes.erase(target_name)


func _on_behavior_updated(subject_name: String) -> void:
	if subject_name.to_lower() != _owner_name.to_lower():
		return
	# Refresh all pairs from InteractionCache
	for tname in _pairs.keys():
		var entry: Dictionary = InteractionCache.lookup_behavior(_owner_name, tname)
		if not entry.is_empty():
			_pairs[tname] = entry


func _physics_process(delta: float) -> void:
	if _error_count >= MAX_ERRORS:
		if not _disabled_logged:
			Log.warn("ObjectBehavior: Disabled after %d errors for '%s'" % [MAX_ERRORS, _owner_name])
			_disabled_logged = true
		return
	if not is_instance_valid(_owner):
		return
	_action_timer = maxf(0.0, _action_timer - delta)

	# Clear debug state (overwritten below if a target is found)
	current_target_name = ""
	current_movement = 2
	current_action = 0
	current_action_amount = 0
	current_best_utility = -1.0
	current_target_distance = 0.0

	# Utility scoring for ALL pairs (active + reactive)
	var best_target: Node = null
	var best_utility: float = -1.0
	var best_entry: Dictionary = {}

	for tname in _pairs:
		var node: Node = _target_nodes.get(tname)
		if node == null or not is_instance_valid(node):
			continue
		var entry: Dictionary = _pairs[tname]
		var movement: int = entry.get("movement", 2)
		var priority: int = entry.get("priority", 0)

		# Skip truly inert pairs (ignore movement AND zero priority)
		if movement == 2 and priority == 0:
			continue

		var weight: float = PRIORITY_WEIGHTS.get(priority, 0.0)
		var dist: float = _owner.global_position.distance_to(node.global_position)
		if dist > PERCEPTION_RANGE:
			continue
		var utility: float = weight / (1.0 + dist / PERCEPTION_RANGE)
		if movement == 1:  # flee
			utility *= FLEE_MULTIPLIER
		if utility > best_utility:
			best_utility = utility
			best_target = node
			best_entry = entry

	if best_target == null:
		return

	# Expose for debug overlay
	current_target_name = best_target.get_object_name() if best_target.has_method("get_object_name") else "?"
	current_movement = best_entry.get("movement", 2)
	current_action = best_entry.get("action", 0)
	current_action_amount = best_entry.get("amount", 0)
	current_best_utility = best_utility
	current_target_distance = _owner.global_position.distance_to(best_target.global_position)

	var movement: int = best_entry.get("movement", 2)
	var dir: Vector2 = (best_target.global_position - _owner.global_position).normalized()
	var dist: float = _owner.global_position.distance_to(best_target.global_position)

	match movement:
		0:  # approach
			if _is_autonomous:
				WorldMutations.apply_movement_force(_owner, dir, _move_speed, _move_speed)
			if dist <= CONTACT_RANGE and _action_timer <= 0.0:
				_execute_action(best_entry, best_target)
				_action_timer = ACTION_COOLDOWN
		1:  # flee
			if _is_autonomous:
				WorldMutations.apply_movement_force(_owner, -dir, _flee_speed, _flee_speed)
		2:  # ignore with priority > 0 (reactive)
			if dist <= CONTACT_RANGE and _action_timer <= 0.0:
				_execute_action(best_entry, best_target)
				_action_timer = ACTION_COOLDOWN


func _record_error(reason: String) -> void:
	_error_count += 1
	Log.debug("ObjectBehavior: Action error for '%s' - %s (%d/%d)" % [_owner_name, reason, _error_count, MAX_ERRORS])


func _execute_action(entry: Dictionary, target: Node) -> void:
	if not is_instance_valid(target):
		_record_error("invalid target")
		return
	var action: int = entry.get("action", 0)
	var amount: int = entry.get("amount", 0)
	var state_action: int = entry.get("state_action", 0)
	var state_id: int = entry.get("state_id", 0)
	var force: int = entry.get("force", 0)

	# Primary action
	match action:
		0:  # nothing
			pass
		1:  # damage
			if not target.has_method("take_damage"):
				_record_error("target missing take_damage")
				return
			var effective: float = INSTANT_KILL_DAMAGE if amount >= LETHAL_THRESHOLD else (float(amount) if amount > 0 else 15.0)
			WorldMutations.apply_damage(target, effective)
		2:  # heal
			if not target.has_method("heal"):
				_record_error("target missing heal")
				return
			WorldMutations.apply_heal(target, float(amount) if amount > 0 else 10.0)
		3:  # consume
			if not target.has_method("take_damage"):
				_record_error("target missing take_damage for consume")
				return
			WorldMutations.apply_damage(target, INSTANT_KILL_DAMAGE)
		4:  # push (primary)
			var force_dir: Vector2 = (target.global_position - _owner.global_position).normalized()
			var magnitude: float = float(amount) * FORCE_SCALE if amount > 0 else 30.0 * FORCE_SCALE
			WorldMutations.apply_impulse(target, force_dir, magnitude)

	# State modifier
	if state_action == 1 and state_id >= 1 and state_id <= 4:
		if target.has_method("add_state"):
			WorldMutations.apply_add_state(
				target, StateContradictions.STATE_NAMES[state_id], 10.0
			)
	elif state_action == 2 and state_id >= 1 and state_id <= 4:
		if target.has_method("remove_state"):
			WorldMutations.apply_remove_state(
				target, StateContradictions.STATE_NAMES[state_id]
			)

	# Force modifier (knockback on damage only)
	if force == 1 and action == 1:
		var force_dir: Vector2 = (target.global_position - _owner.global_position).normalized()
		WorldMutations.apply_impulse(target, force_dir, FORCE_MODIFIER_IMPULSE * FORCE_SCALE)
