extends "res://scenes/levels/base_level.gd"
## Level 1: Cross the Gap
## Two platforms separated by a gap (~384px). Spawn left, goal right.


func _ready() -> void:
	level_id = 0
	objective_text = "Cross the gap!"
	next_level_path = "res://scenes/levels/level_02.tscn"
	super._ready()
	_build_terrain()


func _build_terrain() -> void:
	# Build platforms using StaticBody2D with collision shapes
	# Left platform: 8 tiles wide (512px)
	_create_platform(Vector2(0, 400), Vector2(512, 64))
	# Right platform: 8 tiles wide, after 384px gap
	_create_platform(Vector2(896, 400), Vector2(512, 64))
	# Bottom kill zone (so player respawns if they fall)
	_create_kill_zone(Vector2(512, 700), Vector2(384, 64))


func _create_platform(pos: Vector2, size: Vector2) -> void:
	var body := StaticBody2D.new()
	body.position = pos
	body.collision_layer = 1  # Terrain layer
	body.collision_mask = 0

	var shape := CollisionShape2D.new()
	var rect := RectangleShape2D.new()
	rect.size = size
	shape.shape = rect
	shape.position = size / 2
	body.add_child(shape)

	var visual := ColorRect.new()
	visual.size = size
	visual.color = Color(0.35, 0.28, 0.2)  # Brown terrain
	body.add_child(visual)

	add_child(body)


func _create_kill_zone(pos: Vector2, size: Vector2) -> void:
	var area := Area2D.new()
	area.position = pos
	area.collision_layer = 8  # Hazards layer
	area.collision_mask = 2  # Player

	var shape := CollisionShape2D.new()
	var rect := RectangleShape2D.new()
	rect.size = size
	shape.shape = rect
	shape.position = size / 2
	area.add_child(shape)

	area.body_entered.connect(_on_kill_zone_entered)
	add_child(area)


func _on_kill_zone_entered(body: Node) -> void:
	if body is CharacterBody2D and body.has_method("get_effective_tags"):
		# Respawn player at spawn point
		body.global_position = spawn_point.global_position
		body.velocity = Vector2.ZERO
