extends PanelContainer
## Debug overlay: name, id, HP, durability, affordance, physics, field,
## destruction, states, and creature behavior with live target tracking.

const COL_BRIGHT := Color(1.0, 1.0, 1.0, 0.95)
const COL_MID := Color(0.75, 0.75, 0.75, 0.85)
const COL_DIM := Color(0.55, 0.55, 0.55, 0.7)
const COL_BEHAVIOR := Color(0.95, 0.85, 0.5, 0.9)

const DUR_NAMES: Array[String] = [
	"fragile", "weak", "normal", "tough", "hardy", "fortified", "indestructible"
]
const AFF_NAMES: Array[String] = ["carry", "mount", "climb", "none"]
const SURFACE_NAMES: Array[String] = ["slip", "norm", "grip"]
const SPEED_NAMES: Array[String] = ["slug", "slow", "norm", "fast", "rapid"]
const MOVE_NAMES: Array[String] = ["approach", "flee", "idle"]
const ACT_NAMES: Array[String] = ["idle", "dmg", "heal", "eat", "push"]

var _game_object: Node
var _name_label: Label
var _stats_label: Label
var _state_container: HFlowContainer
var _behavior_label: Label
var _above_offset: float = 8.0
var _is_creature: bool = false

var _last_hp: int = -1
var _last_states: Array = []
var _last_target: String = ""
var _last_movement: int = 2
var _last_action: int = 0


func init(game_obj: Node) -> void:
	_game_object = game_obj
	_is_creature = game_obj.autonomous
	visible = GameManager.debug_mode
	set_process(visible)

	add_theme_stylebox_override("panel",
		InfoWidgets.make_stylebox(Color(0.05, 0.05, 0.08, 0.75), 3, 4, 3))

	var phys: Dictionary = game_obj.blueprint.get("physics", {})
	var height_cm: int = phys.get("height_cm", 30)
	_above_offset = PhysicsComposer.world_sprite_size(height_cm) / 2.0 + 4

	resized.connect(_reposition)

	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 1)
	add_child(vbox)

	# Row 1: name + id
	var row1 := HBoxContainer.new()
	row1.add_theme_constant_override("separation", 6)
	vbox.add_child(row1)

	_name_label = _make_label(10, COL_BRIGHT)
	_name_label.text = game_obj.blueprint.get("name", "?")
	row1.add_child(_name_label)

	var id_label := _make_label(9, COL_DIM)
	id_label.text = game_obj.object_id.left(6)
	row1.add_child(id_label)

	# Row 2: stats (dynamic)
	_stats_label = _make_label(9, COL_MID)
	vbox.add_child(_stats_label)

	# Row 3: physics (static)
	var surf: int = phys.get("surface", 1)
	var surf_str: String = SURFACE_NAMES[surf] if surf >= 0 and surf < SURFACE_NAMES.size() else "?"
	var px_size: float = PhysicsComposer.world_sprite_size(height_cm)
	var phys_label := _make_label(9, COL_DIM)
	phys_label.text = "%skg %dcm(%dpx)  g:%s b:%s  %s" % [
		phys.get("mass_kg", 1), height_cm, int(px_size),
		phys.get("gravity", 50), phys.get("bounce", 10), surf_str
	]
	vbox.add_child(phys_label)

	# Row 4: field + destruction (static, conditional)
	var detail_parts: PackedStringArray = []
	if game_obj.blueprint.get("has_field", false):
		detail_parts.append("field:%dcm" % game_obj.blueprint.get("field_range_cm", 0))
	if game_obj.destruction_result_name != "":
		detail_parts.append("→%s" % game_obj.destruction_result_name)
	if detail_parts.size() > 0:
		var detail_label := _make_label(9, COL_DIM)
		detail_label.text = "  ".join(detail_parts)
		vbox.add_child(detail_label)

	# Row 5: state badges
	_state_container = HFlowContainer.new()
	_state_container.add_theme_constant_override("h_separation", 2)
	_state_container.add_theme_constant_override("v_separation", 1)
	vbox.add_child(_state_container)

	# Row 6: creature behavior (dynamic, creature only)
	if _is_creature:
		_behavior_label = _make_label(9, COL_BEHAVIOR)
		_behavior_label.text = "→ idle"
		vbox.add_child(_behavior_label)

	EventBus.debug_toggled.connect(_on_debug_toggled)

	if visible:
		_refresh()


