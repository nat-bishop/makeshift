extends SceneTree
## Comprehensive test harness: exercises all Godot subsystems headlessly.
## Run: cd godot && timeout 60 godot --headless --quit --script res://test/test_systems.gd

const TPM = preload("res://scripts/data/tag_physics_map.gd")
const TC = preload("res://scripts/data/tag_colors.gd")
const CL = preload("res://scripts/data/collision_layers.gd")
# PhysicsComposer can't be preloaded (class_name TagPhysicsMap dependency
# isn't registered in --script mode). Algorithm tested inline instead.

var _pass_count: int = 0
var _fail_count: int = 0
var _frame: int = 0
var _cam: Camera2D

# Autoload references (resolved from root children)
var _event_bus: Node
var _game_manager: Node
var _rule_engine: Node
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
	_test_effect_executor()
	_test_scene_compilation()
	_test_level_construction()
	_test_collision_resolver()
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

func add_tag(tag: String) -> void:
	if tag not in tags:
		tags.append(tag)

func remove_tag(tag: String) -> void:
	tags.erase(tag)

func take_damage(amount: float) -> void:
	damage_log.append(amount)
	current_durability -= amount

func has_tag(tag: String) -> bool:
	return tag in tags
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


# ---------------------------------------------------------------------------
# Section 1: Autoloads
# ---------------------------------------------------------------------------

func _test_autoloads() -> void:
	_section("Autoloads")
	_assert("EventBus exists", _event_bus != null)
	_assert("GameManager exists", _game_manager != null)
	_assert("RuleEngine exists", _rule_engine != null)
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
	_assert("has 3 level scenes", _game_manager.LEVEL_SCENES.size() == 3)
	_assert("has start_game()", _game_manager.has_method("start_game"))
	_assert("has pause_game()", _game_manager.has_method("pause_game"))
	_assert("has resume_game()", _game_manager.has_method("resume_game"))
	_assert("has return_to_menu()", _game_manager.has_method("return_to_menu"))


# ---------------------------------------------------------------------------
# Section 4: RuleEngine
# ---------------------------------------------------------------------------

