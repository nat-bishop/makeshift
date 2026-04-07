extends StaticBody2D
## V3 Environment Body — indestructible named objects in the pairwise cache.
## Participates in V3 collision system via duck typing:
##   get_tags()/get_states(), get_object_id(), get_blueprint(), add_state(), remove_state()
## Indestructible, no sprites. Pairwise interactions via name-based cache lookup.

const CL = preload("res://scripts/data/collision_layers.gd")

var env_id: String = ""
var blueprint: Dictionary = {}
var _state_manager: StateManager = null
var _solid: bool = true
var _initially_solid: bool = true
var _visual: ColorRect
var _initial_color: Color
var _field_area: Area2D
var _periodic_timer: Timer
var _states: Array = []

const FIELD_MARGIN: float = 32.0


func init_env_v3(bp: Dictionary, size: Vector2, color: Color, solid: bool = true) -> void:
	blueprint = bp
	env_id = bp.get("id", "")

	_state_manager = StateManager.new()
	_state_manager.name = "StateManager"
	add_child(_state_manager)
	_state_manager.init_states(bp.get("states", []), bp.get("name", env_id))
	_state_manager.states_changed.connect(_on_states_changed)
	_states = _state_manager.states

	_solid = solid
	_initially_solid = solid
	_initial_color = color

	# Collision
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

	# Detection Area2D — extends beyond physical shape for field interactions
	if bp.get("has_field", false):
		var field_range: int = bp.get("field_range_cm", 100)
		var range_px: float = float(field_range) * 0.5
		_create_field_area(size, range_px)
		_start_periodic_timer()

	add_to_group("game_objects")
	Log.info("EnvironmentBody: V3 init '%s' (id=%s), solid=%s" % [bp.get("name", "?"), env_id, solid])


func _create_field_area(body_size: Vector2, range_px: float) -> void:
	_field_area = Area2D.new()
	_field_area.name = "FieldArea"
	_field_area.collision_layer = 0
	_field_area.collision_mask = CL.OBJECTS | CL.PLAYER
	_field_area.monitoring = true
	_field_area.monitorable = false
	var area_shape := CollisionShape2D.new()
	var field_rect := RectangleShape2D.new()
	var margin: float = maxf(range_px, FIELD_MARGIN)
	field_rect.size = body_size + Vector2(margin * 2, margin * 2)
	area_shape.shape = field_rect
	_field_area.add_child(area_shape)
	add_child(_field_area)


# V3: states replace tags
func get_states() -> Array:
	return _states


func get_tags() -> Array:
	return _states


var tags: Array:
	get: return _states


func get_object_id() -> String:
	return env_id


func get_blueprint() -> Dictionary:
	return blueprint


func add_state(state: String, duration: float = 0.0) -> void:
	_state_manager.add_state(state, duration)


func remove_state(state: String) -> void:
	_state_manager.remove_state(state)


# Backward compat
func add_tag(tag: String, duration: float = 0.0) -> void:
	add_state(tag, duration)


func remove_tag(tag: String) -> void:
	remove_state(tag)


func _on_states_changed(updated_states: Array) -> void:
	_states = updated_states
	_update_solidity()
	_update_visuals()


func _update_solidity() -> void:
	var should_be_solid: bool
	if "frozen" in _states:
		should_be_solid = true
	else:
		should_be_solid = _initially_solid
	if should_be_solid != _solid:
		_solid = should_be_solid
		collision_layer = CL.OBJECTS if _solid else 0
		Log.debug("EnvironmentBody: '%s' solidity changed to %s" % [env_id, _solid])


func _update_visuals() -> void:
	if _visual == null:
		return
	if "frozen" in _states:
		_visual.color = Color(0.7, 0.85, 1.0, 0.85)
	else:
		_visual.color = _initial_color


func _start_periodic_timer() -> void:
	_periodic_timer = Timer.new()
	_periodic_timer.wait_time = 2.0
	_periodic_timer.one_shot = false
	_periodic_timer.timeout.connect(_on_periodic_tick)
	add_child(_periodic_timer)
	call_deferred("_on_periodic_tick")
	_periodic_timer.start()


func _on_periodic_tick() -> void:
	if _field_area == null:
		return
	for body in _field_area.get_overlapping_bodies():
		if body == self or not is_instance_valid(body):
			continue
		if not (body.has_method("get_states") or body.has_method("get_tags")):
			continue
		var filter: String = "FIELD" if _solid else ""
		CollisionResolver.resolve_and_notify(self, body, 0, filter)
