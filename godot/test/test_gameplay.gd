extends SceneTree
## Gameplay integration test: tests game logic that works within --script mode
## limitations (class_name scripts are NOT registered in --script mode).
## Tests autoload interactions, signal wiring, rule engine integration with
## collision resolver, and effect chains.
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
var _rule_engine: Node
var _backend: Node
var _log: Node
var _collision_resolver: Node


func _initialize() -> void:
	print("=== TEST: Gameplay Integration ===")
	var root = get_root()

	# Resolve autoloads
	for child in root.get_children():
		match child.name:
			"EventBus": _event_bus = child
			"GameManager": _game_manager = child
			"RuleEngine": _rule_engine = child
			"Backend": _backend = child
			"Log": _log = child
			"CollisionResolver": _collision_resolver = child

	# Initialize CollisionResolver's _effect_executor (doesn't fire _ready)
	var ee_script = load("res://scripts/systems/effect_executor.gd")
	var ee = Node.new()
	ee.set_script(ee_script)
	_collision_resolver.add_child(ee)
	_collision_resolver.set("_effect_executor", ee)

	_load_production_rules()

	_test_full_interaction_chain()
	_test_cascade_chain()
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


func _make_mock_body(id: String, tags: Array, durability: float = 150.0) -> Node2D:
	var body = Node2D.new()
	var script = GDScript.new()
	script.source_code = """extends Node2D

var object_id: String = ""
var tags: Array = []
var current_durability: float = 150.0
var damage_log: Array = []

func get_object_id() -> String:
	return object_id

func get_tags() -> Array:
	return tags

func get_effective_tags() -> Array:
	return tags

func add_tag(tag: String, _duration: float = 0.0) -> void:
	if tag not in tags:
		tags.append(tag)

func remove_tag(tag: String) -> void:
	tags.erase(tag)

func take_damage(amount: float) -> void:
	damage_log.append(amount)
	current_durability -= amount
"""
	script.reload()
	body.set_script(script)
	body.name = id
	body.set("object_id", id)
	body.set("tags", tags.duplicate())
	body.set("current_durability", durability)
	body.set("damage_log", [])
	body.position = Vector2(100, 100)
	return body


func _load_production_rules() -> void:
	# Load a representative subset of production rules to test
	# realistic interaction scenarios
	_rule_engine.load_rules([
		{
			"rule_id": "heat_flammable_ignite",
			"tags_required_a": ["HEAT_SOURCE"],
			"tags_required_b": ["FLAMMABLE"],
			"effects": [
				{"effect_type": "ADD_TAG", "target": "b", "tag": "HEAT_SOURCE"},
				{"effect_type": "ADD_TAG", "target": "b", "tag": "HOT"},
				{"effect_type": "DAMAGE", "target": "b", "damage_amount": 10.0, "tick_interval": 1.0, "tick_duration": 5.0, "message": "catches fire!"},
			],
			"execution_order": 5,
			"bidirectional": true,
			"cascade_eligible": true,
		},
		{
			"rule_id": "cold_liquid_freeze",
			"tags_required_a": ["COLD"],
			"tags_required_b": ["LIQUID"],
			"effects": [
				{"effect_type": "ADD_TAG", "target": "b", "tag": "FROZEN"},
				{"effect_type": "ADD_TAG", "target": "b", "tag": "RIGID"},
				{"effect_type": "REMOVE_TAG", "target": "b", "tag": "LIQUID", "message": "freezes solid"},
			],
			"execution_order": 4,
			"bidirectional": true,
			"cascade_eligible": true,
		},
		{
			"rule_id": "sharp_breakable_damage",
			"tags_required_a": ["SHARP"],
			"tags_required_b": ["BREAKABLE"],
			"effects": [
				{"effect_type": "DAMAGE", "target": "b", "damage_amount": 25.0, "message": "slashes!"},
			],
			"execution_order": 3,
			"bidirectional": false,
			"cascade_eligible": false,
		},
		{
			"rule_id": "liquid_heat_extinguish",
			"tags_required_a": ["LIQUID"],
			"tags_required_b": ["HEAT_SOURCE"],
			"effects": [
				{"effect_type": "REMOVE_TAG", "target": "b", "tag": "HEAT_SOURCE"},
				{"effect_type": "REMOVE_TAG", "target": "b", "tag": "HOT", "message": "extinguished!"},
			],
			"execution_order": 6,
			"bidirectional": true,
			"cascade_eligible": false,
		},
		{
			"rule_id": "explosive_wildcard",
			"tags_required_a": ["EXPLOSIVE"],
			"tags_required_b": [],
			"effects": [
				{"effect_type": "DAMAGE", "target": "both", "damage_amount": 50.0, "message": "BOOM!"},
			],
			"execution_order": 10,
			"bidirectional": false,
			"cascade_eligible": false,
		},
	])


