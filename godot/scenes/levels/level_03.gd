extends BaseLevel
## Level 3: The Climb
## Goal is high up. Player must create objects to reach it.
## Stacked objects, ladders, or flying objects all work.

const FIRE_PIT_BP := {
	"name": "fire pit",
	"physics": {"mass_kg": 50.0, "height_cm": 10, "surface": 1, "bounce": 0, "gravity": 50},
	"durability": 6,
}


func _ready() -> void:
	level_id = 2
	objective_text = "Reach the top!"
	next_level_path = ""
	super._ready()
	_build_terrain()
	_spawn_prespawn("wooden_box", Vector2(200, 536))
	_spawn_prespawn("campfire", Vector2(600, 536))

	# Pre-populate behavior: campfire damages wooden box and sets it on fire
	InteractionCache.store_behavior("campfire", "wooden box", {
		"movement": 2, "priority": 2, "action": 1, "amount": 10,
		"state_action": 1, "state_id": 1, "force": 0,
	})


func _build_terrain() -> void:
	_create_platform(Vector2(0, 568), Vector2(1280, 64))
	_create_platform(Vector2(300, 450), Vector2(200, 24))
	_create_platform(Vector2(600, 330), Vector2(200, 24))
	_create_platform(Vector2(900, 210), Vector2(200, 24))
	_create_env_body(
		Vector2(450, 540), Vector2(100, 28),
		"fire pit", FIRE_PIT_BP,
		Color(1.0, 0.3, 0.0, 0.8), false
	)
