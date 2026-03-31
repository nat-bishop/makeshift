class_name TagDecay
extends Node

## Manages temporary tag duration timers for any taggable object.
## Parent must implement remove_tag(tag: String).
## Used by GameObject and EnvironmentBody to avoid duplicated decay logic.

var _timers: Dictionary = {}  # tag name -> Timer


func set_decay(tag: String, duration: float) -> void:
	cancel(tag)
	var timer := Timer.new()
	timer.wait_time = duration
	timer.one_shot = true
	timer.timeout.connect(_on_expired.bind(tag))
	add_child(timer)
	timer.start()
	_timers[tag] = timer


func cancel(tag: String) -> void:
	if tag in _timers and is_instance_valid(_timers[tag]):
		_timers[tag].queue_free()
		_timers.erase(tag)


func _on_expired(tag: String) -> void:
	cancel(tag)
	get_parent().remove_tag(tag)