func _reposition() -> void:
	position.x = -size.x / 2.0
	position.y = -_above_offset - size.y


func _process(_delta: float) -> void:
	var hp: int = _game_object.current_hp if "current_hp" in _game_object else 0
	var states: Array = _game_object.get_states() if _game_object.has_method("get_states") else []
	var needs_refresh := hp != _last_hp or states != _last_states

	if _is_creature:
		var cb: Node = _game_object.get_node_or_null("ObjectBehavior")
		if cb and (cb.current_target_name != _last_target
				or cb.current_movement != _last_movement
				or cb.current_action != _last_action):
			needs_refresh = true

	if needs_refresh:
		_refresh()


func _refresh() -> void:
	_last_hp = _game_object.current_hp if "current_hp" in _game_object else 0
	_last_states = _game_object.get_states().duplicate() if _game_object.has_method("get_states") else []

	var bp: Dictionary = _game_object.blueprint
	var dur: int = bp.get("durability", 2)
	var dur_str: String = DUR_NAMES[dur] if dur >= 0 and dur < DUR_NAMES.size() else "?"
	var aff: int = bp.get("affordance", 3)
	var aff_str: String = AFF_NAMES[aff] if aff >= 0 and aff < AFF_NAMES.size() else "?"
	var max_hp: int = _game_object.max_hp if "max_hp" in _game_object else _last_hp

	var stats_text: String = "[%d/%d] %s  %s" % [_last_hp, max_hp, dur_str, aff_str]
	if _is_creature:
		var spd: int = _game_object.speed_tier if "speed_tier" in _game_object else 2
		var spd_str: String = SPEED_NAMES[spd] if spd >= 0 and spd < SPEED_NAMES.size() else "?"
		stats_text += "  %s" % spd_str
	_stats_label.text = stats_text

	# State badges
	for child in _state_container.get_children():
		child.queue_free()
	for state in _last_states:
		_state_container.add_child(InfoWidgets.create_state_badge(state, 9))

	# Creature behavior
	if _is_creature and _behavior_label:
		var cb: Node = _game_object.get_node_or_null("ObjectBehavior")
		if cb:
			_last_target = cb.current_target_name
			_last_movement = cb.current_movement
			_last_action = cb.current_action
			var pairs_count: int = cb._pairs.size()

			if _last_target.is_empty():
				_behavior_label.text = "→ idle  (%d pairs)" % pairs_count
			else:
				var move_str: String = MOVE_NAMES[_last_movement] if _last_movement >= 0 and _last_movement < MOVE_NAMES.size() else "?"
				var act_str: String = _format_action(cb)
				_behavior_label.text = "→ %s %s | %s  (%d pairs)" % [move_str, _last_target, act_str, pairs_count]

			if cb._error_count > 0:
				_behavior_label.text += " err:%d" % cb._error_count


func _format_action(cb: Node) -> String:
	var action: int = cb.current_action
	var base: String = ACT_NAMES[action] if action >= 0 and action < ACT_NAMES.size() else "?"
	if action in [1, 2, 4]:  # damage, heal, push
		return "%s:%d" % [base, cb.current_action_amount]
	return base


func _make_label(font_size: int, color: Color) -> Label:
	var label := Label.new()
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", color)
	return label


func _on_debug_toggled(on: bool) -> void:
	visible = on
	set_process(on)
	if on:
		_last_hp = -1
		_last_states = []
		_last_target = ""
		_last_movement = 3
		_last_action = 0


func _exit_tree() -> void:
	if EventBus.debug_toggled.is_connected(_on_debug_toggled):
		EventBus.debug_toggled.disconnect(_on_debug_toggled)
