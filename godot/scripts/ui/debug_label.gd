extends Label

var _game_object: RigidBody2D
var _last_durability: int = -1
var _last_tag_count: int = -1


func init(game_obj: RigidBody2D) -> void:
	_game_object = game_obj
	visible = GameManager.debug_mode
	set_process(visible)

	var vd: Dictionary = game_obj.blueprint.get("visual_descriptor", {})
	var size_data: Dictionary = PhysicsComposer.get_size_data(vd.get("size_category", "medium"))
	position = Vector2(0, -(size_data["sprite"] / 2.0) - 8)

	horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	add_theme_font_size_override("font_size", 11)
	add_theme_color_override("font_color", Color(1.0, 1.0, 1.0, 0.9))
	add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.8))
	add_theme_constant_override("shadow_offset_x", 1)
	add_theme_constant_override("shadow_offset_y", 1)

	EventBus.debug_toggled.connect(_on_debug_toggled)

	if visible:
		_update_text()


func _process(_delta: float) -> void:
	var dur: int = _game_object.current_durability
	var tag_count: int = _game_object.tags.size()
	if dur != _last_durability or tag_count != _last_tag_count:
		_update_text()


func _update_text() -> void:
	_last_durability = _game_object.current_durability
	_last_tag_count = _game_object.tags.size()

	var bp: Dictionary = _game_object.blueprint
	var name_str: String = bp.get("name", "?")
	var dur: String = "%d/%d" % [_last_durability, bp.get("starting_durability", 150)]
	var tags_str: String = " ".join(_game_object.tags)

	var lines: PackedStringArray = ["%s [%s]" % [name_str, dur], tags_str]

	for b in bp.get("behaviors", []):
		lines.append("%s > %s" % [b.get("trigger", "?"), b.get("action", "?")])

	text = "\n".join(lines)


func _on_debug_toggled(on: bool) -> void:
	visible = on
	set_process(on)
	if on:
		_last_durability = -1
		_last_tag_count = -1


func _exit_tree() -> void:
	if EventBus.debug_toggled.is_connected(_on_debug_toggled):
		EventBus.debug_toggled.disconnect(_on_debug_toggled)
