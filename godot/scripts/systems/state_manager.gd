class_name StateManager extends Node

signal state_added(state: String)
signal state_removed(state: String)
signal states_changed(states: Array)

var states: Array = []
var _decay: Node = null
var _owner_name: String = ""


func _ready() -> void:
	var decay_script = preload("res://scripts/systems/state_decay.gd")
	_decay = decay_script.new()
	_decay.name = "StateDecay"
	add_child(_decay)


func init_states(initial_states: Array, owner_name: String) -> void:
	_owner_name = owner_name
	for s in initial_states:
		if s not in states:
			states.append(str(s))


func add_state(state: String, duration: float = 0.0) -> void:
	# Auto-remove contradictions
	var contradictions: Array = StateContradictions.get_contradictions(state)
	for c in contradictions:
		if c in states:
			remove_state(c)

	if state not in states:
		states.append(state)
		if duration > 0.0 and _decay != null:
			_decay.set_decay(state, duration)
		state_added.emit(state)
		states_changed.emit(states)
		Log.debug("StateManager: '%s' +state '%s' (total=%d)" % [_owner_name, state, states.size()])


func remove_state(state: String) -> void:
	if state in states:
		states.erase(state)
		if _decay != null:
			_decay.cancel(state)
		state_removed.emit(state)
		states_changed.emit(states)
		Log.debug("StateManager: '%s' -state '%s' (total=%d)" % [_owner_name, state, states.size()])


func has_state(state: String) -> bool:
	return state in states


func get_states() -> Array:
	return states
