extends Node

## V3 creature behavior runtime: per-pair utility-based targeting.
## Each creature x object pair has: movement(0-3), strength(0-100), action(0-6), param.
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

var _owner: RigidBody2D
var _owner_name: String
var _pairs: Dictionary = {}  # target_name -> behavior dict
var _action_timer: float = 0.0
var _error_count: int = 0


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


func _on_object_created(_blueprint: Dictionary) -> void:
	# New objects may have creature behavior entries — rescan on next tick
	call_deferred("_scan_existing")


func _try_add_target(node: Node) -> void:
	if not node.has_method("get_object_name"):
		return
	var target_name: String = node.get_object_name()
	if target_name.is_empty() or target_name == _owner_name:
		return
	var entry: Dictionary = InteractionCache.lookup_creature(_owner_name, target_name)
	if not entry.is_empty():
		_pairs[target_name] = entry


func _physics_process(delta: float) -> void:
	if _error_count >= MAX_ERRORS or not is_instance_valid(_owner):
		return
	_action_timer = maxf(0.0, _action_timer - delta)

	# Utility scoring: find highest-utility target
	var best_target: Node = null
	var best_utility: float = -1.0
	var best_entry: Dictionary = {}

	for node in _owner.get_tree().get_nodes_in_group("game_objects"):
		if node == _owner or not is_instance_valid(node):
			continue
		if not node.has_method("get_object_name"):
			continue
		var tname: String = node.get_object_name()
		if tname not in _pairs:
			continue
		var entry: Dictionary = _pairs[tname]
		var movement: int = entry.get("movement", 3)
		if movement == 3:  # ignore
			continue
		var strength: float = float(entry.get("strength", 0))
		var dist: float = _owner.global_position.distance_to(node.global_position)
		if dist > PERCEPTION_RANGE:
			continue
		var utility: float = strength / (1.0 + dist / PERCEPTION_RANGE)
		if movement == 1:  # flee
			utility *= FLEE_MULTIPLIER
		if utility > best_utility:
			best_utility = utility
			best_target = node
			best_entry = entry

	if best_target == null:
		return

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


func _execute_action(entry: Dictionary, target: Node) -> void:
	var action: int = entry.get("action", 0)
	var param: int = entry.get("param", 0)
	match action:
		0:  # nothing
			pass
		1:  # damage
			WorldMutations.apply_damage(target, float(param) if param > 0 else 15.0)
		2:  # heal
			WorldMutations.apply_heal(target, float(param) if param > 0 else 10.0)
		3:  # add_state
			if param >= 1 and param <= 7:
				WorldMutations.apply_add_state(
					target, CollisionResolver.STATE_NAMES[param], 10.0
				)
		4:  # remove_state
			if param >= 1 and param <= 7:
				WorldMutations.apply_remove_state(
					target, CollisionResolver.STATE_NAMES[param]
				)
		5:  # destroy
			WorldMutations.apply_damage(target, 99999.0)
		6:  # take
			pass  # needs affordance system integration
