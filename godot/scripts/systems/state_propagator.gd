extends Node

## Tick-based state propagation: when an object has active states, periodically
## check nearby bodies and spread states to susceptible neighbors.
## Replaces both ObjectField (has_field area effects) and cascade (instant chain reactions).
## Spread rate is controlled by TICK_INTERVAL — fire spreads as a visible wave.

const TICK_INTERVAL: float = 2.0
const BASE_RADIUS: float = 64.0
const DEFAULT_PROPAGATION_DURATION: float = 10.0

var _owner: Node2D
var _propagation_area: Area2D
var _tick_timer: Timer
var _ticking: bool = false


func init_propagator(owner: Node2D, height_cm: int) -> void:
	_owner = owner
	_create_area(height_cm)
	_create_timer()

	# Connect to state signals for activation
	if owner.has_node("StateManager"):
		var sm: Node = owner.get_node("StateManager")
		sm.state_added.connect(_on_state_added)
		sm.states_changed.connect(_on_states_changed)


func _create_area(height_cm: int) -> void:
	_propagation_area = Area2D.new()
	_propagation_area.name = "PropagationArea"
	_propagation_area.collision_layer = 0
	var cl_script = preload("res://scripts/data/collision_layers.gd")
	_propagation_area.collision_mask = cl_script.OBJECTS | cl_script.PLAYER
	_propagation_area.monitoring = true
	_propagation_area.monitorable = false

	var shape_node := CollisionShape2D.new()
	var circle := CircleShape2D.new()
	# Scale radius with object height
	var scale: float = PhysicsComposer.scale_from_height(height_cm)
	circle.radius = BASE_RADIUS * scale
	shape_node.shape = circle
	_propagation_area.add_child(shape_node)
	_owner.add_child(_propagation_area)


func _create_timer() -> void:
	_tick_timer = Timer.new()
	_tick_timer.wait_time = TICK_INTERVAL
	_tick_timer.one_shot = false
	_tick_timer.timeout.connect(_on_tick)
	add_child(_tick_timer)


func _on_state_added(_state_name: String) -> void:
	if not _ticking:
		_ticking = true
		_tick_timer.start()
		# Immediate first tick so effects aren't delayed
		_on_tick()


func _on_states_changed(states: Array) -> void:
	if states.is_empty() and _ticking:
		_ticking = false
		_tick_timer.stop()


func _on_tick() -> void:
	if _propagation_area == null or not is_instance_valid(_owner):
		return

	var my_states: Array = []
	if _owner.has_method("get_states"):
		my_states = _owner.get_states()
	if my_states.is_empty():
		_ticking = false
		_tick_timer.stop()
		return

	for body in _propagation_area.get_overlapping_bodies():
		if body == _owner or not is_instance_valid(body):
			continue
		if not body.has_method("get_susceptible_states"):
			continue

		var susceptible: Array = body.get_susceptible_states()
		for state_id in my_states:
			if state_id in susceptible:
				WorldMutations.apply_add_state(
					body, StateContradictions.STATE_NAMES[state_id], DEFAULT_PROPAGATION_DURATION
				)
