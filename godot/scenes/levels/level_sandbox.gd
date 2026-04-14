extends BaseLevel
## Sandbox: flat ground with platforms and raised sections. No prebuilt objects.


func _ready() -> void:
	level_id = 3
	objective_text = ""
	next_level_path = ""
	super._ready()
	_build_terrain()


func _build_terrain() -> void:
	_create_platform(Vector2(0, 600), Vector2(1600, 64))

	_create_platform(Vector2(256, 536), Vector2(256, 128))
	_create_platform(Vector2(1088, 472), Vector2(384, 192))

	_create_platform(Vector2(640, 488), Vector2(160, 24))
	_create_platform(Vector2(832, 392), Vector2(160, 24))
	_create_platform(Vector2(192, 336), Vector2(160, 24))

	_create_kill_zone(Vector2(0, 760), Vector2(1600, 64))
