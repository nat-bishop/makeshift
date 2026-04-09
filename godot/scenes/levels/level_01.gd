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
	"has_field": false,
	"field_range_cm": 0,
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

	# Pre-populate pairwise cache for acid + crate
	InteractionCache.store_pairwise("acid pool", "wooden crate", {
		"name_a": "acid pool", "name_b": "wooden crate",
		"damage_a": 0, "damage_b": 15,
		"state_change_a": 0, "state_change_b": 0,
		"force_b": 0,
		"continuous": true,
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
