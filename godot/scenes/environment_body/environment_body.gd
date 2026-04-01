extends StaticBody2D
## Tagged, indestructible, immovable environment hazard (acid pools, fire pits, etc.).
## Participates fully in the tag/rule engine via duck typing:
##   get_tags(), get_object_id(), add_tag(), remove_tag()
## but has NO take_damage/heal (indestructible), NO behaviors, NO sprites.
##
## Non-solid env bodies (solid=false) have collision_layer=0 so objects pass through.
## Their periodic timer fires ALL rules (no trigger_mode filter) since being inside
## the substance is semantically continuous contact.

const CL = preload("res://scripts/data/collision_layers.gd")

var env_id: String = ""
var _tag_manager: TagManager = null
var _solid: bool = true
var _initially_solid: bool = true
var _visual: ColorRect
var _initial_color: Color
var _field_area: Area2D
var _periodic_timer: Timer

const FIELD_MARGIN: float = 32.0


func init_env(id: String, init_tags: Array, size: Vector2, color: Color, solid: bool = true) -> void:
	env_id = id

	_tag_manager = TagManager.new()
	_tag_manager.name = "TagManager"
	add_child(_tag_manager)
	_tag_manager.init_tags(init_tags, id)
	_tag_manager.tags_changed.connect(_on_tags_changed)

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

	# Periodic timer for rule evaluation
	if FieldConfig.has_any_field_tag(tags):
		_start_periodic_timer()

	Log.info("EnvironmentBody: Initialized '%s' with tags %s, solid=%s" % [env_id, tags, solid])


var tags: Array[String]:
	get: return _tag_manager.tags if _tag_manager != null else []


func get_tags() -> Array[String]:
	return tags


func get_object_id() -> String:
	return env_id


func add_tag(tag: String, duration: float = 0.0) -> void:
	_tag_manager.add_tag(tag, duration)


func remove_tag(tag: String) -> void:
	_tag_manager.remove_tag(tag)


func _on_tags_changed(_updated_tags: Array[String]) -> void:
	_update_solidity()
	_update_visuals()
	# Start/stop periodic timer based on field tags
	if FieldConfig.has_any_field_tag(tags):
		if _periodic_timer == null:
			_start_periodic_timer()
	elif _periodic_timer != null:
		_periodic_timer.stop()
		_periodic_timer.queue_free()
		_periodic_timer = null


func _update_solidity() -> void:
	var should_be_solid: bool
	if "FROZEN" in tags:
		# Freezing always makes it solid (walkable frozen surface)
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
	if "FROZEN" in tags:
		_visual.color = Color(0.7, 0.85, 1.0, 0.85)
	else:
		_visual.color = _initial_color


func _start_periodic_timer() -> void:
	_periodic_timer = Timer.new()
	_periodic_timer.wait_time = FieldConfig.PERIODIC_INTERVAL
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
		if not TagColors.is_taggable(body):
			continue
		# Non-solid: no trigger_mode filter — ALL rules fire (CONTACT + FIELD).
		# Being inside the substance is semantically continuous contact.
		# Solid: FIELD-only, since CONTACT rules fire via body_entered.
		var filter: String = "FIELD" if _solid else ""
		CollisionResolver.resolve_collision(self, body, 0, filter)


