extends Node
## Timer-based state decay. When a state's timer expires, calls
## get_parent().remove_state(state) to strip it.

var _timers: Dictionary = {}


func set_decay(state: String, duration: float) -> void:
	cancel(state)
	var timer := Timer.new()
	timer.wait_time = duration
	timer.one_shot = true
	timer.timeout.connect(_on_expired.bind(state))
	_timers[state] = timer
	add_child(timer)
	timer.start()


func cancel(state: String) -> void:
	if state in _timers:
		var timer: Timer = _timers[state]
		timer.stop()
		remove_child(timer)
		timer.queue_free()
		_timers.erase(state)


func _on_expired(state: String) -> void:
	_timers.erase(state)
	var parent := get_parent()
	if parent != null and parent.has_method("remove_state"):
		parent.remove_state(state)
