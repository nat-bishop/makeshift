extends PanelContainer

var _game_object: RigidBody2D
var _name_label: Label
var _tag_container: HFlowContainer
var _last_durability: int = -1
var _last_tags: Array[String] = []


func init(game_obj: RigidBody2D) -> void:
	_game_object = game_obj
	visible = GameManager.debug_mode
	set_process(visible)

	# Semi-transparent background
	add_theme_stylebox_override("panel",
		InfoWidgets.make_stylebox(Color(0.05, 0.05, 0.08, 0.75), 4, 6, 4))

	# Position above object, centered
	var vd: Dictionary = game_obj.blueprint.get("visual_descriptor", {})
	var size_data: Dictionary = PhysicsComposer.get_size_data(vd.get("size_category", "medium"))
	position = Vector2(0, -(size_data["sprite"] / 2.0) - 8)
	resized.connect(func(): position.x = -size.x / 2.0)

	# Build layout
	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 3)
	add_child(vbox)

	_name_label = Label.new()
	_name_label.add_theme_font_size_override("font_size", 11)
	_name_label.add_theme_color_override("font_color", Color(1.0, 1.0, 1.0, 0.9))
	_name_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vbox.add_child(_name_label)

	_tag_container = HFlowContainer.new()
	_tag_container.add_theme_constant_override("h_separation", 3)
	_tag_container.add_theme_constant_override("v_separation", 2)
	vbox.add_child(_tag_container)

	# Behaviors are static — build once from blueprint
	var behaviors: Array = game_obj.blueprint.get("behaviors", [])
	if not behaviors.is_empty():
		for b in behaviors:
			vbox.add_child(InfoWidgets.create_behavior_label(b, 10))

	EventBus.debug_toggled.connect(_on_debug_toggled)

	if visible:
		_refresh()


func _process(_delta: float) -> void:
	var dur: int = _game_object.current_durability
	var tags: Array[String] = _game_object.tags
	if dur != _last_durability or tags != _last_tags:
		_refresh()


func _refresh() -> void:
	_last_durability = _game_object.current_durability
	_last_tags = _game_object.tags.duplicate()

	# Name + durability
	var bp: Dictionary = _game_object.blueprint
	_name_label.text = "%s [%d/%d]" % [
		bp.get("name", "?"), _last_durability, bp.get("starting_durability", 150)
	]

	# Rebuild tag badges
	for child in _tag_container.get_children():
		child.queue_free()
	for tag in _last_tags:
		_tag_container.add_child(InfoWidgets.create_tag_badge(tag, 10))


func _on_debug_toggled(on: bool) -> void:
	visible = on
	set_process(on)
	if on:
		_last_durability = -1
		_last_tags = []


func _exit_tree() -> void:
	if EventBus.debug_toggled.is_connected(_on_debug_toggled):
		EventBus.debug_toggled.disconnect(_on_debug_toggled)
