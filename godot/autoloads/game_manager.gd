extends Node

enum GameState { MENU, PLAYING, PAUSED }

var current_state: GameState = GameState.MENU
var current_level: int = 0

const LEVEL_SCENES: Array[String] = [
	"res://scenes/levels/level_01.tscn",
	"res://scenes/levels/level_02.tscn",
	"res://scenes/levels/level_03.tscn",
]

const GAME_SCENE: String = "res://scenes/game/game.tscn"


func _ready() -> void:
	EventBus.level_completed.connect(_on_level_completed)


func change_scene_to_file(path: String) -> void:
	get_tree().change_scene_to_file(path)


func start_game(level: int = 0) -> void:
	current_level = level
	current_state = GameState.PLAYING
	if current_level < LEVEL_SCENES.size():
		change_scene_to_file(GAME_SCENE)
	else:
		return_to_menu()


func pause_game() -> void:
	current_state = GameState.PAUSED
	get_tree().paused = true


func resume_game() -> void:
	current_state = GameState.PLAYING
	get_tree().paused = false


func return_to_menu() -> void:
	current_state = GameState.MENU
	current_level = 0
	change_scene_to_file("res://scenes/main_menu/main_menu.tscn")


func _on_level_completed(level_id: int) -> void:
	current_level = level_id + 1
	if current_level < LEVEL_SCENES.size():
		# Reload the game scene, which will load the next level
		change_scene_to_file(GAME_SCENE)
	else:
		return_to_menu()
