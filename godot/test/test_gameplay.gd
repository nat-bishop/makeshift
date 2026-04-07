extends SceneTree
## V3 Gameplay integration test: tests game logic that works within --script mode.
## Tests autoload interactions, signal wiring, and game state flow.
##
## Run: cd godot && godot --headless --quit-after 60 --fixed-fps 10 \
##      --script res://test/test_gameplay.gd 2>&1

var _pass_count: int = 0
var _fail_count: int = 0
var _frame: int = 0

# Autoload references
var _event_bus: Node
var _game_manager: Node
var _backend: Node
var _log: Node
var _collision_resolver: Node


func _initialize() -> void:
	print("=== TEST: Gameplay Integration (V3) ===")
	var root = get_root()

	# Resolve autoloads
	for child in root.get_children():
		match child.name:
			"EventBus": _event_bus = child
			"GameManager": _game_manager = child
			"Backend": _backend = child
			"Log": _log = child
			"CollisionResolver": _collision_resolver = child

	_test_autoloads_exist()
	_test_collision_resolver_api()
	_test_game_state_flow()
	_test_backend_pairwise_cache()

	print("\n=== SUMMARY ===")
	print("PASSED: %d" % _pass_count)
	print("FAILED: %d" % _fail_count)
	print("TOTAL:  %d" % (_pass_count + _fail_count))
	if _fail_count == 0:
		print("\nALL PASSED")
	else:
		print("\nFAILURES DETECTED")
	print("=== TEST COMPLETE ===")


func _process(_delta: float) -> bool:
	_frame += 1
	return _frame > 3


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


func _make_mock_body(id: String, obj_name: String, states: Array = []) -> Node2D:
	var body = Node2D.new()
	var script = GDScript.new()
	script.source_code = """extends Node2D

var object_id: String = ""
var blueprint: Dictionary = {}
var _states: Array = []

func get_object_id() -> String:
	return object_id

func get_blueprint() -> Dictionary:
	return blueprint

func get_states() -> Array:
	return _states

func get_tags() -> Array:
	return _states

func add_state(state: String, _duration: float = 0.0) -> void:
	if state not in _states:
		_states.append(state)

func remove_state(state: String) -> void:
	_states.erase(state)

func take_damage(amount: float) -> void:
	pass
"""
	script.reload()
	body.set_script(script)
	body.name = id
	body.set("object_id", id)
	body.set("blueprint", {"id": id, "name": obj_name, "states": states})
	body.set("_states", states.duplicate())
	body.position = Vector2(100, 100)
	return body


# ---------------------------------------------------------------------------
# Test: Autoloads exist and have V3 API
# ---------------------------------------------------------------------------

func _test_autoloads_exist() -> void:
	_section("Autoloads (V3)")
	_assert("EventBus exists", _event_bus != null)
	_assert("GameManager exists", _game_manager != null)
	_assert("Backend exists", _backend != null)
	_assert("CollisionResolver exists", _collision_resolver != null)
	_assert("CollisionResolver has resolve_and_notify", _collision_resolver.has_method("resolve_and_notify"))
	_assert("Backend has get_pairwise", _backend.has_method("get_pairwise"))


# ---------------------------------------------------------------------------
# Test: CollisionResolver V3 API
# ---------------------------------------------------------------------------

func _test_collision_resolver_api() -> void:
	_section("CollisionResolver V3 API")
	var root = get_root()

	# V3 CollisionResolver calls Backend.get_pairwise() which returns empty
	# dict when no server/cache is available. This is a safe no-op.
	var body_a = _make_mock_body("cr_a", "fire sword")
	var body_b = _make_mock_body("cr_b", "wooden shield")
	root.add_child(body_a)
	root.add_child(body_b)

	# Should not crash even with no pairwise data cached
	_collision_resolver.resolve_and_notify(body_a, body_b)
	_assert("resolve_and_notify: no crash without cache", true)

	# States unchanged (no pairwise data = no effects)
	_assert("No states changed without cache", body_a.get_states().is_empty())
	_assert("No states changed on B without cache", body_b.get_states().is_empty())

	body_a.free()
	body_b.free()


# ---------------------------------------------------------------------------
# Test: Game state flow (GameManager)
# ---------------------------------------------------------------------------

func _test_game_state_flow() -> void:
	_section("Game State Flow")

	_assert("Initial state is MENU", _game_manager.current_state == 0)
	_assert("Initial level is 0", _game_manager.current_level == 0)
	_assert("3 levels defined", _game_manager.LEVELS.size() == 3)

	# Verify level scene paths
	for i in range(_game_manager.LEVELS.size()):
		var path: String = _game_manager.LEVELS[i]["scene"]
		var scene = load(path)
		_assert("Level %d scene exists" % (i + 1), scene != null)

	# Level completion flow
	_game_manager.current_level = 0
	_game_manager._on_level_completed(0)
	_assert("After level 0 complete, current_level is 1", _game_manager.current_level == 1)

	# Reset
	_game_manager.current_level = 0
	_game_manager.current_state = 0


# ---------------------------------------------------------------------------
# Test: Backend pairwise cache (local)
# ---------------------------------------------------------------------------

func _test_backend_pairwise_cache() -> void:
	_section("Backend Pairwise Cache")

	# Empty cache returns empty dict
	var result: Dictionary = _backend.get_pairwise("fire sword", "wooden shield")
	_assert("Empty cache returns empty dict", result.is_empty())

	_assert("Backend has fetch_scene_pairwise", _backend.has_method("fetch_scene_pairwise"))
	_assert("Backend has request_reevaluation", _backend.has_method("request_reevaluation"))