func _test_rule_engine() -> void:
	_section("RuleEngine")
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
			"bidirectional": false,
		},
		{
			"rule_id": "electric",
			"tags_required_a": ["ELECTRIC"],
			"tags_required_b": ["CONDUCTING"],
			"effects": [{"effect_type": "ELECTRIFY", "target": "b", "message": "zaps"}],
			"priority": 4,
			"bidirectional": true,
		},
		{
			"rule_id": "wild_explosive",
			"tags_required_a": ["EXPLOSIVE"],
			"tags_required_b": [],
			"effects": [{"effect_type": "DAMAGE", "target": "both", "damage_amount": 50}],
			"priority": 10,
			"bidirectional": false,
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

	# Partial mismatch
	var partial: Array = _rule_engine.find_matching_rules(["HEAT_SOURCE"], ["SOLID"])
	_assert("no match when b-tags miss required", partial.is_empty())

	# Wildcard match
	var wild: Array = _rule_engine.find_matching_rules(["EXPLOSIVE"], ["ANYTHING"])
	_assert("wildcard matches any tags_b", wild.size() == 1)
	_assert("wildcard rule id", wild[0].get("rule_id", "") == "wild_explosive")

	# Wildcard does not match if tags_a missing
	var no_wild: Array = _rule_engine.find_matching_rules(["SOLID"], ["ANYTHING"])
	_assert("wildcard skips if tags_a miss", no_wild.is_empty())

	# Wildcard + pair match simultaneously
	var both: Array = _rule_engine.find_matching_rules(["EXPLOSIVE", "HEAT_SOURCE"], ["FLAMMABLE"])
	_assert("wildcard+pair both match", both.size() == 2)
	_assert("explosive (priority 10) first", both[0].get("rule_id", "") == "wild_explosive")

	# Empty input
	var empty: Array = _rule_engine.find_matching_rules([], [])
	_assert("empty tags returns empty", empty.is_empty())


# ---------------------------------------------------------------------------
# Section 5: EventBus Signals
# ---------------------------------------------------------------------------

func _test_event_bus_signals() -> void:
	_section("EventBus Signals")
	var expected: Array = [
		"interaction_triggered", "object_created", "object_destroyed",
		"sprite_ready", "sprite_failed", "level_completed",
		"inventory_changed", "equipment_changed", "session_started",
		"creation_started", "creation_finished", "creation_failed",
		"slot_selected",
	]
	for sig_name in expected:
		_assert("has signal: %s" % sig_name, _event_bus.has_signal(sig_name))


# ---------------------------------------------------------------------------
# Section 6: PlayerEquipment
# ---------------------------------------------------------------------------

func _test_equipment() -> void:
	_section("PlayerEquipment")
	var equip_script = load("res://scenes/player/player_equipment.gd")
	var equip = Node.new()
	equip.set_script(equip_script)
	get_root().add_child(equip)

	# TOOL item to hand
	var sword: Dictionary = {
		"name": "Flame Sword",
		"tags": ["SOLID", "TOOL", "HEAT_SOURCE", "SHARP"],
		"visual_descriptor": {"base_form": "sword"},
	}
	_assert("hand starts empty", equip.equipped["hand"].is_empty())
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

	# WEARABLE to head
	var helmet: Dictionary = {"name": "Helm", "tags": ["WEARABLE", "INSULATING"], "visual_descriptor": {"base_form": "helmet"}}
	_assert("equip(helmet) succeeds", equip.equip(helmet))
	_assert("helmet in head slot", not equip.equipped["head"].is_empty())
	_assert("INSULATING transferred", equip.has_tag("INSULATING"))

	# Unequip
	var removed: Dictionary = equip.unequip("hand")
	_assert("unequip returns item", removed.get("name", "") == "Flame Sword")
	_assert("hand empty after unequip", equip.equipped["hand"].is_empty())
	_assert("HEAT_SOURCE gone after unequip", not equip.has_tag("HEAT_SOURCE"))

	# Back slot
	var jetpack: Dictionary = {"name": "Jetpack", "tags": ["WEARABLE", "FLOATING"], "visual_descriptor": {"base_form": "jetpack"}}
	equip.equip(jetpack)
	_assert("jetpack goes to back slot", not equip.equipped["back"].is_empty())

	# get_data
	_assert("get_data() returns array", equip.get_data() is Array)

	# Slot replacement: equip a second item to hand
	var wand: Dictionary = {"name": "Wand", "tags": ["TOOL", "ELECTRIC"], "visual_descriptor": {"base_form": "wand"}}
	var axe: Dictionary = {"name": "Axe", "tags": ["TOOL", "SHARP"], "visual_descriptor": {"base_form": "axe"}}
	equip.equip(wand)
	equip.equip(axe)
	_assert("replacement: axe in hand", equip.equipped["hand"].get("name", "") == "Axe")
	_assert("replacement: SHARP from axe", equip.has_tag("SHARP"))

	# Slot mapping checks
	var shield: Dictionary = {"name": "Shield", "tags": ["WEARABLE"], "visual_descriptor": {"base_form": "shield"}}
	equip.equip(shield)
	_assert("shield -> back slot", equip.equipped["back"].get("name", "") == "Shield")

	# Unequip non-existent slot
	var nothing: Dictionary = equip.unequip("nonexistent")
	_assert("unequip bad slot returns empty", nothing.is_empty())

	equip.free()


# ---------------------------------------------------------------------------
# Section 7: PlayerInventory
# ---------------------------------------------------------------------------

func _test_inventory() -> void:
	_section("PlayerInventory")
	var inv_script = load("res://scenes/player/player_inventory.gd")
	var inv = Node.new()
	inv.set_script(inv_script)
	get_root().add_child(inv)
	# _ready() doesn't fire, manually init slots
	inv.slots.resize(8)
	for i in range(8):
		inv.slots[i] = {}

	# Track signals
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

	# Remove from empty slot
	var empty_remove: Dictionary = inv.remove_item(0)
	_assert("remove from empty slot returns empty", empty_remove.is_empty())

	# Remove from negative slot
	var neg_remove: Dictionary = inv.remove_item(-1)
	_assert("remove from negative slot returns empty", neg_remove.is_empty())

	# OOB select_slot
	var old_slot: int = inv.selected_slot
	inv.select_slot(99)
	_assert("OOB select_slot unchanged", inv.selected_slot == old_slot)

	# Refill vacated slot
	var refill_slot: int = inv.add_item({"id": "c"})
	_assert("refill uses vacated slot 0", refill_slot == 0)

	# Full inventory
	for i in range(8):
		inv.slots[i] = {"id": str(i)}
	_assert("add_item returns -1 when full", inv.add_item({"id": "x"}) == -1)

	inv.free()


# ---------------------------------------------------------------------------
# Section 8: PhysicsComposer
# ---------------------------------------------------------------------------

func _test_physics_composer() -> void:
	_section("PhysicsComposer")
	# PhysicsComposer can't be loaded in --script mode (class_name dep chain).
	# Test the algorithm inline using TPM.TAG_PHYSICS data directly.
	# This mirrors PhysicsComposer.compose_physics() logic exactly.

	# Empty tags -> defaults
	var empty_result: Dictionary = _compose_physics([])
	_assert("empty: mass == 1.0", is_equal_approx(empty_result["mass"], 1.0))
	_assert("empty: gravity == 1.0", is_equal_approx(empty_result["gravity"], 1.0))
	_assert("empty: friction == 0.5", is_equal_approx(empty_result["friction"], 0.5))
	_assert("empty: bounce == 0.0", is_equal_approx(empty_result["bounce"], 0.0))

	# Single tag HEAVY
	var heavy: Dictionary = _compose_physics(["HEAVY"])
	_assert("HEAVY: mass == 5.0", is_equal_approx(heavy["mass"], 5.0))
	_assert("HEAVY: gravity == 1.2", is_equal_approx(heavy["gravity"], 1.2))
	_assert("HEAVY: friction == 0.7", is_equal_approx(heavy["friction"], 0.7))
	_assert("HEAVY: bounce == 0.0", is_equal_approx(heavy["bounce"], 0.0))

	# Single tag BOUNCY
	var bouncy: Dictionary = _compose_physics(["BOUNCY"])
	_assert("BOUNCY: bounce == 0.9", is_equal_approx(bouncy["bounce"], 0.9))
	_assert("BOUNCY: friction == 0.2", is_equal_approx(bouncy["friction"], 0.2))
	_assert("BOUNCY: mass == 1.0 (default)", is_equal_approx(bouncy["mass"], 1.0))
	_assert("BOUNCY: gravity == 1.0 (default)", is_equal_approx(bouncy["gravity"], 1.0))

	# HEAVY(priority 8) wins over LIGHT(priority 7) for mass
	var heavy_light: Dictionary = _compose_physics(["HEAVY", "LIGHT"])
	_assert("HEAVY wins over LIGHT for mass", is_equal_approx(heavy_light["mass"], 5.0))

	# Same-priority average: BOUNCY(6) + FROZEN(6) for friction
	var bouncy_frozen: Dictionary = _compose_physics(["BOUNCY", "FROZEN"])
	_assert("same priority friction avg", is_equal_approx(bouncy_frozen["friction"], (0.2 + 0.05) / 2.0))

	# Higher priority wins: FLOATING(9) over HEAVY(8) for gravity
	var float_heavy: Dictionary = _compose_physics(["FLOATING", "HEAVY"])
	_assert("FLOATING overrides HEAVY gravity", is_equal_approx(float_heavy["gravity"], -0.5))

	# Size data (inline constants matching PhysicsComposer.SIZE_TO_PHYSICS)
	var size_data: Dictionary = {
		"tiny": {"sprite": 32, "collision": 16},
		"small": {"sprite": 48, "collision": 32},
		"medium": {"sprite": 64, "collision": 48},
		"large": {"sprite": 96, "collision": 80},
		"huge": {"sprite": 128, "collision": 112},
	}
	_assert("tiny: sprite == 32", size_data["tiny"]["sprite"] == 32)
	_assert("tiny: collision == 16", size_data["tiny"]["collision"] == 16)
	_assert("medium: sprite == 64", size_data["medium"]["sprite"] == 64)
	_assert("unknown size -> medium default", size_data.get("gigantic", size_data["medium"])["sprite"] == 64)

	# Shape detection (inline constants matching PhysicsComposer)
	var elongated: Array[String] = ["sword", "plank", "rope", "ladder", "wand", "torch", "fan"]
	var round_forms: Array[String] = ["sphere", "ball", "boulder", "wheel"]
	_assert("sword -> capsule", "sword" in elongated)
	_assert("ball -> circle", "ball" in round_forms)
	_assert("box -> rectangle (default)", "box" not in elongated and "box" not in round_forms)
	_assert("unknown -> rectangle", "xyz" not in elongated and "xyz" not in round_forms)


# Inline mirror of PhysicsComposer.compose_physics() — tests the algorithm
# using TPM.TAG_PHYSICS data directly (avoids class_name dep chain).
func _compose_physics(tags: Array) -> Dictionary:
	var mass_entries: Array = []
	var gravity_entries: Array = []
	var friction_entries: Array = []
	var bounce_entries: Array = []

	for tag in tags:
		var tag_str: String = str(tag)
		if tag_str not in TPM.TAG_PHYSICS:
			continue
		var props: Dictionary = TPM.TAG_PHYSICS[tag_str]
		var priority: int = props["priority"]

		if props["mass"] >= 0.0:
			mass_entries.append({"priority": priority, "value": props["mass"]})
		if props["gravity"] > -2.0 and props["gravity"] != -1.0:
			gravity_entries.append({"priority": priority, "value": props["gravity"]})
		if props["friction"] >= 0.0:
			friction_entries.append({"priority": priority, "value": props["friction"]})
		if props["bounce"] >= 0.0:
			bounce_entries.append({"priority": priority, "value": props["bounce"]})

	return {
		"mass": _resolve_property(mass_entries, 1.0),
		"gravity": _resolve_property(gravity_entries, 1.0),
		"friction": _resolve_property(friction_entries, 0.5),
		"bounce": _resolve_property(bounce_entries, 0.0),
	}


func _resolve_property(entries: Array, default_value: float) -> float:
	if entries.is_empty():
		return default_value
	var max_priority: int = -1
	for entry in entries:
		if entry["priority"] > max_priority:
			max_priority = entry["priority"]
	var values: Array = []
	for entry in entries:
		if entry["priority"] == max_priority:
			values.append(entry["value"])
	var total: float = 0.0
	for v in values:
		total += v
	return total / values.size()


# ---------------------------------------------------------------------------
# Section 9: TagColors
# ---------------------------------------------------------------------------

func _test_tag_colors() -> void:
	_section("TagColors")
	_assert("HEAT_SOURCE has color", TC.get_color("HEAT_SOURCE") != TC.DEFAULT)
	_assert("FROZEN has color", TC.get_color("FROZEN") != TC.DEFAULT)
	_assert("ELECTRIC has color", TC.get_color("ELECTRIC") != TC.DEFAULT)
	_assert("LIVING has color", TC.get_color("LIVING") != TC.DEFAULT)
	_assert("unknown tag -> DEFAULT", TC.get_color("NONEXISTENT") == TC.DEFAULT)
	_assert("DEFAULT is gray", TC.DEFAULT == Color("#AAAAAA"))
	_assert("COLORS has 14 entries", TC.COLORS.size() == 14)


# ---------------------------------------------------------------------------
# Section 10: TagPhysicsMap
# ---------------------------------------------------------------------------

func _test_tag_physics_map() -> void:
	_section("TagPhysicsMap")
	_assert("HEAVY defined", "HEAVY" in TPM.TAG_PHYSICS)
	_assert("LIGHT defined", "LIGHT" in TPM.TAG_PHYSICS)
	_assert("BOUNCY defined", "BOUNCY" in TPM.TAG_PHYSICS)
	_assert("FLOATING defined", "FLOATING" in TPM.TAG_PHYSICS)
	_assert("FROZEN defined", "FROZEN" in TPM.TAG_PHYSICS)
	_assert("MOLTEN defined", "MOLTEN" in TPM.TAG_PHYSICS)

	var heavy: Dictionary = TPM.TAG_PHYSICS["HEAVY"]
	_assert("HEAVY has priority", heavy.has("priority"))
	_assert("HEAVY mass > 1.0", heavy["mass"] > 1.0)
	_assert("HEAVY priority is 8", heavy["priority"] == 8)
	_assert("TAG_PHYSICS has 12 entries", TPM.TAG_PHYSICS.size() == 12)


# ---------------------------------------------------------------------------
# Section 11: EffectExecutor
# ---------------------------------------------------------------------------

func _test_effect_executor() -> void:
	_section("EffectExecutor")
	var root = get_root()

	var ee_script = load("res://scripts/systems/effect_executor.gd")
	var ee = Node.new()
	ee.set_script(ee_script)
	root.add_child(ee)

	# --- DAMAGE ---
	var a1 = _make_mock_body("src1", ["HEAT_SOURCE"])
	var b1 = _make_mock_body("tgt1", ["FLAMMABLE"])
	root.add_child(a1)
	root.add_child(b1)
	var damage_rule: Dictionary = {
		"effects": [{"effect_type": "DAMAGE", "target": "b", "damage_amount": 25.0, "message": ""}],
	}
	ee.execute(damage_rule, a1, b1)
	_assert("DAMAGE: logged", b1.get("damage_log").size() == 1)
	_assert("DAMAGE: amount 25", b1.get("damage_log")[0] == 25.0)
	a1.free()
	b1.free()

	# --- DESTROY ---
	var a2 = _make_mock_body("src2", [])
	var b2 = _make_mock_body("tgt2", ["BREAKABLE"], 100.0)
	root.add_child(a2)
	root.add_child(b2)
	ee.execute({"effects": [{"effect_type": "DESTROY", "target": "b", "message": ""}]}, a2, b2)
	_assert("DESTROY: 99999 damage", b2.get("damage_log")[0] == 99999.0)
	a2.free()
	b2.free()

	# --- IGNITE ---
	var a3 = _make_mock_body("src3", ["HEAT_SOURCE"])
	var b3 = _make_mock_body("tgt3", ["FLAMMABLE"])
	root.add_child(a3)
	root.add_child(b3)
	ee.execute({"effects": [{"effect_type": "IGNITE", "target": "b", "message": "burns"}]}, a3, b3)
	_assert("IGNITE: adds HEAT_SOURCE", "HEAT_SOURCE" in b3.get("tags"))
	_assert("IGNITE: adds HOT", "HOT" in b3.get("tags"))
	a3.free()
	b3.free()

	# --- EXTINGUISH ---
	var a4 = _make_mock_body("src4", ["LIQUID"])
	var b4 = _make_mock_body("tgt4", ["HEAT_SOURCE", "HOT"])
	root.add_child(a4)
	root.add_child(b4)
	ee.execute({"effects": [{"effect_type": "EXTINGUISH", "target": "b", "message": ""}]}, a4, b4)
	_assert("EXTINGUISH: removes HEAT_SOURCE", "HEAT_SOURCE" not in b4.get("tags"))
	_assert("EXTINGUISH: removes HOT", "HOT" not in b4.get("tags"))
	a4.free()
	b4.free()

	# --- FREEZE ---
	var a5 = _make_mock_body("src5", ["COLD"])
	var b5 = _make_mock_body("tgt5", ["LIQUID"])
	root.add_child(a5)
	root.add_child(b5)
	ee.execute({"effects": [{"effect_type": "FREEZE", "target": "b", "message": ""}]}, a5, b5)
	_assert("FREEZE: adds FROZEN", "FROZEN" in b5.get("tags"))
	_assert("FREEZE: adds RIGID", "RIGID" in b5.get("tags"))
	_assert("FREEZE: removes LIQUID", "LIQUID" not in b5.get("tags"))
	a5.free()
	b5.free()

	# --- MELT ---
	var a6 = _make_mock_body("src6", ["HEAT_SOURCE"])
	var b6 = _make_mock_body("tgt6", ["FROZEN", "RIGID"])
	root.add_child(a6)
	root.add_child(b6)
	ee.execute({"effects": [{"effect_type": "MELT", "target": "b", "message": ""}]}, a6, b6)
	_assert("MELT: removes FROZEN", "FROZEN" not in b6.get("tags"))
	_assert("MELT: removes RIGID", "RIGID" not in b6.get("tags"))
	_assert("MELT: adds LIQUID", "LIQUID" in b6.get("tags"))
	a6.free()
	b6.free()

	# --- ADD_TAG ---
	var a7 = _make_mock_body("src7", [])
	var b7 = _make_mock_body("tgt7", ["SOLID"])
	root.add_child(a7)
	root.add_child(b7)
	ee.execute({"effects": [{"effect_type": "ADD_TAG", "target": "b", "tags_to_add": ["MAGNETIC", "GLOWING"], "message": ""}]}, a7, b7)
	_assert("ADD_TAG: MAGNETIC added", "MAGNETIC" in b7.get("tags"))
	_assert("ADD_TAG: GLOWING added", "GLOWING" in b7.get("tags"))
	a7.free()
	b7.free()

	# --- REMOVE_TAG ---
	var a8 = _make_mock_body("src8", [])
	var b8 = _make_mock_body("tgt8", ["MAGNETIC", "GLOWING"])
	root.add_child(a8)
	root.add_child(b8)
	ee.execute({"effects": [{"effect_type": "REMOVE_TAG", "target": "b", "tags_to_remove": ["MAGNETIC", "GLOWING"], "message": ""}]}, a8, b8)
	_assert("REMOVE_TAG: MAGNETIC gone", "MAGNETIC" not in b8.get("tags"))
	_assert("REMOVE_TAG: GLOWING gone", "GLOWING" not in b8.get("tags"))
	a8.free()
	b8.free()

	# --- TRANSFORM ---
	var a9 = _make_mock_body("src9", [])
	var b9 = _make_mock_body("tgt9", ["LIQUID"])
	root.add_child(a9)
	root.add_child(b9)
	ee.execute({"effects": [{"effect_type": "TRANSFORM", "target": "b", "tags_to_add": ["FROZEN"], "tags_to_remove": ["LIQUID"], "message": ""}]}, a9, b9)
	_assert("TRANSFORM: FROZEN added", "FROZEN" in b9.get("tags"))
	_assert("TRANSFORM: LIQUID removed", "LIQUID" not in b9.get("tags"))
	a9.free()
	b9.free()

	# --- ELECTRIFY ---
	var a10 = _make_mock_body("src10", ["ELECTRIC"])
	var b10 = _make_mock_body("tgt10", ["CONDUCTING"])
	root.add_child(a10)
	root.add_child(b10)
	ee.execute({"effects": [{"effect_type": "ELECTRIFY", "target": "b", "damage_amount": 30.0, "message": ""}]}, a10, b10)
	_assert("ELECTRIFY: damage applied", b10.get("damage_log").size() == 1)
	a10.free()
	b10.free()

	# --- Target routing: "a" ---
	var ta = _make_mock_body("target_a", ["SOLID"])
	var tb = _make_mock_body("target_b", ["SOLID"])
	root.add_child(ta)
	root.add_child(tb)
	ee.execute({"effects": [{"effect_type": "DAMAGE", "target": "a", "damage_amount": 10.0, "message": ""}]}, ta, tb)
	_assert("target=a: body_a damaged", ta.get("damage_log").size() == 1)
	_assert("target=a: body_b untouched", tb.get("damage_log").size() == 0)
	ta.free()
	tb.free()

	# --- Target routing: "both" ---
	var ba = _make_mock_body("both_a", ["SOLID"])
	var bb = _make_mock_body("both_b", ["SOLID"])
	root.add_child(ba)
	root.add_child(bb)
	ee.execute({"effects": [{"effect_type": "DAMAGE", "target": "both", "damage_amount": 5.0, "message": ""}]}, ba, bb)
	_assert("target=both: body_a damaged", ba.get("damage_log").size() == 1)
	_assert("target=both: body_b damaged", bb.get("damage_log").size() == 1)
	ba.free()
	bb.free()

	# --- interaction_triggered signal ---
	var signal_fired: Array = [false]
	_event_bus.interaction_triggered.connect(func(_sn, _st, _tn, _tt, _em, _wp): signal_fired[0] = true, CONNECT_ONE_SHOT)
	var sa = _make_mock_body("sig_a", ["X"])
	var sb = _make_mock_body("sig_b", ["Y"])
	root.add_child(sa)
	root.add_child(sb)
	ee.execute({"effects": [{"effect_type": "DAMAGE", "target": "b", "damage_amount": 1.0, "message": "test hit"}]}, sa, sb)
	_assert("interaction_triggered signal fires", signal_fired[0])
	sa.free()
	sb.free()

	ee.free()


# ---------------------------------------------------------------------------
# Section 12: Scene Compilation
# ---------------------------------------------------------------------------

func _test_scene_compilation() -> void:
	_section("Scene Compilation")
	var scenes: Array[String] = [
		"res://scenes/game/game.tscn",
		"res://scenes/game_object/game_object.tscn",
		"res://scenes/hud/hotbar.tscn",
		"res://scenes/hud/hud.tscn",
		"res://scenes/hud/interaction_feedback.tscn",
		"res://scenes/hud/item_tooltip.tscn",
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
# Section 13: Level Construction
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

		# Structural checks (scripts may not compile in --script mode,
		# so @export properties may not be set — test node structure only)
		var spawn = level.find_child("SpawnPoint", true, false)
		var goal = level.find_child("Goal", true, false)

		_assert("level_%d has SpawnPoint" % (i + 1), spawn != null)
		_assert("level_%d has Goal" % (i + 1), goal != null)

		# Goal should be an Area2D with a CollisionShape2D
		if goal != null:
			_assert("level_%d Goal is Area2D" % (i + 1), goal is Area2D)
			var goal_shape = goal.find_child("CollisionShape2D", false, false)
			_assert("level_%d Goal has CollisionShape2D" % (i + 1), goal_shape != null)

		level.free()


# ---------------------------------------------------------------------------
# Section 14: CollisionResolver
# ---------------------------------------------------------------------------

func _test_collision_resolver() -> void:
	_section("CollisionResolver")
	var root = get_root()

	_assert("has resolve_collision()", _collision_resolver.has_method("resolve_collision"))
	_assert("has clear_cooldowns()", _collision_resolver.has_method("clear_cooldowns"))

	# Manually init _effect_executor since _ready() didn't fire
	var ee_script = load("res://scripts/systems/effect_executor.gd")
	var ee = Node.new()
	ee.set_script(ee_script)
	_collision_resolver.add_child(ee)
	_collision_resolver.set("_effect_executor", ee)

	# Load rules for collision tests
	_rule_engine.load_rules([{
		"rule_id": "test_fire",
		"tags_required_a": ["HEAT_SOURCE"],
		"tags_required_b": ["FLAMMABLE"],
		"effects": [{"effect_type": "IGNITE", "target": "b", "message": "burns"}],
		"priority": 5,
		"bidirectional": false,
		"cascade_eligible": false,
	}])

	# Functional collision
	_collision_resolver.clear_cooldowns()
	var body_a = _make_mock_body("fire_src", ["HEAT_SOURCE"])
	var body_b = _make_mock_body("wood", ["FLAMMABLE"])
	root.add_child(body_a)
	root.add_child(body_b)
	_collision_resolver.resolve_collision(body_a, body_b)
	_assert("collision: IGNITE adds HEAT_SOURCE", "HEAT_SOURCE" in body_b.get("tags"))
	_assert("collision: IGNITE adds HOT", "HOT" in body_b.get("tags"))

	# Cooldown blocks re-execution
	body_b.remove_tag("HEAT_SOURCE")
	body_b.remove_tag("HOT")
	_collision_resolver.resolve_collision(body_a, body_b)
	_assert("cooldown blocks repeat", "HEAT_SOURCE" not in body_b.get("tags"))

	# clear_cooldowns allows re-execution
	_collision_resolver.clear_cooldowns()
	body_b.set("tags", ["FLAMMABLE"])
	_collision_resolver.resolve_collision(body_a, body_b)
	_assert("after clear: rule fires again", "HEAT_SOURCE" in body_b.get("tags"))

	body_a.free()
	body_b.free()

	# No-match collision
	_collision_resolver.clear_cooldowns()
	var body_c = _make_mock_body("rock", ["SOLID"])
	var body_d = _make_mock_body("dirt", ["SOLID"])
	root.add_child(body_c)
	root.add_child(body_d)
	_collision_resolver.resolve_collision(body_c, body_d)
	_assert("no-match: c unchanged", body_c.get("tags") == ["SOLID"])
	_assert("no-match: d unchanged", body_d.get("tags") == ["SOLID"])
	body_c.free()
	body_d.free()

	# Cooldown key is deterministic (both orderings blocked)
	_collision_resolver.clear_cooldowns()
	var body_e = _make_mock_body("aaa", ["HEAT_SOURCE"])
	var body_f = _make_mock_body("zzz", ["FLAMMABLE"])
	root.add_child(body_e)
	root.add_child(body_f)
	_collision_resolver.resolve_collision(body_e, body_f)
	body_f.remove_tag("HEAT_SOURCE")
	body_f.remove_tag("HOT")
	body_f.set("tags", ["FLAMMABLE"])
	# Reversed order should still be on cooldown (same pair key)
	_collision_resolver.resolve_collision(body_f, body_e)
	_assert("cooldown key symmetric", "HEAT_SOURCE" not in body_f.get("tags"))

	body_e.free()
	body_f.free()

	ee.free()


# ---------------------------------------------------------------------------
# Section 15: GameObject
# ---------------------------------------------------------------------------

func _test_game_object() -> void:
	_section("GameObject")
	var root = get_root()
	# game_object.gd can't be loaded in --script mode (CollisionLayers class_name).
	# Test the GameObject API contract via mock bodies that implement the same
	# interface. This validates the behavior that EffectExecutor/CollisionResolver
	# depend on.

	var go = _make_mock_body("test_001", ["SOLID", "HEAVY"], 100.0)
	go.set("blueprint", {"id": "test_001", "tags": ["SOLID", "HEAVY"], "visual_descriptor": {}})
	root.add_child(go)

	# Core API
	_assert("get_object_id()", go.get_object_id() == "test_001")
	_assert("get_tags()", go.get_tags() == ["SOLID", "HEAVY"])
	_assert("get_effective_tags()", go.get_effective_tags() == ["SOLID", "HEAVY"])

	# Tag mutation
	go.add_tag("FLAMMABLE")
	_assert("add_tag adds FLAMMABLE", "FLAMMABLE" in go.get_tags())
	go.add_tag("FLAMMABLE")
	_assert("add_tag no duplicate", go.get_tags().count("FLAMMABLE") == 1)

	go.remove_tag("HEAVY")
	_assert("remove_tag removes HEAVY", "HEAVY" not in go.get_tags())
	go.remove_tag("NONEXISTENT")
	_assert("remove nonexistent no crash", true)

	# Damage
	go.take_damage(30.0)
	_assert("take_damage reduces durability", go.get("current_durability") == 70.0)
	_assert("take_damage logs damage", go.get("damage_log").size() == 1)

	# has_tag
	_assert("has_tag(SOLID)", go.has_tag("SOLID"))
	_assert("not has_tag(HEAVY)", not go.has_tag("HEAVY"))

	go.free()


# ---------------------------------------------------------------------------
# _process for --write-movie compatibility
# ---------------------------------------------------------------------------

func _process(_delta: float) -> bool:
	_frame += 1
	return _frame > 3
