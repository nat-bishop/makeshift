extends Node

## V3 Verb Behavior System — receives behaviors from backend via WebSocket.
## Each behavior: {target_name, movement (0-3), strength (0-100), action (0-6), action_param}
## Movement: 0=approach, 1=flee, 2=orbit, 3=ignore
## Action: 0=nothing, 1=damage, 2=heal, 3=add state, 4=remove state, 5=destroy, 6=take

const MELEE_RANGE: float = 48.0
const MELEE_COOLDOWN: float = 1.0
const MOVE_SPEED: float = 150.0
const FLEE_SPEED: float = 250.0
const ORBIT_DISTANCE: float = 80.0
const ORBIT_SPEED: float = 100.0
const MAX_ERRORS: int = 5
const PERCEPTION_RANGE: float = 400.0

var _owner_body: RigidBody2D
var _behaviors: Array = []
var _error_count: int = 0
var _disabled: bool = false
var _melee_timer: float = 0.0


func init_behaviors(behaviors: Array, owner: RigidBody2D) -> void:
	_owner_body = owner
	_behaviors = behaviors


func update_behaviors(behaviors: Array) -> void:
	## Called when backend sends updated creature_behaviors.
	_behaviors = behaviors


func _physics_process(delta: float) -> void:
	if _disabled or _behaviors.is_empty() or _owner_body == null:
		return

	_melee_timer = maxf(0.0, _melee_timer - delta)

	# Utility-based priority selection
	var best_target: Node = null
	var best_utility: float = -1.0
	var best_behavior: Dictionary = {}

	for behavior in _behaviors:
		if behavior is not Dictionary:
			continue
		var target := _find_target_by_name(behavior.get("target_name", ""))
		if target == null or not is_instance_valid(target):
			continue
		var dist: float = _owner_body.global_position.distance_to(target.global_position)
		if dist > PERCEPTION_RANGE:
			continue
		var strength: float = float(behavior.get("strength", 50))
		var utility: float = strength / (1.0 + dist / PERCEPTION_RANGE)
		var movement: int = behavior.get("movement", 3)
		if movement == 1:  # flee
			utility *= 1.5
		if utility > best_utility:
			best_utility = utility
			best_target = target
			best_behavior = behavior

	if best_target == null:
		return

	var movement: int = best_behavior.get("movement", 3)
	match movement:
		0: _approach(best_target)
		1: _flee_from(best_target)
		2: _orbit(best_target)

	# On-arrival action for approach/orbit
	if movement in [0, 2]:
		var dist: float = _owner_body.global_position.distance_to(best_target.global_position)
		if dist < MELEE_RANGE:
			_execute_action(best_behavior, best_target)


func _approach(target: Node) -> void:
	if target is not Node2D:
		return
	var direction: Vector2 = (target.global_position - _owner_body.global_position).normalized()
	WorldMutations.apply_movement_force(_owner_body, direction, MOVE_SPEED, MOVE_SPEED)


func _flee_from(target: Node) -> void:
	if target is not Node2D:
		return
	var direction: Vector2 = (_owner_body.global_position - target.global_position).normalized()
	WorldMutations.apply_movement_force(_owner_body, direction, FLEE_SPEED, FLEE_SPEED)


func _orbit(target: Node) -> void:
	if target is not Node2D:
		return
	var to_target: Vector2 = target.global_position - _owner_body.global_position
	var dist: float = to_target.length()
	if dist < 1.0:
		return

	# Move tangentially while maintaining orbit distance
	var tangent := Vector2(-to_target.y, to_target.x).normalized()
	var radial: Vector2 = to_target.normalized()
	var radial_correction: float = (dist - ORBIT_DISTANCE) / ORBIT_DISTANCE
	var direction: Vector2 = (tangent + radial * radial_correction).normalized()
	WorldMutations.apply_movement_force(_owner_body, direction, ORBIT_SPEED, ORBIT_SPEED)


func _execute_action(behavior: Dictionary, target: Node) -> void:
	if _melee_timer > 0.0:
		return
	_melee_timer = MELEE_COOLDOWN

	var action: int = behavior.get("action", 0)
	var param: int = behavior.get("action_param", 0)

	match action:
		0: pass  # nothing
		1:  # damage
			WorldMutations.apply_damage(target, float(param))
		2:  # heal
			WorldMutations.apply_heal(target, float(param))
		3:  # add state
			if param >= 1 and param <= 7:
				var state_name: String = EffectExecutor.STATES[param - 1]
				if target.has_method("add_state"):
					target.add_state(state_name)
				elif target.has_method("add_tag"):
					target.add_tag(state_name)
		4:  # remove state
			if param >= 1 and param <= 7:
				var state_name: String = EffectExecutor.STATES[param - 1]
				if target.has_method("remove_state"):
					target.remove_state(state_name)
				elif target.has_method("remove_tag"):
					target.remove_tag(state_name)
		5:  # destroy
			if target.has_method("take_damage"):
				target.take_damage(99999)
		6: pass  # take — requires affordance system


func _find_target_by_name(target_name: String) -> Node:
	if target_name.is_empty():
		return null
	var lower_name: String = target_name.to_lower()
	for node in get_tree().get_nodes_in_group("game_objects"):
		if node == _owner_body:
			continue
		if not is_instance_valid(node):
			continue
		if node.has_method("get_blueprint"):
			var bp: Dictionary = node.get_blueprint()
			if bp.get("name", "").to_lower() == lower_name:
				return node
	# Also check player
	var player := get_tree().get_first_node_in_group("player")
	if player != null and "player" in lower_name:
		return player
	return null
