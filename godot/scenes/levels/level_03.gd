extends "res://scenes/levels/base_level.gd"
## Level 3: Reach the Top
## Tall vertical chamber, spawn at bottom, goal at top (~600px up).
## Walls on sides.


func _ready() -> void:
	level_id = 2
	objective_text = "Reach the top!"
	next_level_path = ""  # Last level
	super._ready()
	_build_terrain()


func _build_terrain() -> void:
	# Floor
	_create_platform(Vector2(128, 700), Vector2(512, 64))

	# Left wall
	_create_platform(Vector2(64, 0), Vector2(64, 764))

	# Right wall
	_create_platform(Vector2(640, 0), Vector2(64, 764))

	# Some small ledges to hint at stacking/climbing
	_create_platform(Vector2(192, 560), Vector2(128, 16))
	_create_platform(Vector2(400, 440), Vector2(128, 16))
	_create_platform(Vector2(224, 300), Vector2(128, 16))

	# Ceiling with gap for the goal
	_create_platform(Vector2(64, 64), Vector2(240, 32))
	_create_platform(Vector2(464, 64), Vector2(240, 32))


func _create_platform(pos: Vector2, size: Vector2) -> void:
	var body := StaticBody2D.new()
	body.position = pos
	body.collision_layer = 1  # Terrain
	body.collision_mask = 0

	var shape := CollisionShape2D.new()
	var rect := RectangleShape2D.new()
	rect.size = size
	shape.shape = rect
	shape.position = size / 2
	body.add_child(shape)

	var visual := ColorRect.new()
	visual.size = size
	visual.color = Color(0.4, 0.35, 0.3)  # Stone walls
	body.add_child(visual)

	add_child(body)
