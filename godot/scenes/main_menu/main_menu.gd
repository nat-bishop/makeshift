extends Control

@onready var new_game_button: Button = %NewGameButton
@onready var continue_button: Button = %ContinueButton
@onready var quit_button: Button = %QuitButton

var _level_select_container: VBoxContainer


func _ready() -> void:
	new_game_button.pressed.connect(_on_new_game_pressed)
	continue_button.pressed.connect(_on_continue_pressed)
	quit_button.pressed.connect(_on_quit_pressed)

	# Disable Continue if no saved session
	continue_button.disabled = Backend.session_id.is_empty()

	_build_level_select()


func _build_level_select() -> void:
	_level_select_container = VBoxContainer.new()
	_level_select_container.visible = false
	_level_select_container.add_theme_constant_override("separation", 8)

	# Insert after NewGameButton in the parent VBox
	var vbox: VBoxContainer = new_game_button.get_parent()
	vbox.add_child(_level_select_container)
	vbox.move_child(_level_select_container, new_game_button.get_index() + 1)

	for i in GameManager.LEVELS.size():
		var btn := Button.new()
		btn.text = GameManager.LEVELS[i]["name"]
		btn.custom_minimum_size = Vector2(0, 36)
		btn.pressed.connect(_on_level_selected.bind(i))
		_level_select_container.add_child(btn)


func _on_new_game_pressed() -> void:
	_level_select_container.visible = !_level_select_container.visible


func _on_level_selected(level: int) -> void:
	Log.info("MainMenu: Level %d selected" % level)
	new_game_button.disabled = true
	continue_button.disabled = true

	var result: Dictionary = await Backend.create_session()
	if result.get("error", false):
		Log.warn("MainMenu: Session creation failed, starting in offline mode")

	GameManager.start_game(level)


func _on_continue_pressed() -> void:
	if Backend.session_id.is_empty():
		return

	Log.info("MainMenu: Continue requested for session %s" % Backend.session_id)
	new_game_button.disabled = true
	continue_button.disabled = true

	var result: Dictionary = await Backend.restore_session(Backend.session_id)
	if result.get("error", false):
		Log.warn("MainMenu: Failed to restore session")
		new_game_button.disabled = false
		continue_button.disabled = false
		return

	GameManager.start_game(GameManager.current_level)


func _on_quit_pressed() -> void:
	get_tree().quit()
