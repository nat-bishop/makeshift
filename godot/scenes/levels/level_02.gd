extends BaseLevel
## Level 2: The Sentry
## A hostile creature guards the goal. Player must create something
## to distract, defeat, or bypass it.


func _ready() -> void:
	level_id = 1
	objective_text = "Get past the guard dog!"
	next_level_path = "res://scenes/levels/level_03.tscn"
	super._ready()
	_build_terrain()
	_spawn_prespawn("bone", Vector2(200, 536))
	_spawn_prespawn("guard_dog", Vector2(800, 520))

	# Pre-populate behavior: dog approaches and attacks player
	InteractionCache.store_behavior("guard dog", "player", {
		"movement": 0, "priority": 2, "action": 1, "amount": 20,
		"state_action": 0, "state_id": 0, "force": 0,
	})
	# Dog approaches bone (distraction, higher priority than player)
	InteractionCache.store_behavior("guard dog", "bone", {
		"movement": 0, "priority": 3, "action": 3, "amount": 0,
		"state_action": 0, "state_id": 0, "force": 0,
	})


func _build_terrain() -> void:
	_create_platform(Vector2(0, 568), Vector2(1280, 64))
	_create_kill_zone(Vector2(0, 700), Vector2(1280, 64))
