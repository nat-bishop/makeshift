extends BaseLevel
## Level 2: The Burning Bridge
## Two platforms connected by a wooden bridge (FLAMMABLE+BREAKABLE segments).
## Lava below (hazard). A torch (HEAT_SOURCE) sits on the bridge.

const GAME_OBJECT_SCENE: PackedScene = preload("res://scenes/game_object/game_object.tscn")

const BRIDGE_SEGMENT_BLUEPRINT := {
	"id": "bridge_segment",
	"name": "Wooden Plank",
	"tags": ["SOLID", "RIGID", "FLAMMABLE", "BREAKABLE"],
	"visual_descriptor": {
		"base_form": "plank",
		"material": "wood",
		"color_primary": "#8B6914",
		"color_secondary": "#A0812A",
		"visual_effects": [],
		"size_category": "medium",
	},
}

const TORCH_BLUEPRINT := {
	"id": "torch_level02",
	"name": "Torch",
	"tags": ["SOLID", "RIGID", "HEAT_SOURCE", "HOT", "GLOWING", "LIGHT"],
	"visual_descriptor": {
		"base_form": "torch",
		"material": "wood",
		"color_primary": "#FF6600",
		"color_secondary": "#884400",
		"visual_effects": ["flaming", "glowing"],
		"size_category": "small",
	},
}


func _ready() -> void:
	level_id = 1
	objective_text = "Cross the burning bridge!"
	next_level_path = "res://scenes/levels/level_03.tscn"
	super._ready()
	_build_terrain()
	_spawn_bridge_and_torch()


func _build_terrain() -> void:
	# Left platform
	_create_platform(Vector2(0, 400), Vector2(384, 64))
	# Right platform
	_create_platform(Vector2(896, 400), Vector2(384, 64))
	# Lava pit below bridge
	_create_lava_zone(Vector2(384, 500), Vector2(512, 64))
	# Walls below platforms
	_create_platform(Vector2(0, 464), Vector2(384, 200))
	_create_platform(Vector2(896, 464), Vector2(384, 200))


func _spawn_bridge_and_torch() -> void:
	# 5 bridge segments spanning the gap
	var bridge_start_x: float = 384.0
	var segment_width: float = 102.0  # ~512px / 5 segments
	var bridge_y: float = 368.0  # On top of platform level

	for i in range(5):
		var bp := BRIDGE_SEGMENT_BLUEPRINT.duplicate(true)
		bp["id"] = "bridge_segment_%d" % i
		var segment := GAME_OBJECT_SCENE.instantiate()
		add_child(segment)
		segment.global_position = Vector2(
			bridge_start_x + (i * segment_width) + segment_width / 2,
			bridge_y
		)
		segment.init_from_blueprint(bp)
		# Lock bridge segments in place initially
		segment.freeze = true
		segment.freeze_mode = RigidBody2D.FREEZE_MODE_STATIC

	# Torch placed on the middle of the bridge
	var torch := GAME_OBJECT_SCENE.instantiate()
	add_child(torch)
	torch.global_position = Vector2(bridge_start_x + 2.5 * segment_width, bridge_y - 48)
	torch.init_from_blueprint(TORCH_BLUEPRINT.duplicate(true))


func _create_lava_zone(pos: Vector2, size: Vector2) -> void:
	# Visual lava
	var visual := ColorRect.new()
	visual.position = pos
	visual.size = size
	visual.color = Color(0.9, 0.2, 0.0, 0.9)
	add_child(visual)

	# Hazard area
	var area := Area2D.new()
	area.position = pos
	area.collision_layer = CollisionLayers.HAZARDS
	area.collision_mask = CollisionLayers.PLAYER | CollisionLayers.OBJECTS

	var shape := CollisionShape2D.new()
	var rect := RectangleShape2D.new()
	rect.size = size
	shape.shape = rect
	shape.position = size / 2
	area.add_child(shape)

	area.body_entered.connect(_on_lava_entered)
	add_child(area)


func _on_lava_entered(body: Node2D) -> void:
	if _is_player(body):
		_respawn_player(body)
	else:
		WorldMutations.apply_damage(body, 999.0)
