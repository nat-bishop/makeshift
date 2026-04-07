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
	Log.info("Level: Ready — id=%d path=%s" % [level_id, scene_file_path])
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

const ENV_BODY_SCRIPT: GDScript = preload("res://scenes/environment_body/environment_body.gd")
const PLATFORM_TEX: Texture2D = preload("res://assets/tilesets/cardboard_platform.png")
const GAME_OBJECT_SCENE: PackedScene = preload("res://scenes/game_object/game_object.tscn")

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


func _spawn_game_object(blueprint: Dictionary, pos: Vector2) -> Node:
	var obj = GAME_OBJECT_SCENE.instantiate()
	add_child(obj)
	obj.global_position = pos
	obj.init_from_blueprint(blueprint.duplicate(true))
	return obj


func _create_kill_zone(pos: Vector2, size: Vector2) -> void:
	var area := Area2D.new()
	area.position = pos + size / 2
	area.collision_layer = CollisionLayers.HAZARDS
	area.collision_mask = CollisionLayers.PLAYER | CollisionLayers.OBJECTS
	var shape := CollisionShape2D.new()
	var rect := RectangleShape2D.new()
	rect.size = size
	shape.shape = rect
	area.add_child(shape)
	area.body_entered.connect(_on_kill_zone_entered)
	add_child(area)


func _on_kill_zone_entered(body: Node2D) -> void:
	if _is_player(body):
		_respawn_player(body)
	else:
		WorldMutations.apply_damage(body, 999.0)


func _create_env_body(pos: Vector2, size: Vector2, env_name: String, color: Color, env_id: String = "", solid: bool = true) -> StaticBody2D:
	## V3: Create environment body with blueprint-based pairwise interactions.
	var bp: Dictionary = {
		"id": env_id if env_id != "" else env_name + "_" + str(randi()),
		"name": env_name,
		"description": env_name,
		"mass_kg": 99999, "height_cm": int(size.y),
		"friction": 50, "bounce": 0, "gravity": 50,
		"armor": 100, "hp": 0, "indestructible": true,
		"has_field": true, "field_range_cm": int(size.x * 0.6),
		"autonomous": false, "affordance": 3,
		"visual_descriptor": {"visual_description": env_name, "size_category": "large"},
		"destruction_result_name": "", "states": [],
	}
	var body := StaticBody2D.new()
	body.set_script(ENV_BODY_SCRIPT)
	body.position = pos + size / 2
	add_child(body)
	body.init_env_v3(bp, size, color, solid)
	return body
