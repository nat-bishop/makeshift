extends Node

enum GameState { MENU, PLAYING, PAUSED }

var current_state: GameState = GameState.MENU
var current_level: int = 0
var debug_mode: bool = false

const LEVEL_SCENES: Array[String] = [
	"res://scenes/levels/level_01.tscn",
	"res://scenes/levels/level_02.tscn",
	"res://scenes/levels/level_03.tscn",
]

const GAME_SCENE: String = "res://scenes/game/game.tscn"


func _ready() -> void:
	EventBus.level_completed.connect(_on_level_completed)


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("toggle_debug"):
		debug_mode = !debug_mode
		EventBus.debug_toggled.emit(debug_mode)
		Log.debug("GameManager: Debug mode %s" % ("ON" if debug_mode else "OFF"))


func change_scene_to_file(path: String) -> void:
	Log.info("GameManager: Changing scene to %s" % path)
	get_tree().change_scene_to_file(path)


func start_game(level: int = 0) -> void:
	Log.info("GameManager: Starting game at level %d" % level)
	current_level = level
	current_state = GameState.PLAYING
	if current_level < LEVEL_SCENES.size():
		change_scene_to_file(GAME_SCENE)
	else:
		Log.warn("GameManager: Level %d out of range, returning to menu" % level)
		return_to_menu()


func pause_game() -> void:
	Log.info("GameManager: Game paused")
	current_state = GameState.PAUSED
	get_tree().paused = true


func resume_game() -> void:
	Log.info("GameManager: Game resumed")
	current_state = GameState.PLAYING
	get_tree().paused = false


func return_to_menu() -> void:
	Log.info("GameManager: Returning to menu (from level %d)" % current_level)
	current_state = GameState.MENU
	current_level = 0
	change_scene_to_file("res://scenes/main_menu/main_menu.tscn")


func _on_level_completed(level_id: int) -> void:
	Log.info("GameManager: Level %d completed, advancing to %d" % [level_id, level_id + 1])
	current_level = level_id + 1
	if current_level < LEVEL_SCENES.size():
		# Reload the game scene, which will load the next level
		change_scene_to_file(GAME_SCENE)
	else:
		Log.info("GameManager: All levels completed!")
		return_to_menu()
