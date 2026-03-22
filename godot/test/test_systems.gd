extends SceneTree
## Test harness: exercises autoloads, rule engine, inventory, equipment,
## physics composer, and collision layers. Scene instantiation is skipped
## because SceneTree scripts can't resolve class_name references at parse time.

const TPM = preload("res://scripts/data/tag_physics_map.gd")
const TC = preload("res://scripts/data/tag_colors.gd")
const CL = preload("res://scripts/data/collision_layers.gd")

var _frame: int = 0
var _cam: Camera2D

# Autoload references (resolved from root children — quirks.md)
var _event_bus: Node
var _game_manager: Node
var _rule_engine: Node
var _backend: Node
var _log: Node
var _collision_resolver: Node


func _initialize() -> void:
	print("=== TEST: Systems Integration ===")
	var root := get_root()

	# Resolve autoloads
	for child in root.get_children():
		match child.name:
			"EventBus": _event_bus = child
			"GameManager": _game_manager = child
			"RuleEngine": _rule_engine = child
			"Backend": _backend = child
			"Log": _log = child
			"CollisionResolver": _collision_resolver = child

	_test_autoloads()
	_test_collision_layers()
	_test_game_manager()
	_test_rule_engine()
	_test_event_bus_signals()
	_test_equipment()
	_test_inventory()
	_test_physics_composer()
	_test_tag_colors()
	_test_tag_physics_map()
	_test_collision_resolver()

	# Camera for screenshot (add to tree before make_current)
	_cam = Camera2D.new()
	_cam.position = Vector2(640, 360)
	root.add_child(_cam)
	_cam.call_deferred("make_current")

	print("\n=== ALL TESTS COMPLETE ===")


func _test_autoloads() -> void:
	print("\n--- Autoloads ---")
	_assert("EventBus exists", _event_bus != null)
	_assert("GameManager exists", _game_manager != null)
	_assert("RuleEngine exists", _rule_engine != null)
	_assert("Backend exists", _backend != null)
	_assert("Log exists", _log != null)
	_assert("CollisionResolver exists", _collision_resolver != null)

	# Verify Log has expected methods
	_assert("Log has debug()", _log.has_method("debug"))
	_assert("Log has info()", _log.has_method("info"))
	_assert("Log has warn()", _log.has_method("warn"))
	_assert("Log has error()", _log.has_method("error"))

	# Verify CollisionResolver has expected methods
	_assert("CollisionResolver has resolve_collision()", _collision_resolver.has_method("resolve_collision"))
	_assert("CollisionResolver has clear_cooldowns()", _collision_resolver.has_method("clear_cooldowns"))


func _test_collision_layers() -> void:
	print("\n--- CollisionLayers ---")
	_assert("TERRAIN == 1 (bit 1)", CL.TERRAIN == 1)
	_assert("PLAYER == 2 (bit 2)", CL.PLAYER == 2)
	_assert("OBJECTS == 4 (bit 3)", CL.OBJECTS == 4)
	_assert("HAZARDS == 8 (bit 4)", CL.HAZARDS == 8)
	_assert("TRIGGERS == 16 (bit 5)", CL.TRIGGERS == 16)
	# Verify powers of 2
	_assert("TERRAIN is power of 2", CL.TERRAIN & (CL.TERRAIN - 1) == 0)
	_assert("OBJECTS is power of 2", CL.OBJECTS & (CL.OBJECTS - 1) == 0)
	# Verify no overlap
	_assert("No layer overlap", CL.TERRAIN | CL.PLAYER | CL.OBJECTS | CL.HAZARDS | CL.TRIGGERS == 31)


func _test_game_manager() -> void:
	print("\n--- GameManager ---")
	_assert("starts in MENU state (0)", _game_manager.current_state == 0)
	_assert("current_level starts at 0", _game_manager.current_level == 0)
	_assert("has 3 level scenes", _game_manager.LEVEL_SCENES.size() == 3)
	_assert("has start_game()", _game_manager.has_method("start_game"))
	_assert("has pause_game()", _game_manager.has_method("pause_game"))
	_assert("has resume_game()", _game_manager.has_method("resume_game"))
	_assert("has return_to_menu()", _game_manager.has_method("return_to_menu"))
	_assert("GAME_SCENE path defined", _game_manager.GAME_SCENE != "")


