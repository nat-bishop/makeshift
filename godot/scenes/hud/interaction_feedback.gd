extends Node2D
## Spawns floating labels at world positions when interactions trigger.
## Added to the world (not HUD layer) so labels follow world position.

const MAX_ACTIVE := 5
const FLOAT_DISTANCE := 40.0
const FLOAT_DURATION := 2.0
const FONT_SIZE := 14
const OUTLINE_SIZE := 3
const OUTLINE_COLOR := Color.BLACK

var _active_labels: Array[Label] = []


func _ready() -> void:
	EventBus.interaction_triggered.connect(_on_interaction_triggered)


func _on_interaction_triggered(
	source_name: String,
	source_tags: Array,
	target_name: String,
	target_tags: Array,
	effect_message: String,
	world_pos: Vector2
) -> void:
	var source_tag_str := _format_tag(source_tags)
	var target_tag_str := _format_tag(target_tags)
	var text := "%s %s + %s %s -> %s" % [
		source_name, source_tag_str, target_name, target_tag_str, effect_message
	]
	_spawn_label(text, world_pos)


func _format_tag(tags: Array) -> String:
	if tags.is_empty():
		return ""
	# Show the first relevant tag
	return "[%s]" % str(tags[0])


func _spawn_label(text: String, world_pos: Vector2) -> void:
	# Remove oldest if at capacity
	while _active_labels.size() >= MAX_ACTIVE:
		var oldest = _active_labels.pop_front()
		if is_instance_valid(oldest):
			oldest.queue_free()

	var label := Label.new()
	label.text = text
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.add_theme_font_size_override("font_size", FONT_SIZE)
	label.add_theme_color_override("font_color", Color.WHITE)
	label.add_theme_color_override("font_outline_color", OUTLINE_COLOR)
	label.add_theme_constant_override("outline_size", OUTLINE_SIZE)

	# Position centered on world_pos
	label.position = world_pos
	label.position.x -= 150  # rough centering
	label.custom_minimum_size.x = 300

	add_child(label)
	_active_labels.append(label)

	# Tween: float up and fade out
	var tween := create_tween()
	tween.set_parallel(true)
	tween.tween_property(label, "position:y", world_pos.y - FLOAT_DISTANCE, FLOAT_DURATION)
	tween.tween_property(label, "modulate:a", 0.0, FLOAT_DURATION)
	tween.set_parallel(false)
	tween.tween_callback(_remove_label.bind(label))


func _remove_label(label: Label) -> void:
	if is_instance_valid(label):
		_active_labels.erase(label)
		label.queue_free()
