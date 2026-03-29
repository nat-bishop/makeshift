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
var tags: Array[String] = []
var _solid: bool = true
var _initially_solid: bool = true
var _visual: ColorRect
var _initial_color: Color
var _field_area: Area2D
var _periodic_timer: Timer
var _decay_timers: Dictionary = {}  # tag name -> Timer

const FIELD_MARGIN: float = 32.0
const PERIODIC_INTERVAL: float = 2.0


func init_env(id: String, init_tags: Array, size: Vector2, color: Color, solid: bool = true) -> void:
	env_id = id
	tags.clear()
	for tag in init_tags:
		tags.append(str(tag))
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


func get_tags() -> Array[String]:
	return tags


func get_object_id() -> String:
	return env_id


func add_tag(tag: String, duration: float = 0.0) -> void:
	var is_new: bool = tag not in tags
	if is_new:
		tags.append(tag)
		Log.debug("EnvironmentBody: '%s' +tag %s%s" % [env_id, tag, " (%.1fs)" % duration if duration > 0.0 else ""])
		_on_tags_changed()
	if duration > 0.0:
		_cancel_decay_timer(tag)
		var timer := Timer.new()
		timer.wait_time = duration
		timer.one_shot = true
		timer.timeout.connect(_on_decay_timer_expired.bind(tag))
		add_child(timer)
		timer.start()
		_decay_timers[tag] = timer


func remove_tag(tag: String) -> void:
	_cancel_decay_timer(tag)
	if tag not in tags:
		return
	Log.debug("EnvironmentBody: '%s' -tag %s" % [env_id, tag])
	tags.erase(tag)
	_on_tags_changed()


func _on_tags_changed() -> void:
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
	Log.debug("EnvironmentBody: '%s' tags now: %s" % [env_id, tags])


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
	_periodic_timer.wait_time = PERIODIC_INTERVAL
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
		if not body.has_method("get_tags") and not body.has_method("get_effective_tags"):
			continue
		# Non-solid: no trigger_mode filter — ALL rules fire (CONTACT + FIELD).
		# Being inside the substance is semantically continuous contact.
		# Solid: FIELD-only, since CONTACT rules fire via body_entered.
		var filter: String = "FIELD" if _solid else ""
		CollisionResolver.resolve_collision(self, body, 0, filter)


func _on_decay_timer_expired(tag: String) -> void:
	Log.debug("EnvironmentBody: Decay timer expired for tag '%s' on '%s'" % [tag, env_id])
	remove_tag(tag)


func _cancel_decay_timer(tag: String) -> void:
	if tag in _decay_timers and is_instance_valid(_decay_timers[tag]):
		_decay_timers[tag].queue_free()
		_decay_timers.erase(tag)
