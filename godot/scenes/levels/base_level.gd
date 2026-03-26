class_name BaseLevel
extends Node2D
## Base class for all levels. Provides spawn point, goal area, objective, and
## shared terrain-building helpers.

@export var level_id: int = 0
@export var objective_text: String = ""
@export var next_level_path: String = ""

@onready var spawn_point: Marker2D = $SpawnPoint
@onready var goal_area: Area2D = $Goal


func _ready() -> void:
	goal_area.body_entered.connect(_on_goal_body_entered)


func get_objective_text() -> String:
	return objective_text


func _on_goal_body_entered(body: Node2D) -> void:
	if _is_player(body):
		Log.info("BaseLevel: Player reached goal! Completing level %d" % level_id)
		EventBus.level_completed.emit(level_id)


# --- Shared helpers ---

func _is_player(body: Node) -> bool:
	return body is CharacterBody2D and body.has_method("get_effective_tags")


func _respawn_player(body: Node2D) -> void:
	Log.info("BaseLevel: Respawning player to %s" % str(spawn_point.global_position))
	body.global_position = spawn_point.global_position
	body.velocity = Vector2.ZERO

const PLATFORM_TEX: Texture2D = preload("res://assets/tilesets/cardboard_platform.png")

func _create_platform(pos: Vector2, size: Vector2, texture: Texture2D = PLATFORM_TEX) -> void:
	var body := StaticBody2D.new()
	body.position = pos + size / 2
	body.collision_layer = CollisionLayers.TERRAIN
	body.collision_mask = 0

	var shape := CollisionShape2D.new()
	var rect := RectangleShape2D.new()
	rect.size = size
	shape.shape = rect
	body.add_child(shape)

	var visual := TextureRect.new()
	visual.texture = texture
	visual.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	visual.size = size
	visual.position = -size / 2
	visual.stretch_mode = TextureRect.STRETCH_TILE
	body.add_child(visual)

	add_child(body)