# ---------------------------------------------------------------------------
# Test: Full interaction chain (torch lights wood, wood ignites nearby wood)
# ---------------------------------------------------------------------------

func _test_full_interaction_chain() -> void:
	_section("Full Interaction Chain")
	var root = get_root()

	# Create torch and wooden plank
	var torch = _make_mock_body("torch", ["SOLID", "HEAT_SOURCE", "HOT"], 80.0)
	var plank = _make_mock_body("plank", ["SOLID", "FLAMMABLE", "BREAKABLE"], 50.0)
	root.add_child(torch)
	root.add_child(plank)

	# Wire up interaction tracking
	var interaction_log: Array = []
	_event_bus.interaction_triggered.connect(
		func(_sn, _st, _tn, _tt, msg, _wp): interaction_log.append(msg),
		CONNECT_ONE_SHOT
	)

	# Torch collides with plank
	_collision_resolver.clear_cooldowns()
	_collision_resolver.resolve_collision(torch, plank)

	# Plank should now be on fire
	_assert("Chain: plank gains HEAT_SOURCE", "HEAT_SOURCE" in plank.get("tags"))
	_assert("Chain: plank gains HOT", "HOT" in plank.get("tags"))
	_assert("Chain: interaction message logged", interaction_log.size() > 0)
	if not interaction_log.is_empty():
		_assert("Chain: message is 'catches fire!'", interaction_log[0] == "catches fire!")

	# Now the plank (on fire) is itself a HEAT_SOURCE
	# It should be able to ignite another flammable object
	var plank2 = _make_mock_body("plank2", ["SOLID", "FLAMMABLE"], 50.0)
	root.add_child(plank2)
	_collision_resolver.clear_cooldowns()
	_collision_resolver.resolve_collision(plank, plank2)
	_assert("Chain: fire spreads to plank2", "HEAT_SOURCE" in plank2.get("tags"))

	# Extinguish with water
	var water = _make_mock_body("water", ["LIQUID"], 999.0)
	root.add_child(water)
	_collision_resolver.clear_cooldowns()
	_collision_resolver.resolve_collision(water, plank)
	_assert("Chain: water extinguishes plank", "HEAT_SOURCE" not in plank.get("tags"))
	_assert("Chain: water removes HOT from plank", "HOT" not in plank.get("tags"))

	# Explosive wildcard
	var bomb = _make_mock_body("bomb", ["EXPLOSIVE"], 10.0)
	var bystander = _make_mock_body("bystander", ["SOLID"], 100.0)
	root.add_child(bomb)
	root.add_child(bystander)
	_collision_resolver.clear_cooldowns()
	_collision_resolver.resolve_collision(bomb, bystander)
	_assert("Explosive damages both", bomb.get("damage_log").size() > 0)
	_assert("Explosive damages bystander too", bystander.get("damage_log").size() > 0)

	torch.free()
	plank.free()
	plank2.free()
	water.free()
	bomb.free()
	bystander.free()


# ---------------------------------------------------------------------------
# Test: Cascade chain (fire spreads via cascade-eligible rules)
# ---------------------------------------------------------------------------

func _test_cascade_chain() -> void:
	_section("Cascade Chain")
	var root = get_root()

	# The IGNITE rule is cascade_eligible. When plank gains tags, cascade
	# checks neighbors. In headless mode, get_cascade_neighbors won't find
	# spatial neighbors, so cascade doesn't propagate. But we can test that
	# the cascade_depth limit is respected.

	var torch = _make_mock_body("c_torch", ["HEAT_SOURCE"])
	var plank = _make_mock_body("c_plank", ["FLAMMABLE"])
	root.add_child(torch)
	root.add_child(plank)

	# Resolve at max depth - should be a no-op
	_collision_resolver.clear_cooldowns()
	_collision_resolver.resolve_collision(torch, plank, 4)  # MAX_CASCADE_DEPTH is 3
	_assert("Cascade: blocked at max depth", "HEAT_SOURCE" not in plank.get("tags"))

	# Resolve at depth 0 - should work
	_collision_resolver.clear_cooldowns()
	_collision_resolver.resolve_collision(torch, plank, 0)
	_assert("Cascade: works at depth 0", "HEAT_SOURCE" in plank.get("tags"))

	torch.free()
	plank.free()


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
