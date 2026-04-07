extends PanelContainer
## V3 debug overlay: shows name, HP/armor, states, affordance, physics.

var _game_object: Node
var _name_label: Label
var _state_container: HFlowContainer
var _last_hp: int = -1
var _last_states: Array = []
var _above_offset: float = 8.0


func init(game_obj: Node) -> void:
	_game_object = game_obj
	visible = GameManager.debug_mode
	set_process(visible)

	add_theme_stylebox_override("panel",
		InfoWidgets.make_stylebox(Color(0.05, 0.05, 0.08, 0.75), 3, 4, 3))

	# Position above sprite
	var phys: Dictionary = game_obj.blueprint.get("physics", {})
	var height_cm: int = phys.get("height_cm", 30)
	var size_cat: String = PhysicsComposer.size_from_height(height_cm)
	var size_data: Dictionary = PhysicsComposer.get_size_data(size_cat)
	_above_offset = size_data["sprite"] / 2.0 + 4

	resized.connect(_reposition)

	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 2)
	add_child(vbox)

	_name_label = Label.new()
	_name_label.add_theme_font_size_override("font_size", 10)
	_name_label.add_theme_color_override("font_color", Color(1.0, 1.0, 1.0, 0.9))
	_name_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vbox.add_child(_name_label)

	_state_container = HFlowContainer.new()
	_state_container.add_theme_constant_override("h_separation", 2)
	_state_container.add_theme_constant_override("v_separation", 1)
	vbox.add_child(_state_container)

	EventBus.debug_toggled.connect(_on_debug_toggled)

	if visible:
		_refresh()


func _reposition() -> void:
	position.x = -size.x / 2.0
	position.y = -_above_offset - size.y


func _process(_delta: float) -> void:
	var hp: int = _game_object.current_hp if "current_hp" in _game_object else 0
	var states: Array = _game_object.get_states() if _game_object.has_method("get_states") else []
	if hp != _last_hp or states != _last_states:
		_refresh()


func _refresh() -> void:
	_last_hp = _game_object.current_hp if "current_hp" in _game_object else 0
	_last_states = _game_object.get_states().duplicate() if _game_object.has_method("get_states") else []

	var bp: Dictionary = _game_object.blueprint
	var phys: Dictionary = bp.get("physics", {})
	var dest: Dictionary = bp.get("destructibility", {})
	var aff_names := ["carry", "mount", "climb", "none"]
	var aff: int = bp.get("affordance", 3)
	var aff_str: String = aff_names[aff] if aff >= 0 and aff < aff_names.size() else "?"

	_name_label.text = "%s [%d/%d] arm=%d %s" % [
		bp.get("name", "?"), _last_hp, dest.get("hp", 50), dest.get("armor", 0), aff_str
	]

	for child in _state_container.get_children():
		child.queue_free()
	for state in _last_states:
		_state_container.add_child(InfoWidgets.create_state_badge(state, 9))


func _on_debug_toggled(on: bool) -> void:
	visible = on
	set_process(on)
	if on:
		_last_hp = -1
		_last_states = []


func _exit_tree() -> void:
	if EventBus.debug_toggled.is_connected(_on_debug_toggled):
		EventBus.debug_toggled.disconnect(_on_debug_toggled)
