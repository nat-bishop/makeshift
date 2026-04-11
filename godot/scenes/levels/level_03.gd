extends BaseLevel
## Level 3: The Climb
## Goal is high up. Player must create objects to reach it.
## Stacked objects, ladders, or flying objects all work.

const WOODEN_BOX_BLUEPRINT := {
	"id": "box_level03",
	"name": "wooden box",
	"description": "wooden box",
	"visual_description": "a sturdy wooden storage box, medium sized",
	"physics": {"mass_kg": 8.0, "height_cm": 60, "surface": 1, "bounce": 10, "gravity": 55},
	"durability": 2,
	"affordance": 0,
	"autonomous": false,
	"susceptible_states": [1],
}

const CAMPFIRE_BLUEPRINT := {
	"id": "campfire_level03",
	"name": "campfire",
	"description": "campfire",
	"visual_description": "a small campfire with logs and orange flames",
	"physics": {"mass_kg": 3.0, "height_cm": 40, "surface": 1, "bounce": 5, "gravity": 55},
	"durability": 1,
	"affordance": 3,
	"autonomous": false,
	"initial_states": [1],
}

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
	_spawn_game_object(WOODEN_BOX_BLUEPRINT, Vector2(200, 536))
	_spawn_game_object(CAMPFIRE_BLUEPRINT, Vector2(600, 536))

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
