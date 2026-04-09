extends BaseLevel
## Level 2: The Sentry
## A hostile creature guards the goal. Player must create something
## to distract, defeat, or bypass it.

const GUARD_DOG_BLUEPRINT := {
	"id": "guard_dog_level02",
	"name": "guard dog",
	"description": "guard dog",
	"visual_description": "a fierce black guard dog with a spiked collar, crouching stance",
	"physics": {"mass_kg": 30.0, "height_cm": 80, "surface": 1, "bounce": 15, "gravity": 50},
	"durability": 3,
	"affordance": 3,
	"autonomous": true,
	"has_field": false,
	"field_range_cm": 0,
}

const BONE_BLUEPRINT := {
	"id": "bone_level02",
	"name": "bone",
	"description": "bone",
	"visual_description": "a white dog bone, cartoon style",
	"physics": {"mass_kg": 0.3, "height_cm": 20, "surface": 1, "bounce": 20, "gravity": 50},
	"durability": 2,
	"affordance": 0,
	"autonomous": false,
	"has_field": false,
	"field_range_cm": 0,
}


func _ready() -> void:
	level_id = 1
	objective_text = "Get past the guard dog!"
	next_level_path = "res://scenes/levels/level_03.tscn"
	super._ready()
	_build_terrain()
	_spawn_game_object(BONE_BLUEPRINT, Vector2(200, 536))
	_spawn_game_object(GUARD_DOG_BLUEPRINT, Vector2(800, 520))

	# Pre-populate creature behavior: dog approaches player aggressively
	InteractionCache.store_creature("guard dog", "player", {
		"movement": 0, "priority": 2, "action": 1, "amount": 20, "state_id": 0,
	})
	# Dog approaches bone (distraction)
	InteractionCache.store_creature("guard dog", "bone", {
		"movement": 0, "priority": 3, "action": 6, "amount": 0, "state_id": 0,
	})


func _build_terrain() -> void:
	_create_platform(Vector2(0, 568), Vector2(1280, 64))
