class_name StateDecay
extends Node

## Manages timed decay of states. Created by StateManager as a child node.

signal decay_expired(state: String)

var _timers: Dictionary = {}  # state -> Timer


func set_decay(state: String, duration: float) -> void:
	cancel_decay(state)
	var timer := Timer.new()
	timer.wait_time = duration
	timer.one_shot = true
	timer.timeout.connect(_on_expired.bind(state))
	add_child(timer)
	timer.start()
	_timers[state] = timer


func cancel_decay(state: String) -> void:
	if state in _timers and is_instance_valid(_timers[state]):
		_timers[state].stop()
		_timers[state].queue_free()
		_timers.erase(state)


func _on_expired(state: String) -> void:
	cancel_decay(state)
	decay_expired.emit(state)