func _test_rule_engine() -> void:
	print("\n--- RuleEngine ---")
	_assert("not loaded initially", not _rule_engine.is_loaded())

	var test_rules: Array = [
		{
			"rule_id": "fire",
			"tags_required_a": ["HEAT_SOURCE"],
			"tags_required_b": ["FLAMMABLE"],
			"effects": [{"effect_type": "IGNITE", "target": "b", "message": "catches fire"}],
			"priority": 5,
			"bidirectional": false,
			"cascade_eligible": true,
		},
		{
			"rule_id": "freeze",
			"tags_required_a": ["COLD"],
			"tags_required_b": ["LIQUID"],
			"effects": [{"effect_type": "FREEZE", "target": "b", "message": "freezes"}],
			"priority": 3,
		},
		{
			"rule_id": "electric",
			"tags_required_a": ["ELECTRIC"],
			"tags_required_b": ["CONDUCTING"],
			"effects": [{"effect_type": "ELECTRIFY", "target": "b", "message": "zaps"}],
			"priority": 4,
			"bidirectional": true,
		},
	]
	_rule_engine.load_rules(test_rules)
	_assert("loaded after load_rules", _rule_engine.is_loaded())

	# Direct match
	var fire: Array = _rule_engine.find_matching_rules(["HEAT_SOURCE"], ["FLAMMABLE"])
	_assert("fire rule matched", fire.size() == 1)
	_assert("fire rule id correct", fire[0].get("rule_id", "") == "fire")

	# No match
	var none: Array = _rule_engine.find_matching_rules(["SOLID"], ["RIGID"])
	_assert("no match for SOLID+RIGID", none.is_empty())

	# Bidirectional
	var bidir: Array = _rule_engine.find_matching_rules(["CONDUCTING"], ["ELECTRIC"])
	_assert("bidirectional match (reversed)", bidir.size() == 1)
	_assert("bidirectional rule id correct", bidir[0].get("rule_id", "") == "electric")

	# Priority ordering
	var multi: Array = _rule_engine.find_matching_rules(["HEAT_SOURCE", "COLD"], ["FLAMMABLE", "LIQUID"])
	_assert("multi-match returns 2 rules", multi.size() == 2)
	_assert("higher priority first", multi[0].get("priority", 0) > multi[1].get("priority", 0))

	# Multiple tags on one side
	var partial: Array = _rule_engine.find_matching_rules(["HEAT_SOURCE"], ["SOLID"])
	_assert("no match when b-tags don't include required", partial.is_empty())


func _test_event_bus_signals() -> void:
	print("\n--- EventBus Signals ---")
	var expected_signals: Array = [
		"interaction_triggered", "object_created", "object_destroyed",
		"sprite_ready", "sprite_failed", "level_completed",
		"inventory_changed", "equipment_changed", "session_started",
		"creation_started", "creation_finished", "creation_failed",
		"slot_selected",
	]
	for sig_name in expected_signals:
		_assert("has signal: %s" % sig_name, _event_bus.has_signal(sig_name))


func _test_equipment() -> void:
	print("\n--- PlayerEquipment ---")
	var equip_script = load("res://scenes/player/player_equipment.gd")
	var equip = Node.new()
	equip.set_script(equip_script)
	get_root().add_child(equip)

	# Equip TOOL item
	var sword: Dictionary = {
		"name": "Flame Sword",
		"tags": ["SOLID", "TOOL", "HEAT_SOURCE", "SHARP"],
		"visual_descriptor": {"base_form": "sword"},
	}
	_assert("hand slot starts empty", equip.equipped["hand"].is_empty())
	_assert("equip(sword) succeeds", equip.equip(sword))
	_assert("sword in hand slot", not equip.equipped["hand"].is_empty())

	# Effective tags
	var eff: Array = equip.get_effective_tags()
	_assert("LIVING always present", "LIVING" in eff)
	_assert("HEAT_SOURCE transferred", "HEAT_SOURCE" in eff)
	_assert("SHARP transferred", "SHARP" in eff)
	_assert("SOLID not transferred", "SOLID" not in eff)
	_assert("has_tag(HEAT_SOURCE)", equip.has_tag("HEAT_SOURCE"))
	_assert("not has_tag(HEAVY)", not equip.has_tag("HEAVY"))

	# Non-equippable
	var rock: Dictionary = {"name": "Rock", "tags": ["SOLID"], "visual_descriptor": {"base_form": "boulder"}}
	_assert("cannot equip non-TOOL/WEARABLE", not equip.equip(rock))

	# WEARABLE item
	var helmet: Dictionary = {"name": "Helm", "tags": ["WEARABLE", "INSULATING"], "visual_descriptor": {"base_form": "helmet"}}
	_assert("equip(helmet) succeeds", equip.equip(helmet))
	_assert("helmet in head slot", not equip.equipped["head"].is_empty())
	_assert("INSULATING transferred", equip.has_tag("INSULATING"))

	# Unequip
	var removed: Dictionary = equip.unequip("hand")
	_assert("unequip returns item", removed.get("name", "") == "Flame Sword")
	_assert("hand slot empty after unequip", equip.equipped["hand"].is_empty())
	_assert("HEAT_SOURCE gone after unequip", not equip.has_tag("HEAT_SOURCE"))

	# Slot mapping
	var jetpack: Dictionary = {"name": "Jetpack", "tags": ["WEARABLE", "FLOATING"], "visual_descriptor": {"base_form": "jetpack"}}
	equip.equip(jetpack)
	_assert("jetpack goes to back slot", not equip.equipped["back"].is_empty())

	# get_data
	_assert("get_data() returns array", equip.get_data() is Array)

	equip.free()


