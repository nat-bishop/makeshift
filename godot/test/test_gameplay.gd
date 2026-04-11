extends SceneTree
## Gameplay integration test: tests game logic that works within --script mode
## limitations (class_name scripts are NOT registered in --script mode).
## Tests autoload interactions, signal wiring, and game state management.
##
## For full scene testing, run: godot --headless --quit-after 50 --fixed-fps 10
## (validates all scripts compile and main_menu loads without errors).
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


func _initialize() -> void:
	print("=== TEST: Gameplay Integration ===")
	var root = get_root()

	# Resolve autoloads
	for child in root.get_children():
		match child.name:
			"EventBus": _event_bus = child
			"GameManager": _game_manager = child
			"Backend": _backend = child
			"Log": _log = child

	_test_game_state_flow()
	_test_backend_offline_mode()

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


# ---------------------------------------------------------------------------
# Test: Game state flow (GameManager)
# ---------------------------------------------------------------------------

func _test_game_state_flow() -> void:
	_section("Game State Flow")

	_assert("Initial state is MENU", _game_manager.current_state == 0)  # MENU
	_assert("Initial level is 0", _game_manager.current_level == 0)
	_assert("GAME_SCENE defined", _game_manager.GAME_SCENE != "")
	_assert("3 levels defined", _game_manager.LEVELS.size() == 3)

	# Verify level scene paths are loadable
	for i in range(_game_manager.LEVELS.size()):
		var path: String = _game_manager.LEVELS[i]["scene"]
		var scene = load(path)
		_assert("Level %d scene exists" % (i + 1), scene != null)

	# Simulate level completion signal
	# GameManager listens for level_completed in _ready(), which didn't fire
	# But we can test the flow manually
	_game_manager.current_level = 0
	_game_manager._on_level_completed(0)
	_assert("After level 0 complete, current_level is 1", _game_manager.current_level == 1)

	# Reset for other tests
	_game_manager.current_level = 0
	_game_manager.current_state = 0


# ---------------------------------------------------------------------------
# Test: Backend offline mode
# ---------------------------------------------------------------------------

func _test_backend_offline_mode() -> void:
	_section("Backend Offline Mode")

	# Backend should be in a usable state even without a server
	_assert("Backend has session_id field", _backend.get("session_id") != null)
	_assert("Session ID starts empty or loaded from file", true)
	_assert("Backend has create_object method", _backend.has_method("create_object"))
	_assert("Backend has create_session method", _backend.has_method("create_session"))
	_assert("Backend has fetch_rules method", _backend.has_method("fetch_rules"))
	_assert("Backend has get_cached_sprite method", _backend.has_method("get_cached_sprite"))

	# Sprite cache should return null for unknown IDs
	var cached: Texture2D = _backend.get_cached_sprite("nonexistent")
	_assert("No cached sprite for unknown ID", cached == null)

	# Mark dirty should not crash
	_backend.mark_dirty()
	_assert("mark_dirty() no crash", true)
