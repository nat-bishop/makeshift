extends BaseLevel
## Level 1: The Acid Moat
## Two platforms separated by a 480px acid-filled pit. Player must create
## a durable bridge to cross. Stone resists acid; wood corrodes.

const CRATE_BLUEPRINT := {
	"id": "crate_level01",
	"name": "wooden crate",
	"description": "wooden crate",
	"visual_description": "a small wooden shipping crate with planks and nails",
	"physics": {"mass_kg": 5.0, "height_cm": 40, "surface": 1, "bounce": 10, "gravity": 55},
	"durability": 2,
	"affordance": 0,
	"autonomous": false,
}

const ACID_POOL_BP := {
	"name": "acid pool",
	"physics": {"mass_kg": 100.0, "height_cm": 10, "surface": 0, "bounce": 0, "gravity": 50},
	"durability": 6,
}


func _ready() -> void:
	level_id = 0
	objective_text = "Cross the acid moat!"
	next_level_path = "res://scenes/levels/level_02.tscn"
	super._ready()
	_build_terrain()
	_spawn_game_object(CRATE_BLUEPRINT, Vector2(280, 536))

	# Pre-populate behavior: acid pool damages wooden crate (reactive)
	InteractionCache.store_behavior("acid pool", "wooden crate", {
		"movement": 2, "priority": 2, "action": 1, "amount": 15,
		"state_action": 0, "state_id": 0, "force": 0,
	})


func _build_terrain() -> void:
	_create_platform(Vector2(0, 568), Vector2(384, 64))
	_create_platform(Vector2(896, 568), Vector2(384, 64))
	_create_platform(Vector2(384, 568), Vector2(16, 128))
	_create_platform(Vector2(880, 568), Vector2(16, 128))
	_create_env_body(
		Vector2(400, 632), Vector2(480, 48),
		"acid pool", ACID_POOL_BP,
		Color(0.2, 0.9, 0.1, 0.8), false
	)
	_create_kill_zone(Vector2(400, 700), Vector2(480, 64))
