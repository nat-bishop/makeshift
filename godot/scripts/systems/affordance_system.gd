extends Node

## V3 Affordance system: carry and ride via combined sprite swap.
## On pickup/mount the player sprite swaps to a pre-cached combined image.
## On drop/dismount the originals are restored. Attack while holding throws the object.

enum Affordance { CARRY = 0, MOUNT = 1, CLIMB = 2, NONE = 3 }

const INTERACT_RANGE: float = 64.0
const THROW_FORCE: float = 600.0
const MASS_CARRY_LIMIT: float = 50.0  # kg — can't carry objects heavier than this

var _player: CharacterBody2D
var _held_collision_layer: int = 0
var _held_collision_mask: int = 0


func init(player: CharacterBody2D) -> void:
	_player = player


func interact() -> void:
	if _player.held_object != null:
		_drop()
		return

	var nearest: Node = _find_nearest_interactable()
	if nearest == null:
		return

	var aff: int = nearest.affordance if "affordance" in nearest else Affordance.NONE
	match aff:
		Affordance.CARRY:
			_acquire(nearest)
		Affordance.MOUNT:
			_acquire(nearest)


func _acquire(obj: Node) -> void:
	# Mass limit (carry only — mounts can be heavy)
	if obj.affordance == Affordance.CARRY and obj is RigidBody2D and obj.mass > MASS_CARRY_LIMIT:
		var dir := Vector2(_player.get_facing(), 0)
		WorldMutations.apply_impulse(obj, dir, 200.0)
		return

	var tex: Texture2D = _get_combined_texture(obj)
	if tex == null:
		Log.warn("AffordanceSystem: No combined sprite for '%s'" % obj.get_object_name())
		return

	# Hide and disable physics so creatures/propagation don't target it
	obj.visible = false
	if obj is RigidBody2D:
		_held_collision_layer = obj.collision_layer
		_held_collision_mask = obj.collision_mask
		obj.freeze = true
		obj.collision_layer = 0
		obj.collision_mask = 0

	# Auto-restore if held object is destroyed while carried
	obj.tree_exiting.connect(_on_held_object_freed, CONNECT_ONE_SHOT)

	_player.swap_to_combined_sprite(tex, obj)
	var action: String = "Mounted" if obj.affordance == Affordance.MOUNT else "Picked up"
	Log.info("AffordanceSystem: %s '%s'" % [action, obj.get_object_name()])


func throw_held() -> void:
	var obj: Node = _release()
	if obj == null:
		return
	var facing: int = _player.get_facing()
	obj.global_position = _player.global_position + Vector2(facing * 40, -10)
	if obj is RigidBody2D:
		var throw_dir := Vector2(facing, -0.3).normalized()
		obj.apply_central_impulse(throw_dir * THROW_FORCE)
	Log.info("AffordanceSystem: Threw '%s'" % obj.get_object_name())


func _drop() -> void:
	var obj: Node = _release()
	if obj == null:
		return
	var facing: int = _player.get_facing()
	obj.global_position = _player.global_position + Vector2(facing * 40, 0)
	Log.info("AffordanceSystem: Dropped '%s'" % obj.get_object_name())


func _release() -> Node:
	var obj: Node = _player.restore_original_sprite()
	if obj == null or not is_instance_valid(obj):
		return null
	# Disconnect destruction watcher
	if obj.tree_exiting.is_connected(_on_held_object_freed):
		obj.tree_exiting.disconnect(_on_held_object_freed)
	# Restore visibility and physics
	obj.visible = true
	if obj is RigidBody2D:
		obj.freeze = false
		obj.collision_layer = _held_collision_layer
		obj.collision_mask = _held_collision_mask
	return obj


func _on_held_object_freed() -> void:
	_player.restore_original_sprite()
	Log.info("AffordanceSystem: Held object destroyed, restored player sprite")


# --- Helpers ---

func _get_combined_texture(obj: Node) -> Texture2D:
	if obj.has_meta("combined_texture"):
		return obj.get_meta("combined_texture")
	# Fall back to buffered cache (texture arrived before object was placed)
	var tex: Texture2D = Backend.get_combined_sprite(obj.get_object_id())
	if tex != null:
		obj.set_meta("combined_texture", tex)
	return tex


func _find_nearest_interactable() -> Node:
	var best: Node = null
	var best_dist: float = INTERACT_RANGE
	for node in _player.get_tree().get_nodes_in_group("game_objects"):
		if not is_instance_valid(node) or node is not Node2D:
			continue
		var dist: float = _player.global_position.distance_to(node.global_position)
		if dist < best_dist:
			var aff: int = Affordance.NONE
			if "affordance" in node:
				aff = node.affordance
			if aff == Affordance.CARRY or aff == Affordance.MOUNT:
				best = node
				best_dist = dist
	return best
