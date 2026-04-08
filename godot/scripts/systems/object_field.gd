extends Node

## V3 field system: simplified replacement for V2 TagField.
## Field range comes from the blueprint (LLM-generated), not tag config.
## Periodic 2s tick resolves collisions via pairwise cache.

const CL = preload("res://scripts/data/collision_layers.gd")
const PERIODIC_INTERVAL: float = 2.0

var _owner_body: Node2D
var _field_area: Area2D
var _periodic_timer: Timer
var _range_px: float = 0.0


func init_field(owner: Node2D, range_cm: float) -> void:
	_owner_body = owner
	_range_px = range_cm  # 1cm = 1px (world scale)
	_create_area(_range_px)
	_start_periodic_timer()


func _create_area(radius: float) -> void:
	_field_area = Area2D.new()
	_field_area.name = "FieldArea"
	_field_area.collision_layer = 0
	_field_area.collision_mask = CL.OBJECTS | CL.PLAYER
	_field_area.monitoring = true
	_field_area.monitorable = false

	var shape_node := CollisionShape2D.new()
	var circle := CircleShape2D.new()
	circle.radius = radius
	shape_node.shape = circle
	_field_area.add_child(shape_node)
	_owner_body.add_child(_field_area)


func _start_periodic_timer() -> void:
	_periodic_timer = Timer.new()
	_periodic_timer.wait_time = PERIODIC_INTERVAL
	_periodic_timer.one_shot = false
	_periodic_timer.timeout.connect(_on_tick)
	add_child(_periodic_timer)
	call_deferred("_on_tick")
	_periodic_timer.start()


func _on_tick() -> void:
	if _field_area == null or not is_instance_valid(_owner_body):
		return
	for body in _field_area.get_overlapping_bodies():
		if body == _owner_body or not is_instance_valid(body):
			continue
		CollisionResolver.resolve_collision(_owner_body, body, 0, {}, true)
