class_name AffordanceSystem extends Node

## V3 affordance system: carry (0), mount (1), climb (2), nothing (3).
## Attached to the player. Handles pick up, throw, mount/dismount.

var _held_object: Node = null
var _mounted_object: Node = null
const INTERACT_RANGE := 64.0
const THROW_IMPULSE := 500.0


func try_interact(player: CharacterBody2D) -> bool:
	"""Called when player presses interact. Returns true if interaction started."""
	if _held_object:
		_drop_or_throw(player)
		return true
	if _mounted_object:
		_dismount(player)
		return true
	var nearest := _find_nearest_interactable(player)
	if nearest == null:
		return false
	var affordance: int = nearest.blueprint.get("affordance", 3)
	match affordance:
		0: _carry(player, nearest)
		1: _mount(player, nearest)
		2: pass  # climb handled by overlap detection
		3: return false
	return true


func get_held_object() -> Node:
	return _held_object


func is_mounted() -> bool:
	return _mounted_object != null


func _carry(player: Node, obj: Node) -> void:
	_held_object = obj
	if obj is RigidBody2D:
		obj.freeze = true
	obj.reparent(player)
	obj.position = Vector2(24, -16)
	Log.info("AffordanceSystem: Carrying '%s'" % obj.blueprint.get("name", "?"))


func _drop_or_throw(player: Node) -> void:
	var obj := _held_object
	_held_object = null
	obj.reparent(player.get_parent())
	if obj is RigidBody2D:
		obj.freeze = false
	var facing: int = player._facing if "_facing" in player else 1
	obj.global_position = player.global_position + Vector2(32, 0) * facing
	# If player is moving, throw with impulse
	if player.velocity.length() > 50:
		if obj is RigidBody2D:
			obj.apply_central_impulse(player.velocity.normalized() * THROW_IMPULSE)
	Log.info("AffordanceSystem: Dropped/threw '%s'" % obj.blueprint.get("name", "?"))


func _mount(player: Node, obj: Node) -> void:
	_mounted_object = obj
	player.reparent(obj)
	player.position = Vector2(0, -32)  # sit on top
	Log.info("AffordanceSystem: Mounted '%s'" % obj.blueprint.get("name", "?"))


func _dismount(player: Node) -> void:
	var obj := _mounted_object
	_mounted_object = null
	player.reparent(obj.get_parent())
	player.global_position = obj.global_position + Vector2(0, -48)
	Log.info("AffordanceSystem: Dismounted '%s'" % obj.blueprint.get("name", "?"))


func _find_nearest_interactable(player: Node) -> Node:
	var best: Node = null
	var best_dist: float = INTERACT_RANGE

	for obj in player.get_tree().get_nodes_in_group("game_objects"):
		if obj == player:
			continue
		if not is_instance_valid(obj):
			continue
		if not obj.has_method("get_blueprint"):
			continue
		var affordance: int = obj.blueprint.get("affordance", 3)
		if affordance == 3:
			continue
		if obj is not Node2D:
			continue
		var dist: float = player.global_position.distance_to(obj.global_position)
		if dist < best_dist:
			best_dist = dist
			best = obj

	return best
