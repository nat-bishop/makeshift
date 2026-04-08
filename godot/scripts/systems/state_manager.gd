class_name StateManager
extends Node

## Manages V3 interaction states (on_fire, frozen, wet, etc).
## Replaces V2 TagManager + TagDecay.
## Objects are born stateless. States are applied by interactions.

signal state_added(state: String)
signal state_removed(state: String)
signal states_changed(states: Array)

var _states: Array = []
var _decay: StateDecay = null
var _owner_name: String = "?"


func init_states(owner_name: String) -> void:
	_owner_name = owner_name
	_decay = StateDecay.new()
	_decay.name = "StateDecay"
	_decay.decay_expired.connect(_on_expired)
	add_child(_decay)


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
		_decay.set_decay(state, duration)


func remove_state(state: String) -> void:
	_decay.cancel_decay(state)
	if state not in _states:
		return
	_states.erase(state)
	state_removed.emit(state)
	states_changed.emit(_states)


func has_state(state: String) -> bool:
	return state in _states


func get_states() -> Array:
	return _states


func _on_expired(state: String) -> void:
	remove_state(state)
