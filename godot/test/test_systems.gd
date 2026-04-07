extends SceneTree
## Comprehensive test harness: exercises all Godot subsystems headlessly.
## Run: cd godot && timeout 60 godot --headless --quit --script res://test/test_systems.gd

const CL = preload("res://scripts/data/collision_layers.gd")
const SC = preload("res://scripts/data/state_colors.gd")

var _pass_count: int = 0
var _fail_count: int = 0
var _frame: int = 0
var _cam: Camera2D

# Autoload references (resolved from root children)
var _event_bus: Node
var _game_manager: Node
var _backend: Node
var _log: Node
var _collision_resolver: Node


func _initialize() -> void:
	print("=== TEST: Systems Integration (Comprehensive) ===")
	var root = get_root()

	# Resolve autoloads
	for child in root.get_children():
		match child.name:
			"EventBus": _event_bus = child
			"GameManager": _game_manager = child
			"Backend": _backend = child
			"Log": _log = child
			"CollisionResolver": _collision_resolver = child

	_test_autoloads()
	_test_collision_layers()
	_test_game_manager()
	_test_event_bus_signals()
	_test_state_colors()
	_test_state_contradictions()
	_test_scene_compilation()
	_test_level_construction()
	_test_game_object()

	# Camera for screenshot compatibility
	_cam = Camera2D.new()
	_cam.position = Vector2(640, 360)
	root.add_child(_cam)
	_cam.call_deferred("make_current")

	# Summary
	print("\n=== SUMMARY ===")
	print("PASSED: %d" % _pass_count)
	print("FAILED: %d" % _fail_count)
	print("TOTAL:  %d" % (_pass_count + _fail_count))

	if _fail_count == 0:
		print("\nALL PASSED")
	else:
		print("\nFAILURES DETECTED")

	print("=== TEST COMPLETE ===")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

func _assert(desc: String, condition: bool) -> void:
	if condition:
		_pass_count += 1
		print("ASSERT PASS: %s" % desc)
	else:
		_fail_count += 1
		print("ASSERT FAIL: %s" % desc)


func _section(name: String) -> void:
	print("\n--- %s ---" % name)


func _make_mock_body(id: String, states: Array, durability: float = 150.0) -> Node2D:
	var body = Node2D.new()
	var script = GDScript.new()
	script.source_code = """extends Node2D

var object_id: String = ""
var tags: Array = []
var states: Array = []
var current_durability: float = 150.0
var damage_log: Array = []
var blueprint: Dictionary = {}

func get_object_id() -> String:
	return object_id

func get_tags() -> Array:
	return states

func get_states() -> Array:
	return states

func get_effective_tags() -> Array:
	return states

func add_state(state: String, _duration: float = 0.0) -> void:
	if state not in states:
		states.append(state)

func remove_state(state: String) -> void:
	states.erase(state)

func add_tag(tag: String, _duration: float = 0.0) -> void:
	add_state(tag, _duration)

func remove_tag(tag: String) -> void:
	remove_state(tag)

func take_damage(amount: float) -> void:
	damage_log.append(amount)
	current_durability -= amount

func has_tag(tag: String) -> bool:
	return tag in states
"""
	script.reload()
	body.set_script(script)
	body.name = id
	body.set("object_id", id)
	body.set("states", states.duplicate())
	body.set("tags", states.duplicate())
	body.set("current_durability", durability)
	body.set("damage_log", [])
	body.position = Vector2(100, 100)
	return body


# ---------------------------------------------------------------------------
# Section 1: Autoloads
# ---------------------------------------------------------------------------

func _test_autoloads() -> void:
	_section("Autoloads")
	_assert("EventBus exists", _event_bus != null)
	_assert("GameManager exists", _game_manager != null)
	_assert("Backend exists", _backend != null)
	_assert("Log exists", _log != null)
	_assert("CollisionResolver exists", _collision_resolver != null)

	_assert("Log has debug()", _log.has_method("debug"))
	_assert("Log has info()", _log.has_method("info"))
	_assert("Log has warn()", _log.has_method("warn"))
	_assert("Log has error()", _log.has_method("error"))


# ---------------------------------------------------------------------------
# Section 2: CollisionLayers
# ---------------------------------------------------------------------------

func _test_collision_layers() -> void:
	_section("CollisionLayers")
	_assert("TERRAIN == 1", CL.TERRAIN == 1)
	_assert("PLAYER == 2", CL.PLAYER == 2)
	_assert("OBJECTS == 4", CL.OBJECTS == 4)
	_assert("HAZARDS == 8", CL.HAZARDS == 8)
	_assert("TRIGGERS == 16", CL.TRIGGERS == 16)
	_assert("TERRAIN is power of 2", CL.TERRAIN & (CL.TERRAIN - 1) == 0)
	_assert("No layer overlap (union == 31)", CL.TERRAIN | CL.PLAYER | CL.OBJECTS | CL.HAZARDS | CL.TRIGGERS == 31)


# ---------------------------------------------------------------------------
# Section 3: GameManager
# ---------------------------------------------------------------------------

func _test_game_manager() -> void:
	_section("GameManager")
	_assert("starts in MENU state (0)", _game_manager.current_state == 0)
	_assert("current_level starts at 0", _game_manager.current_level == 0)
	_assert("has 3 levels", _game_manager.LEVELS.size() == 3)
	_assert("has start_game()", _game_manager.has_method("start_game"))
	_assert("has pause_game()", _game_manager.has_method("pause_game"))
	_assert("has resume_game()", _game_manager.has_method("resume_game"))
	_assert("has return_to_menu()", _game_manager.has_method("return_to_menu"))


