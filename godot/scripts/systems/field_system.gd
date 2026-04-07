extends Node
## V3 field system: reads has_field and field_range_cm from blueprint.
## Creates Area2D with blueprint-specified radius. Periodic tick (2s)
## routes through CollisionResolver for pairwise lookups.

var _owner: Node = null
var _field_area: Area2D = null
var _periodic_timer: Timer = null
var _range_px: float = 0.0


func init_field(owner: Node, bp: Dictionary) -> void:
	_owner = owner
	if not bp.get("has_field", false):
		return
	var range_cm: int = bp.get("field_range_cm", 100)
	_range_px = range_cm * 0.5  # conversion factor
	_create_area(_range_px)
	_start_periodic_timer()


func _create_area(radius: float) -> void:
	_field_area = Area2D.new()
	_field_area.name = "FieldArea"
	_field_area.collision_layer = 0
	_field_area.collision_mask = CollisionLayers.OBJECTS | CollisionLayers.PLAYER
	_field_area.monitoring = true

	var shape := CircleShape2D.new()
	shape.radius = radius
	var col := CollisionShape2D.new()
	col.shape = shape
	_field_area.add_child(col)
	_owner.add_child(_field_area)


func _start_periodic_timer() -> void:
	_periodic_timer = Timer.new()
	_periodic_timer.wait_time = 2.0
	_periodic_timer.one_shot = false
	_periodic_timer.timeout.connect(_on_periodic_tick)
	add_child(_periodic_timer)
	_periodic_timer.start()
	# First tick immediate
	call_deferred("_on_periodic_tick")


func _on_periodic_tick() -> void:
	if _field_area == null or _owner == null:
		return
	for body in _field_area.get_overlapping_bodies():
		if body == _owner:
			continue
		if not is_instance_valid(body):
			continue
		# Route through collision resolver for pairwise lookup
		CollisionResolver.resolve_and_notify(_owner, body, 0, "FIELD")


func on_states_changed(_states: Array) -> void:
	# Field doesn't change shape based on states in V3 —
	# re-evaluation happens via pairwise cache
	pass
