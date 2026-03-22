extends Node2D

@onready var world: Node2D = $World
@onready var hud: CanvasLayer = $HUD
@onready var player: CharacterBody2D = $Player

var _current_level_scene: Node2D = null


func _ready() -> void:
	EventBus.level_completed.connect(_on_level_completed)
	EventBus.object_created.connect(_on_object_created)
	_load_current_level()


func _load_current_level() -> void:
	var level_index: int = GameManager.current_level
	if level_index >= GameManager.LEVEL_SCENES.size():
		return

	var level_path: String = GameManager.LEVEL_SCENES[level_index]
	var level_scene: PackedScene = load(level_path)
	if level_scene == null:
		Logger.error("Game: Failed to load level: %s" % level_path)
		return

	_current_level_scene = level_scene.instantiate()
	world.add_child(_current_level_scene)

	# Position player at spawn point
	var spawn_point: Marker2D = _current_level_scene.find_child("SpawnPoint", true, false)
	if spawn_point:
		player.global_position = spawn_point.global_position
	else:
		player.global_position = Vector2(128, 0)

	# Set objective text in HUD
	if _current_level_scene.has_method("get_objective_text"):
		hud.set_objective(_current_level_scene.get_objective_text())


func _on_level_completed(_level_id: int) -> void:
	# GameManager handles level progression via its own listener
	pass


func _on_object_created(blueprint: Dictionary) -> void:
	# Spawn object near player
	var spawn_pos: Vector2 = player.global_position + Vector2(80, -32)
	world.spawn_object(blueprint, spawn_pos)
