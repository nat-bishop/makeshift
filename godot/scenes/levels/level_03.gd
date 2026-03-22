extends BaseLevel
## Level 3: Reach the Top
## Tall vertical chamber, spawn at bottom, goal at top (~600px up).
## Walls on sides.

const STONE_COLOR := Color(0.4, 0.35, 0.3)


func _ready() -> void:
	level_id = 2
	objective_text = "Reach the top!"
	next_level_path = ""  # Last level
	super._ready()
	_build_terrain()


func _build_terrain() -> void:
	# Floor
	_create_platform(Vector2(128, 700), Vector2(512, 64), STONE_COLOR)

	# Left wall
	_create_platform(Vector2(64, 0), Vector2(64, 764), STONE_COLOR)

	# Right wall
	_create_platform(Vector2(640, 0), Vector2(64, 764), STONE_COLOR)

	# Some small ledges to hint at stacking/climbing
	_create_platform(Vector2(192, 560), Vector2(128, 16), STONE_COLOR)
	_create_platform(Vector2(400, 440), Vector2(128, 16), STONE_COLOR)
	_create_platform(Vector2(224, 300), Vector2(128, 16), STONE_COLOR)

	# Ceiling with gap for the goal
	_create_platform(Vector2(64, 64), Vector2(240, 32), STONE_COLOR)
	_create_platform(Vector2(464, 64), Vector2(240, 32), STONE_COLOR)
