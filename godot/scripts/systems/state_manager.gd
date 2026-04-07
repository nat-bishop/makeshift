class_name StateManager
extends Node

## Manages V3 interaction states (on_fire, frozen, wet, etc).
## Replaces V2 TagManager + TagDecay.
## Objects are born stateless. States are applied by interactions.

signal state_added(state: String)
signal state_removed(state: String)
signal states_changed(states: Array)

var _states: Array = []
var _decay_timers: Dictionary = {}  # state -> Timer
var _owner_name: String = "?"


func init_states(owner_name: String) -> void:
	_owner_name = owner_name


func add_state(state: String, duration: float = 0.0) -> void:
	# Remove contradictions (directed)
	for contra in StateContradictions.get_removals(state):
		if contra in _states:
			remove_state(contra)
	var is_new: bool = state not in _states
	if is_new:
		_states.append(state)
		state_added.emit(state)
		states_changed.emit(_states)
	if duration > 0.0:
		_set_decay(state, duration)


func remove_state(state: String) -> void:
	_cancel_decay(state)
	if state not in _states:
		return
	_states.erase(state)
	state_removed.emit(state)
	states_changed.emit(_states)


func has_state(state: String) -> bool:
	return state in _states


func get_states() -> Array:
	return _states


func _set_decay(state: String, duration: float) -> void:
	_cancel_decay(state)
	var timer := Timer.new()
	timer.wait_time = duration
	timer.one_shot = true
	timer.timeout.connect(_on_expired.bind(state))
	add_child(timer)
	timer.start()
	_decay_timers[state] = timer


func _cancel_decay(state: String) -> void:
	if state in _decay_timers and is_instance_valid(_decay_timers[state]):
		_decay_timers[state].stop()
		_decay_timers[state].queue_free()
		_decay_timers.erase(state)


func _on_expired(state: String) -> void:
	_cancel_decay(state)
	remove_state(state)
