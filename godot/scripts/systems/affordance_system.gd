extends Node

## V3 Affordance system: carry, mount, climb.
## Attached to the player. Checks nearest object's affordance on interact input.

const CL = preload("res://scripts/data/collision_layers.gd")

enum Affordance { CARRY = 0, MOUNT = 1, CLIMB = 2, NONE = 3 }

const INTERACT_RANGE: float = 64.0
const THROW_FORCE: float = 600.0
const SWING_ARC: float = PI / 3.0  # 60 degrees
const SWING_DURATION: float = 0.2
const MASS_CARRY_LIMIT: float = 50.0  # kg — can't carry objects heavier than this

var _player: CharacterBody2D
var _held_object: RigidBody2D = null
var _mount_object: Node2D = null
var _hand_marker: Marker2D
var _swing_timer: float = 0.0
var _facing: int = 1  # 1 = right, -1 = left


func init(player: CharacterBody2D) -> void:
	_player = player
	_hand_marker = Marker2D.new()
	_hand_marker.name = "HandMarker"
	_hand_marker.position = Vector2(24, -8)
	_player.add_child(_hand_marker)


func _physics_process(delta: float) -> void:
	if _swing_timer > 0.0:
		_swing_timer -= delta
		if _swing_timer <= 0.0 and _held_object != null:
			_hand_marker.rotation = 0.0

	# Update facing from player
	if _player.has_method("get_facing"):
		_facing = _player.get_facing()
	_hand_marker.position.x = 24.0 * _facing


func interact() -> void:
	if _held_object != null:
		throw_held(Vector2(_facing, -0.3).normalized())
		return
	if _mount_object != null:
		dismount()
		return

	var nearest: Node = _find_nearest_interactable()
	if nearest == null:
		return

	var aff: int = nearest.blueprint.get("affordance", 3) if nearest.has_method("get_blueprint") else 3
	match aff:
		Affordance.CARRY:
			pickup(nearest)
		Affordance.MOUNT:
			mount(nearest)
		Affordance.CLIMB:
			pass  # Climb is handled by overlap, not interact press


func is_holding() -> bool:
	return _held_object != null


func is_mounted() -> bool:
	return _mount_object != null


# --- Carry ---

func pickup(obj: RigidBody2D) -> void:
	if obj.mass > MASS_CARRY_LIMIT:
		# Too heavy — push instead
		var dir := Vector2(_facing, 0)
		WorldMutations.apply_impulse(obj, dir, 200.0)
		return

	_held_object = obj
	_held_object.freeze = true
	_held_object.collision_layer = 0
	_held_object.collision_mask = 0
	# Reparent under hand marker
	var global_pos: Vector2 = _held_object.global_position
	_held_object.get_parent().remove_child(_held_object)
	_hand_marker.add_child(_held_object)
	_held_object.position = Vector2.ZERO
	Log.info("AffordanceSystem: Picked up '%s'" % _held_object.get_object_name())


func swing() -> void:
	if _held_object == null or _swing_timer > 0.0:
		return
	_swing_timer = SWING_DURATION
	# Rotate hand through arc
	var start_angle: float = -SWING_ARC / 2.0
	var end_angle: float = SWING_ARC / 2.0
	var tween := _hand_marker.create_tween()
	_hand_marker.rotation = start_angle * _facing
	tween.tween_property(_hand_marker, "rotation", end_angle * _facing, SWING_DURATION)

	# Check overlaps during swing — apply held object's pairwise interaction
	await _player.get_tree().create_timer(SWING_DURATION * 0.5).timeout
	if not is_instance_valid(_held_object):
		return
	var space_state := _player.get_world_2d().direct_space_state
	var query := PhysicsShapeQueryParameters2D.new()
	var circle := CircleShape2D.new()
	circle.radius = INTERACT_RANGE
	query.shape = circle
	query.transform = Transform2D(0, _hand_marker.global_position)
	query.collision_mask = CL.OBJECTS
	for result in space_state.intersect_shape(query, 8):
		var target: Node = result.get("collider", null)
		if target == null or target == _held_object or target == _player:
			continue
		CollisionResolver.resolve_collision(_held_object, target)


func throw_held(direction: Vector2) -> void:
	if _held_object == null:
		return
	var obj: RigidBody2D = _held_object
	_held_object = null
	var global_pos: Vector2 = obj.global_position
	_hand_marker.remove_child(obj)
	_player.get_parent().add_child(obj)
	obj.global_position = global_pos
	obj.freeze = false
	obj.collision_layer = CL.OBJECTS
	obj.collision_mask = CL.TERRAIN | CL.PLAYER | CL.OBJECTS
	obj.apply_central_impulse(direction * THROW_FORCE)
	Log.info("AffordanceSystem: Threw '%s'" % obj.get_object_name())


func drop() -> void:
	throw_held(Vector2.ZERO)


# --- Mount ---

func mount(obj: Node2D) -> void:
	_mount_object = obj
	# Player follows mount
	Log.info("AffordanceSystem: Mounted '%s'" % obj.get_object_name())


func dismount() -> void:
	if _mount_object == null:
		return
	Log.info("AffordanceSystem: Dismounted")
	_mount_object = null


# --- Helpers ---

func _find_nearest_interactable() -> Node:
	var best: Node = null
	var best_dist: float = INTERACT_RANGE
	for node in _player.get_tree().get_nodes_in_group("game_objects"):
		if not is_instance_valid(node) or node is not Node2D:
			continue
		var dist: float = _player.global_position.distance_to(node.global_position)
		if dist < best_dist:
			var aff: int = 3
			if node.has_method("get_blueprint"):
				aff = node.get_blueprint().get("affordance", 3)
			elif "affordance" in node:
				aff = node.affordance
			if aff != Affordance.NONE:
				best = node
				best_dist = dist
	return best
