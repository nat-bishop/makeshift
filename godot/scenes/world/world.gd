extends Node2D

const GAME_OBJECT_SCENE: PackedScene = preload("res://scenes/game_object/game_object.tscn")

@onready var objects_container: Node2D = $ObjectsContainer
@onready var tile_map: TileMapLayer = $TileMapLayer

var _current_level: Node2D = null


func spawn_object(blueprint: Dictionary, pos: Vector2) -> Node:
	var obj: RigidBody2D = GAME_OBJECT_SCENE.instantiate()
	objects_container.add_child(obj)
	obj.global_position = pos
	obj.init_from_blueprint(blueprint)
	return obj


func clear_objects() -> void:
	for child in objects_container.get_children():
		child.queue_free()


func load_level(level_scene: PackedScene) -> void:
	# Remove current level
	if _current_level:
		_current_level.queue_free()
		_current_level = null

	_current_level = level_scene.instantiate()
	add_child(_current_level)
	move_child(_current_level, 0)  # Behind objects