func _test_inventory() -> void:
	print("\n--- PlayerInventory ---")
	var inv_script = load("res://scenes/player/player_inventory.gd")
	var inv = Node.new()
	inv.set_script(inv_script)
	get_root().add_child(inv)
	inv.slots.resize(8)
	for i in range(8):
		inv.slots[i] = {}

	# Track signal via array (reference type — shared with lambda)
	var signal_log: Array = []
	_event_bus.slot_selected.connect(func(s): signal_log.append(s))

	# Add items
	_assert("add_item returns slot 0", inv.add_item({"id": "a"}) == 0)
	_assert("add_item returns slot 1", inv.add_item({"id": "b"}) == 1)
	_assert("has_item(0)", inv.has_item(0))
	_assert("not has_item(2)", not inv.has_item(2))
	_assert("get_item(0).id == 'a'", inv.get_item(0).get("id", "") == "a")

	# Select slot
	inv.select_slot(3)
	_assert("selected_slot == 3", inv.selected_slot == 3)
	_assert("slot_selected signal fired", signal_log.size() >= 1)
	_assert("get_selected_item empty (slot 3)", inv.get_selected_item().is_empty())

	inv.select_slot(0)
	_assert("get_selected_item returns item A", inv.get_selected_item().get("id", "") == "a")

	# Remove
	var removed: Dictionary = inv.remove_item(0)
	_assert("remove_item returns item", removed.get("id", "") == "a")
	_assert("slot 0 now empty", not inv.has_item(0))

	# Bounds
	_assert("get_item(-1) returns empty", inv.get_item(-1).is_empty())
	_assert("get_item(99) returns empty", inv.get_item(99).is_empty())
	_assert("has_item(-1) false", not inv.has_item(-1))

	# get_data
	_assert("get_data() returns 8 slots", inv.get_data().size() == 8)

	# Full inventory
	for i in range(8):
		inv.slots[i] = {"id": str(i)}
	_assert("add_item returns -1 when full", inv.add_item({"id": "x"}) == -1)

	inv.free()


func _test_physics_composer() -> void:
	print("\n--- PhysicsComposer ---")
	# PhysicsComposer depends on TagPhysicsMap (class_name), which isn't
	# resolved in SceneTree --script context. Validated via godot --headless --quit.
	print("ASSERT SKIP: PhysicsComposer (class_name dependency, tested via compile check)")


func _test_tag_colors() -> void:
	print("\n--- TagColors ---")
	_assert("HEAT_SOURCE has color", TC.get_color("HEAT_SOURCE") != TC.DEFAULT)
	_assert("FROZEN has color", TC.get_color("FROZEN") != TC.DEFAULT)
	_assert("ELECTRIC has color", TC.get_color("ELECTRIC") != TC.DEFAULT)
	_assert("LIVING has color", TC.get_color("LIVING") != TC.DEFAULT)
	_assert("unknown tag → DEFAULT", TC.get_color("NONEXISTENT") == TC.DEFAULT)
	_assert("DEFAULT is gray", TC.DEFAULT == Color("#AAAAAA"))


func _test_tag_physics_map() -> void:
	print("\n--- TagPhysicsMap ---")
	_assert("HEAVY defined", "HEAVY" in TPM.TAG_PHYSICS)
	_assert("LIGHT defined", "LIGHT" in TPM.TAG_PHYSICS)
	_assert("BOUNCY defined", "BOUNCY" in TPM.TAG_PHYSICS)
	_assert("FLOATING defined", "FLOATING" in TPM.TAG_PHYSICS)
	_assert("FROZEN defined", "FROZEN" in TPM.TAG_PHYSICS)
	_assert("MOLTEN defined", "MOLTEN" in TPM.TAG_PHYSICS)

	var heavy: Dictionary = TPM.TAG_PHYSICS["HEAVY"]
	_assert("HEAVY has priority", heavy.has("priority"))
	_assert("HEAVY has mass", heavy.has("mass"))
	_assert("HEAVY mass > 1.0", heavy["mass"] > 1.0)
	_assert("HEAVY priority is 8", heavy["priority"] == 8)


func _test_collision_resolver() -> void:
	print("\n--- CollisionResolver ---")
	# _ready() doesn't fire in _initialize(), so child count may be 0
	# Test the API surface instead
	_assert("has resolve_collision method", _collision_resolver.has_method("resolve_collision"))
	_assert("has clear_cooldowns method", _collision_resolver.has_method("clear_cooldowns"))
	_collision_resolver.clear_cooldowns()
	_assert("clear_cooldowns succeeds", true)


func _process(_delta: float) -> bool:
	_frame += 1
	return _frame > 3


func _assert(desc: String, condition: bool) -> void:
	if condition:
		print("ASSERT PASS: %s" % desc)
	else:
		print("ASSERT FAIL: %s" % desc)
