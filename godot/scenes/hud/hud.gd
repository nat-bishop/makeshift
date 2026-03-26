extends CanvasLayer

@onready var object_creation_panel: PanelContainer = %ObjectCreationPanel
@onready var objective_label: Label = %ObjectiveLabel
@onready var _action_hint: Label = %ActionHint

var _placement_active: bool = false
var _pause_menu: Control
var _game_over_panel: Control


func _ready() -> void:
	layer = 10
	process_mode = Node.PROCESS_MODE_ALWAYS
	object_creation_panel.visible = false
	_action_hint.visible = false

	EventBus.placement_started.connect(_on_placement_started)
	EventBus.placement_ended.connect(_on_placement_ended)
	EventBus.debug_toggled.connect(_on_debug_toggled)
	EventBus.player_died.connect(_on_player_died)

	_pause_menu = _build_overlay("Paused", Color(0, 0, 0, 0.5), [
		{"text": "Resume", "callback": _hide_pause_menu},
		{"text": "Main Menu", "callback": _on_main_menu_pressed},
	])
	_game_over_panel = _build_overlay("You fell!", Color(0.1, 0, 0, 0.6), [
		{"text": "Retry", "callback": _on_retry_pressed},
		{"text": "Main Menu", "callback": _on_main_menu_pressed},
	])


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		if _placement_active:
			return  # game.gd handles Escape during placement
		if _game_over_panel.visible:
			get_viewport().set_input_as_handled()
			return
		if object_creation_panel.visible:
			object_creation_panel.visible = false
			GameManager.resume_game()
			get_viewport().set_input_as_handled()
			return
		if _pause_menu.visible:
			_hide_pause_menu()
			get_viewport().set_input_as_handled()
			return
		_show_pause_menu()
		get_viewport().set_input_as_handled()
		return

	if event.is_action_pressed("create_object"):
		if _game_over_panel.visible or _pause_menu.visible:
			get_viewport().set_input_as_handled()
			return
		if _placement_active:
			return
		object_creation_panel.visible = !object_creation_panel.visible
		Log.debug("HUD: Creation panel %s" % ("opened" if object_creation_panel.visible else "closed"))
		if object_creation_panel.visible:
			object_creation_panel.focus_input()
			GameManager.pause_game()
		else:
			GameManager.resume_game()
		get_viewport().set_input_as_handled()


func set_objective(text: String) -> void:
	objective_label.text = text


func _build_overlay(title_text: String, dim_color: Color, buttons: Array) -> Control:
	var root := Control.new()
	root.visible = false
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_STOP

	var dim := ColorRect.new()
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	dim.color = dim_color
	root.add_child(dim)

	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.add_child(center)

	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 16)
	center.add_child(vbox)

	var title := Label.new()
	title.text = title_text
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 32)
	vbox.add_child(title)

	for btn_data in buttons:
		var btn := Button.new()
		btn.text = btn_data["text"]
		btn.custom_minimum_size = Vector2(200, 40)
		btn.pressed.connect(btn_data["callback"])
		vbox.add_child(btn)

	add_child(root)
	return root


func _show_pause_menu() -> void:
	_pause_menu.visible = true
	GameManager.pause_game()


func _hide_pause_menu() -> void:
	_pause_menu.visible = false
	GameManager.resume_game()


func _on_main_menu_pressed() -> void:
	_pause_menu.visible = false
	_game_over_panel.visible = false
	GameManager.return_to_menu()


func _on_retry_pressed() -> void:
	_game_over_panel.visible = false
	GameManager.restart_level()


func _on_placement_started() -> void:
	_placement_active = true
	_update_action_hint()


func _on_placement_ended() -> void:
	_placement_active = false
	_update_action_hint()


func _on_debug_toggled(enabled: bool) -> void:
	_action_hint.visible = enabled
	if enabled:
		_update_action_hint()


func _on_player_died() -> void:
	_game_over_panel.visible = true
	GameManager.pause_game()


func _update_action_hint() -> void:
	if _placement_active:
		_action_hint.text = "Click: Place  |  Esc: Cancel"
	else:
		_action_hint.text = "Tab: Create  |  E: Kick  |  Esc: Menu  |  F3: Debug"