# ---------------------------------------------------------------------------
# Section 4: EventBus Signals
# ---------------------------------------------------------------------------

func _test_event_bus_signals() -> void:
	_section("EventBus Signals")
	var expected: Array = [
		"interaction_triggered", "object_created",
		"sprite_ready", "level_completed",
	]
	for sig_name in expected:
		_assert("has signal: %s" % sig_name, _event_bus.has_signal(sig_name))


# ---------------------------------------------------------------------------
# Section 5: StateColors (V3)
# ---------------------------------------------------------------------------

func _test_state_colors() -> void:
	_section("StateColors")
	_assert("on_fire has color", SC.get_color("on_fire") != Color.WHITE)
	_assert("frozen has color", SC.get_color("frozen") != Color.WHITE)
	_assert("electrified has color", SC.get_color("electrified") != Color.WHITE)
	_assert("unknown state -> white", SC.get_color("NONEXISTENT") == Color.WHITE)
	_assert("is_stateful detects on_fire", SC.is_stateful("on_fire"))
	_assert("is_stateful rejects unknown", not SC.is_stateful("NONEXISTENT"))


# ---------------------------------------------------------------------------
# Section 6: StateContradictions (V3)
# ---------------------------------------------------------------------------

func _test_state_contradictions() -> void:
	_section("StateContradictions")
	var SContra = preload("res://scripts/data/state_contradictions.gd")
	var contras = SContra.get_contradictions("on_fire")
	_assert("on_fire contradicts frozen", "frozen" in contras)
	_assert("on_fire contradicts wet", "wet" in contras)
	var empty = SContra.get_contradictions("nonexistent")
	_assert("unknown state has no contradictions", empty.is_empty())


# ---------------------------------------------------------------------------
# Section 7: Scene Compilation
# ---------------------------------------------------------------------------

func _test_scene_compilation() -> void:
	_section("Scene Compilation")
	var scenes: Array[String] = [
		"res://scenes/game/game.tscn",
		"res://scenes/game_object/game_object.tscn",
		"res://scenes/hud/hud.tscn",
		"res://scenes/hud/interaction_feedback.tscn",
		"res://scenes/hud/object_creation_panel.tscn",
		"res://scenes/levels/base_level.tscn",
		"res://scenes/levels/level_01.tscn",
		"res://scenes/levels/level_02.tscn",
		"res://scenes/levels/level_03.tscn",
		"res://scenes/main_menu/main_menu.tscn",
		"res://scenes/player/player.tscn",
		"res://scenes/world/world.tscn",
	]
	for path in scenes:
		var scene = load(path)
		_assert("loads: %s" % path, scene != null)


# ---------------------------------------------------------------------------
# Section 8: Level Construction
# ---------------------------------------------------------------------------

func _test_level_construction() -> void:
	_section("Level Construction")
	var root = get_root()

	var level_paths: Array[String] = [
		"res://scenes/levels/level_01.tscn",
		"res://scenes/levels/level_02.tscn",
		"res://scenes/levels/level_03.tscn",
	]

	for i in range(level_paths.size()):
		var scene: PackedScene = load(level_paths[i])
		_assert("level_%d scene loads" % (i + 1), scene != null)
		var level = scene.instantiate()
		root.add_child(level)

		var spawn = level.find_child("SpawnPoint", true, false)
		var goal = level.find_child("Goal", true, false)

		_assert("level_%d has SpawnPoint" % (i + 1), spawn != null)
		_assert("level_%d has Goal" % (i + 1), goal != null)

		if goal != null:
			_assert("level_%d Goal is Area2D" % (i + 1), goal is Area2D)
			var goal_shape = goal.find_child("CollisionShape2D", false, false)
			_assert("level_%d Goal has CollisionShape2D" % (i + 1), goal_shape != null)

		level.free()


# ---------------------------------------------------------------------------
# Section 9: GameObject
# ---------------------------------------------------------------------------

func _test_game_object() -> void:
	_section("GameObject")
	var root = get_root()

	var go = _make_mock_body("test_001", ["on_fire", "frozen"], 100.0)
	go.set("blueprint", {"id": "test_001", "name": "test", "states": ["on_fire", "frozen"], "visual_descriptor": {}})
	root.add_child(go)

	# Core API
	_assert("get_object_id()", go.get_object_id() == "test_001")
	_assert("get_states()", go.get_states() == ["on_fire", "frozen"])

	# State mutation
	go.add_state("wet")
	_assert("add_state adds wet", "wet" in go.get_states())
	go.add_state("wet")
	_assert("add_state no duplicate", go.get_states().count("wet") == 1)

	go.remove_state("frozen")
	_assert("remove_state removes frozen", "frozen" not in go.get_states())
	go.remove_state("NONEXISTENT")
	_assert("remove nonexistent no crash", true)

	# Damage
	go.take_damage(30.0)
	_assert("take_damage reduces durability", go.get("current_durability") == 70.0)
	_assert("take_damage logs damage", go.get("damage_log").size() == 1)

	# has_tag (backward compat)
	_assert("has_tag(on_fire)", go.has_tag("on_fire"))
	_assert("not has_tag(frozen)", not go.has_tag("frozen"))

	go.free()


# ---------------------------------------------------------------------------
# _process for --write-movie compatibility
# ---------------------------------------------------------------------------

func _process(_delta: float) -> bool:
	_frame += 1
	return _frame > 3
