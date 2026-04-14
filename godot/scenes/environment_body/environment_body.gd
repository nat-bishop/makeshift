extends StaticBody2D
## V3 Environment body: named, indestructible object in the pairwise cache.
## Participates in interactions via duck typing: get_object_name(), get_states(),
## add_state(), remove_state(). No take_damage/heal (indestructible).

const CL = preload("res://scripts/data/collision_layers.gd")

var env_name: String = ""
var blueprint: Dictionary = {}
var _state_manager: StateManager = null
var _solid: bool = true
var _initially_solid: bool = true
var _visual: ColorRect
var _initial_color: Color
var _field_area: Area2D

const FIELD_MARGIN: float = 32.0


func init_env(name: String, bp: Dictionary, size: Vector2, color: Color, solid: bool = true) -> void:
	env_name = name
	blueprint = bp

	_state_manager = StateManager.new()
	_state_manager.name = "StateManager"
	add_child(_state_manager)
	_state_manager.init_states(name)
	_state_manager.states_changed.connect(_on_states_changed)

	_solid = solid
	_initially_solid = solid
	_initial_color = color

	collision_layer = CL.OBJECTS if solid else 0
	collision_mask = 0

	# Physics shape
	var body_shape := CollisionShape2D.new()
	var rect := RectangleShape2D.new()
	rect.size = size
	body_shape.shape = rect
	add_child(body_shape)

	# Visual
	_visual = ColorRect.new()
	_visual.size = size
	_visual.position = -size / 2
	_visual.color = color
	add_child(_visual)

	# Detection Area2D
	_field_area = Area2D.new()
	_field_area.name = "FieldArea"
	_field_area.collision_layer = 0
	_field_area.collision_mask = CL.OBJECTS | CL.PLAYER
	_field_area.monitoring = true
	_field_area.monitorable = false
	var area_shape := CollisionShape2D.new()
	var field_rect := RectangleShape2D.new()
	field_rect.size = size + Vector2(FIELD_MARGIN * 2, FIELD_MARGIN * 2)
	area_shape.shape = field_rect
	_field_area.add_child(area_shape)
	add_child(_field_area)

	# Group for interaction targeting
	add_to_group("game_objects")

	Log.info("EnvironmentBody: Initialized '%s', solid=%s" % [env_name, solid])


func get_object_name() -> String:
	return env_name


func get_states() -> Array:
	return _state_manager.get_states() if _state_manager != null else []


func get_tags() -> Array[String]:
	## Compatibility alias.
	var result: Array[String] = []
	for s in get_states():
		result.append(s)
	return result


func get_object_id() -> String:
	return env_name


func add_state(state: String, duration: float = 0.0) -> void:
	if _state_manager != null:
		_state_manager.add_state(state, duration)


func remove_state(state: String) -> void:
	if _state_manager != null:
		_state_manager.remove_state(state)


func _on_states_changed(_updated_states: Array) -> void:
	_update_solidity()
	_update_visuals()
	InteractionCache.mark_stale(env_name)


func _update_solidity() -> void:
	var should_be_solid: bool
	if _state_manager != null and _state_manager.has_state("frozen"):
		should_be_solid = true  # Frozen surface is walkable
	else:
		should_be_solid = _initially_solid
	if should_be_solid != _solid:
		_solid = should_be_solid
		collision_layer = CL.OBJECTS if _solid else 0


func _update_visuals() -> void:
	if _visual == null:
		return
	if _state_manager != null and _state_manager.has_state("frozen"):
		_visual.color = Color(0.7, 0.85, 1.0, 0.85)
	else:
		_visual.color = _initial_color


