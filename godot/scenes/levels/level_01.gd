extends BaseLevel
## Level 1: The Acid Moat
## Two platforms separated by a 480px acid-filled pit. Wooden crate seed object
## demonstrates corrosion rules. Player must create a durable bridge to cross.

const CRATE_BLUEPRINT := {
	"id": "crate_level01",
	"name": "Wooden Crate",
	"mass_kg": 10, "height_cm": 40,
	"friction": 50, "bounce": 10, "gravity": 50,
	"armor": 10, "hp": 50, "indestructible": false,
	"has_field": false, "field_range_cm": 0,
	"autonomous": false, "affordance": 0,
	"visual_descriptor": {
		"visual_description": "a small wooden shipping crate with planks and nails",
		"size_category": "small",
	},
	"destruction_result_name": "wood splinters",
	"states": [],
}


func _ready() -> void:
	level_id = 0
	objective_text = "Cross the acid moat!"
	next_level_path = "res://scenes/levels/level_02.tscn"
	super._ready()
	_build_terrain()
	_spawn_game_object(CRATE_BLUEPRINT, Vector2(280, 536))
	Log.debug("Level: Terrain built for level_01 (The Acid Moat)")


func _build_terrain() -> void:
	_create_platform(Vector2(0, 568), Vector2(384, 64))
	_create_platform(Vector2(896, 568), Vector2(384, 64))
	# Pit walls contain acid and prevent edge shortcuts
	_create_platform(Vector2(384, 568), Vector2(16, 128))
	_create_platform(Vector2(880, 568), Vector2(16, 128))
	_create_env_body(
		Vector2(400, 632), Vector2(480, 48),
		"acid pool",
		Color(0.2, 0.9, 0.1, 0.8), "acid_pool", false
	)
	_create_kill_zone(Vector2(400, 700), Vector2(480, 64))
