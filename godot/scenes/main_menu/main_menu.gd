extends Control

@onready var new_game_button: Button = %NewGameButton
@onready var continue_button: Button = %ContinueButton
@onready var quit_button: Button = %QuitButton


func _ready() -> void:
	new_game_button.pressed.connect(_on_new_game_pressed)
	continue_button.pressed.connect(_on_continue_pressed)
	quit_button.pressed.connect(_on_quit_pressed)

	# Disable Continue if no saved session
	continue_button.disabled = Backend.session_id.is_empty()


func _on_new_game_pressed() -> void:
	new_game_button.disabled = true
	continue_button.disabled = true

	var result: Dictionary = await Backend.create_session()
	if result.get("error", false):
		Log.warn("MainMenu: Session creation failed, starting in offline mode")

	GameManager.start_game(0)


func _on_continue_pressed() -> void:
	if Backend.session_id.is_empty():
		return

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
