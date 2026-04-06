extends CanvasLayer

@onready var object_creation_panel: PanelContainer = %ObjectCreationPanel
@onready var objective_label: Label = %ObjectiveLabel
@onready var _action_hint: Label = %ActionHint

var _placement_active: bool = false
var _pause_menu: Control
var _game_over_panel: Control
var _game_over_title: Label
var _health_bar: ProgressBar
var _health_label: Label
var _damage_flash: ColorRect
var _post_process_label: Label


func _ready() -> void:
	layer = 10
	process_mode = Node.PROCESS_MODE_ALWAYS
	object_creation_panel.visible = false
	_update_action_hint()

	EventBus.placement_started.connect(_on_placement_started)
	EventBus.placement_ended.connect(_on_placement_ended)
	EventBus.debug_toggled.connect(_on_debug_toggled)
	EventBus.player_died.connect(_on_player_died)
	EventBus.player_damaged.connect(_on_player_damaged)
	EventBus.player_healed.connect(_on_player_healed)
	EventBus.post_process_changed.connect(_on_post_process_changed)

	_pause_menu = _build_overlay("Paused", Color(0, 0, 0, 0.5), [
		{"text": "Resume", "callback": _hide_pause_menu},
		{"text": "Main Menu", "callback": _on_main_menu_pressed},
	])
	_game_over_panel = _build_overlay("Game Over", Color(0.1, 0, 0, 0.6), [
		{"text": "Retry", "callback": _on_retry_pressed},
		{"text": "Main Menu", "callback": _on_main_menu_pressed},
	])
	_game_over_title = _game_over_panel.get_meta("title")

	_build_health_bar()
	_build_damage_flash()
	_build_post_process_label()


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
	root.set_meta("title", title)

	for btn_data in buttons:
		var btn := Button.new()
		btn.text = btn_data["text"]
		btn.custom_minimum_size = Vector2(200, 40)
		btn.pressed.connect(btn_data["callback"])
		vbox.add_child(btn)

	add_child(root)
	return root


func _build_health_bar() -> void:
	var container := HBoxContainer.new()
	container.set_anchors_preset(Control.PRESET_TOP_RIGHT)
	container.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	container.position = Vector2(-170, 16)
	container.add_theme_constant_override("separation", 6)

	_health_bar = ProgressBar.new()
	_health_bar.custom_minimum_size = Vector2(150, 24)
	_health_bar.max_value = 100
	_health_bar.value = 100
	_health_bar.show_percentage = false
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.2, 0.2, 0.2, 0.8)
	style.corner_radius_top_left = 4
	style.corner_radius_top_right = 4
	style.corner_radius_bottom_left = 4
	style.corner_radius_bottom_right = 4
	_health_bar.add_theme_stylebox_override("background", style)
	var fill := StyleBoxFlat.new()
	fill.bg_color = Color(0.3, 0.9, 0.3)
	fill.corner_radius_top_left = 4
	fill.corner_radius_top_right = 4
	fill.corner_radius_bottom_left = 4
	fill.corner_radius_bottom_right = 4
	_health_bar.add_theme_stylebox_override("fill", fill)
	container.add_child(_health_bar)

	_health_label = Label.new()
	_health_label.text = "100/100"
	_health_label.add_theme_font_size_override("font_size", 14)
	container.add_child(_health_label)

	add_child(container)


func _build_damage_flash() -> void:
	_damage_flash = ColorRect.new()
	_damage_flash.set_anchors_preset(Control.PRESET_FULL_RECT)
	_damage_flash.color = Color(1.0, 0.0, 0.0, 0.0)
	_damage_flash.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_damage_flash)


func _update_health_bar(current: int, maximum: int) -> void:
	Log.debug("HUD: Health bar updated %d/%d" % [current, maximum])
	_health_bar.max_value = maximum
	_health_bar.value = current
	_health_label.text = "%d/%d" % [current, maximum]
	var ratio: float = float(current) / float(maximum) if maximum > 0 else 0.0
	var fill: StyleBoxFlat = _health_bar.get_theme_stylebox("fill")
	if ratio > 0.5:
		fill.bg_color = Color(0.3, 0.9, 0.3)
	elif ratio > 0.25:
		fill.bg_color = Color(0.9, 0.9, 0.2)
	else:
		fill.bg_color = Color(0.9, 0.2, 0.2)


func _flash_damage_overlay() -> void:
	_damage_flash.color = Color(1.0, 0.0, 0.0, 0.25)
	var tween := create_tween()
	tween.tween_property(_damage_flash, "color:a", 0.0, 0.4)


func _on_player_damaged(amount: float, current: int, maximum: int) -> void:
	_update_health_bar(current, maximum)
	_flash_damage_overlay()


func _on_player_healed(amount: float, current: int, maximum: int) -> void:
	_update_health_bar(current, maximum)


func _show_pause_menu() -> void:
	Log.debug("HUD: Pause menu shown")
	_pause_menu.visible = true
	GameManager.pause_game()


func _hide_pause_menu() -> void:
	Log.debug("HUD: Pause menu hidden")
	_pause_menu.visible = false
	GameManager.resume_game()


func _on_main_menu_pressed() -> void:
	Log.info("HUD: Returning to main menu")
	_pause_menu.visible = false
	_game_over_panel.visible = false
	GameManager.return_to_menu()


func _on_retry_pressed() -> void:
	Log.info("HUD: Retry pressed")
	_game_over_panel.visible = false
	GameManager.restart_level()


func _on_placement_started() -> void:
	_placement_active = true
	_update_action_hint()


func _on_placement_ended() -> void:
	_placement_active = false
	_update_action_hint()


func _on_debug_toggled(enabled: bool) -> void:
	_post_process_label.visible = enabled


func _build_post_process_label() -> void:
	_post_process_label = Label.new()
	_post_process_label.text = "Post: OFF"
	_post_process_label.visible = GameManager.debug_mode
	_post_process_label.set_anchors_preset(Control.PRESET_TOP_LEFT)
	_post_process_label.position = Vector2(16, 40)
	_post_process_label.add_theme_font_size_override("font_size", 14)
	_post_process_label.add_theme_color_override("font_color", Color(0.7, 1.0, 0.7, 0.9))
	add_child(_post_process_label)


func _on_post_process_changed(shader_name: String) -> void:
	_post_process_label.text = "Post: %s" % shader_name


func _on_player_died() -> void:
	if _health_bar.value > 0:
		_game_over_title.text = "You fell!"
		Log.info("HUD: Game over — player fell")
	else:
		_game_over_title.text = "You died!"
		Log.info("HUD: Game over — player died (health depleted)")
	_game_over_panel.visible = true
	GameManager.pause_game()


func _update_action_hint() -> void:
	if _placement_active:
		_action_hint.text = "Click: Place  |  Esc: Cancel"
	else:
		_action_hint.text = "Tab: Create  |  E: Kick  |  F8: Shader  |  F9: Cycle  |  Esc: Menu  |  F3: Debug"
