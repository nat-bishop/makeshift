extends Node

## V3 creature behavior runtime: per-pair utility-based targeting.
## Each creature x object pair has: movement(0-3), priority(0-3), action(0-6), param.
## Loaded from InteractionCache at spawn time and on scene changes.

const PERCEPTION_RANGE: float = 500.0
const CONTACT_RANGE: float = 48.0
const ORBIT_RANGE: float = 128.0
const FLEE_MULTIPLIER: float = 1.5
const ACTION_COOLDOWN: float = 1.0
const MOVE_SPEED: float = 200.0
const FLEE_SPEED: float = 250.0
const ORBIT_SPEED: float = 150.0
const MAX_ERRORS: int = 5

# Priority level (0-3) → utility weight (mirrors backend PRIORITY_WEIGHTS)
const PRIORITY_WEIGHTS: Dictionary = {0: 0.0, 1: 25.0, 2: 60.0, 3: 100.0}

var _owner: RigidBody2D
var _owner_name: String
var _pairs: Dictionary = {}  # target_name -> behavior dict
var _target_nodes: Dictionary = {}  # target_name -> Node (cached refs)
var _action_timer: float = 0.0
var _error_count: int = 0
var _disabled_logged: bool = false
var current_target_name: String = ""
var current_movement: int = 3      # 3=no target
var current_action: int = 0        # 0=nothing
var current_action_amount: int = 0


func init_creature(owner: RigidBody2D, creature_name: String) -> void:
	_owner = owner
	_owner_name = creature_name
	EventBus.object_created.connect(_on_object_created)
	call_deferred("_scan_existing")


func _scan_existing() -> void:
	for node in _owner.get_tree().get_nodes_in_group("game_objects"):
		if node == _owner:
			continue
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
	var entry: Dictionary = InteractionCache.lookup_creature(_owner_name, target_name)
	if not entry.is_empty():
		_pairs[target_name] = entry
		_target_nodes[target_name] = node


func _physics_process(delta: float) -> void:
	if _error_count >= MAX_ERRORS:
		if not _disabled_logged:
			Log.warn("CreatureBehavior: Disabled after %d errors for '%s'" % [MAX_ERRORS, _owner_name])
			_disabled_logged = true
		return
	if not is_instance_valid(_owner):
		return
	_action_timer = maxf(0.0, _action_timer - delta)

	# Clear debug state (overwritten below if a target is found)
	current_target_name = ""
	current_movement = 3
	current_action = 0
	current_action_amount = 0

	# Utility scoring using cached node refs (not group iteration)
	var best_target: Node = null
	var best_utility: float = -1.0
	var best_entry: Dictionary = {}

	for tname in _pairs:
		var node: Node = _target_nodes.get(tname)
		if node == null or not is_instance_valid(node):
			continue
		var entry: Dictionary = _pairs[tname]
		var movement: int = entry.get("movement", 3)
		if movement == 3:  # ignore
			continue
		var priority: int = entry.get("priority", 0)
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
	current_movement = best_entry.get("movement", 3)
	current_action = best_entry.get("action", 0)
	current_action_amount = best_entry.get("amount", 0)

	var movement: int = best_entry.get("movement", 3)
	var dir: Vector2 = (best_target.global_position - _owner.global_position).normalized()
	var dist: float = _owner.global_position.distance_to(best_target.global_position)

	match movement:
		0:  # approach
			WorldMutations.apply_movement_force(_owner, dir, MOVE_SPEED, MOVE_SPEED)
			if dist <= CONTACT_RANGE and _action_timer <= 0.0:
				_execute_action(best_entry, best_target)
				_action_timer = ACTION_COOLDOWN
		1:  # flee
			WorldMutations.apply_movement_force(_owner, -dir, FLEE_SPEED, FLEE_SPEED)
		2:  # orbit
			var tangent: Vector2 = dir.rotated(PI / 2.0)
			if dist < ORBIT_RANGE:
				tangent = (tangent - dir * 0.3).normalized()
			elif dist > ORBIT_RANGE * 1.5:
				tangent = (tangent + dir * 0.3).normalized()
			WorldMutations.apply_movement_force(_owner, tangent, ORBIT_SPEED, ORBIT_SPEED)
			if dist <= ORBIT_RANGE * 1.2 and dist >= ORBIT_RANGE * 0.5 and _action_timer <= 0.0:
				_execute_action(best_entry, best_target)
				_action_timer = ACTION_COOLDOWN


func _record_error(reason: String) -> void:
	_error_count += 1
	Log.debug("CreatureBehavior: Action error for '%s' - %s (%d/%d)" % [_owner_name, reason, _error_count, MAX_ERRORS])


func _execute_action(entry: Dictionary, target: Node) -> void:
	if not is_instance_valid(target):
		_record_error("invalid target")
		return
	var action: int = entry.get("action", 0)
	var amount: int = entry.get("amount", 0)
	var state_id: int = entry.get("state_id", 0)
	match action:
		0:  # nothing
			pass
		1:  # damage
			if not target.has_method("take_damage"):
				_record_error("target missing take_damage")
				return
			WorldMutations.apply_damage(target, float(amount) if amount > 0 else 15.0)
		2:  # heal
			if not target.has_method("heal"):
				_record_error("target missing heal")
				return
			WorldMutations.apply_heal(target, float(amount) if amount > 0 else 10.0)
		3:  # add_state
			if state_id < 1 or state_id > 7 or not target.has_method("add_state"):
				_record_error("invalid state_id or target missing add_state")
				return
			WorldMutations.apply_add_state(
				target, CollisionResolver.STATE_NAMES[state_id], 10.0
			)
		4:  # remove_state
			if state_id < 1 or state_id > 7 or not target.has_method("remove_state"):
				_record_error("invalid state_id or target missing remove_state")
				return
			WorldMutations.apply_remove_state(
				target, CollisionResolver.STATE_NAMES[state_id]
			)
		5:  # destroy
			if not target.has_method("take_damage"):
				_record_error("target missing take_damage for destroy")
				return
			WorldMutations.apply_damage(target, 99999.0)
		6:  # take
			pass  # needs affordance system integration
