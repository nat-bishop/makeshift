extends Node2D
## Spawns floating damage/heal numbers at world positions.
## Listens to effect_applied signal for element-colored feedback.

const MAX_ACTIVE := 8
const FLOAT_DISTANCE := 50.0
const FLOAT_DURATION := 1.5
const SOLID_DURATION := 0.75
const FONT_SIZE := 18
const OUTLINE_SIZE := 4
const OUTLINE_COLOR := Color.BLACK
const HEAL_COLOR := Color(0.3, 1.0, 0.3)
const X_SCATTER := 20.0

var _active_labels: Array[Label] = []


func _ready() -> void:
	EventBus.effect_applied.connect(_on_effect_applied)


func _on_effect_applied(
	effect_type: String,
	amount: float,
	element_color: Color,
	world_pos: Vector2
) -> void:
	var text: String
	var color: Color
	if effect_type == "HEAL":
		text = "+%d" % int(amount)
		color = HEAL_COLOR
	else:
		text = "-%d" % int(amount)
		color = element_color
	_spawn_label(text, color, world_pos)


func _spawn_label(text: String, color: Color, world_pos: Vector2) -> void:
	while _active_labels.size() >= MAX_ACTIVE:
		var oldest = _active_labels.pop_front()
		if is_instance_valid(oldest):
			oldest.queue_free()

	var label := Label.new()
	label.text = text
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.add_theme_font_size_override("font_size", FONT_SIZE)
	label.add_theme_color_override("font_color", color)
	label.add_theme_color_override("font_outline_color", OUTLINE_COLOR)
	label.add_theme_constant_override("outline_size", OUTLINE_SIZE)

	# Random x offset to prevent stacking
	var x_offset: float = randf_range(-X_SCATTER, X_SCATTER)
	label.position = Vector2(world_pos.x - 30 + x_offset, world_pos.y)
	label.custom_minimum_size.x = 60

	add_child(label)
	_active_labels.append(label)

	# Float up, stay solid then fade
	var tween := create_tween()
	tween.tween_property(label, "position:y", world_pos.y - FLOAT_DISTANCE, FLOAT_DURATION)
	tween.tween_interval(SOLID_DURATION)
	tween.tween_property(label, "modulate:a", 0.0, FLOAT_DURATION - SOLID_DURATION)
	tween.tween_callback(_remove_label.bind(label))


func _remove_label(label: Label) -> void:
	if is_instance_valid(label):
		_active_labels.erase(label)
		label.queue_free()
