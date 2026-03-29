extends BaseLevel
## Level 2: The Sentry
## Sentry turret on a pedestal patrols and fires HOT projectiles. Player uses
## seed objects (barricade for cover, reflective shield) or creates counter-objects.

const TURRET_BLUEPRINT := {
	"id": "turret_level02",
	"name": "Sentry Turret",
	"tags": ["SOLID", "RIGID", "HEAVY", "HEAT_SOURCE"],
	"starting_durability": 200,
	"visual_descriptor": {
		"visual_description": "a mechanical sentry turret with a rotating barrel mounted on a tripod base",
		"size_category": "medium",
	},
	"behaviors": [
		{
			"trigger": "ALWAYS",
			"action": "PATROL",
			"target": "SELF",
			"speed": "SLOW",
		},
		{
			"trigger": "ON_PROXIMITY",
			"action": "SPAWN_PROJECTILE",
			"target": "NEAREST_PLAYER",
			"intensity": "MEDIUM",
			"range": "FAR",
			"interval": "SLOW",
		},
	],
}

const BARRICADE_BLUEPRINT := {
	"id": "barricade_level02",
	"name": "Wooden Barricade",
	"tags": ["SOLID", "RIGID", "FLAMMABLE", "BREAKABLE"],
	"starting_durability": 50,
	"visual_descriptor": {
		"visual_description": "a tall wooden barricade made of thick planks nailed together",
		"size_category": "large",
	},
}

const SHIELD_BLUEPRINT := {
	"id": "shield_level02",
	"name": "Metal Shield",
	"tags": ["SOLID", "RIGID", "REFLECTIVE", "CONDUCTING"],
	"starting_durability": 200,
	"visual_descriptor": {
		"visual_description": "a polished metal tower shield with riveted edges",
		"size_category": "medium",
	},
}


func _ready() -> void:
	level_id = 1
	objective_text = "Get past the sentry!"
	next_level_path = "res://scenes/levels/level_03.tscn"
	super._ready()
	_build_terrain()
	_spawn_objects()
	Log.debug("Level: Terrain built for level_02 (The Sentry)")


func _build_terrain() -> void:
	_create_platform(Vector2(0, 400), Vector2(1280, 64))
	_create_platform(Vector2(620, 340), Vector2(128, 60))


func _spawn_objects() -> void:
	_spawn_game_object(TURRET_BLUEPRINT, Vector2(684, 300))

	# Frozen in place as initial cover
	var barricade = _spawn_game_object(BARRICADE_BLUEPRINT, Vector2(420, 280))
	barricade.freeze = true
	barricade.freeze_mode = RigidBody2D.FREEZE_MODE_STATIC

	_spawn_game_object(SHIELD_BLUEPRINT, Vector2(350, 368))
