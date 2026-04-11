extends PanelContainer
## Debug overlay: shows ALL object information — identity, HP, physics, velocity,
## states (active + born + susceptible), and full behavior pair table with
## live targeting, utility, distance, and cooldown.

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
const STATE_ACT_NAMES: Array[String] = ["", "+", "-"]

const REFRESH_INTERVAL: int = 6  # dynamic update every 6 frames (~10fps)

var _game_object: Node
var _name_label: Label
var _stats_label: Label
var _physics_label: Label
var _physics_prefix: String = ""
var _state_container: HFlowContainer
var _target_detail_label: Label
var _speeds_label: Label
var _pairs_container: VBoxContainer
var _pair_labels: Dictionary = {}   # target_name -> Label
var _above_offset: float = 8.0
var _is_creature: bool = false

var _last_hp: int = -1
var _last_states: Array = []
var _last_target: String = ""
var _last_movement: int = 2
var _last_action: int = 0
var _last_action_amount: int = 0
var _last_pairs_keys: Array = []
var _frame_counter: int = 0


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

	# Row 2: stats (dynamic HP)
	_stats_label = _make_label(9, COL_MID)
	vbox.add_child(_stats_label)

	# Row 3: physics + velocity (dynamic suffix)
	var surf: int = phys.get("surface", 1)
	var surf_str: String = SURFACE_NAMES[surf] if surf >= 0 and surf < SURFACE_NAMES.size() else "?"
	var px_size: float = PhysicsComposer.world_sprite_size(height_cm)
	_physics_prefix = "%skg %dcm(%dpx)  g:%s b:%s  %s" % [
		phys.get("mass_kg", 1), height_cm, int(px_size),
		phys.get("gravity", 50), phys.get("bounce", 10), surf_str
	]
	_physics_label = _make_label(9, COL_DIM)
	_physics_label.text = _physics_prefix
	vbox.add_child(_physics_label)

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

	# Row 5: initial + susceptible states (static, conditional)
	var state_parts: PackedStringArray = []
	if not game_obj.initial_states.is_empty():
		var names: PackedStringArray = []
		for sid in game_obj.initial_states:
			if sid >= 1 and sid < StateContradictions.STATE_NAMES.size():
				names.append(StateContradictions.STATE_NAMES[sid])
		if names.size() > 0:
			state_parts.append("born: %s" % " ".join(names))
	if not game_obj.susceptible_states.is_empty():
		var names: PackedStringArray = []
		for sid in game_obj.susceptible_states:
			if sid >= 1 and sid < StateContradictions.STATE_NAMES.size():
				names.append(StateContradictions.STATE_NAMES[sid])
		if names.size() > 0:
			state_parts.append("vuln: %s" % " ".join(names))
	if state_parts.size() > 0:
		var props_label := _make_label(9, COL_DIM)
		props_label.text = "  ".join(state_parts)
		vbox.add_child(props_label)

	# Row 6: state badges (dynamic)
	_state_container = HFlowContainer.new()
	_state_container.add_theme_constant_override("h_separation", 2)
	_state_container.add_theme_constant_override("v_separation", 1)
	vbox.add_child(_state_container)

	# Rows 7-9+: creature behavior details
	if _is_creature:
		# Separator
		var sep := _make_label(8, COL_DIM)
		sep.text = "── behaviors ──"
		vbox.add_child(sep)

		# Row 7: current target detail
		_target_detail_label = _make_label(9, COL_BEHAVIOR)
		_target_detail_label.text = "-> idle (no target)"
		vbox.add_child(_target_detail_label)

		# Row 8: speeds + errors
		_speeds_label = _make_label(9, COL_MID)
		vbox.add_child(_speeds_label)

		# Row 9+: all pairs
		_pairs_container = VBoxContainer.new()
		_pairs_container.add_theme_constant_override("separation", 0)
		vbox.add_child(_pairs_container)

		# Init speeds label
		var cb: Node = game_obj.get_node_or_null("ObjectBehavior")
		if cb:
			_speeds_label.text = "spd:%d/%d  err:%d/%d" % [
				int(cb._move_speed), int(cb._flee_speed), cb._error_count, cb.MAX_ERRORS
			]

	EventBus.debug_toggled.connect(_on_debug_toggled)

	if visible:
		_refresh()


func _reposition() -> void:
	position.x = -size.x / 2.0
	position.y = -_above_offset - size.y


func _process(_delta: float) -> void:
	# --- Discrete change detection ---
	var hp: int = _game_object.current_hp if "current_hp" in _game_object else 0
	var states: Array = _game_object.get_states() if _game_object.has_method("get_states") else []
	var needs_refresh := hp != _last_hp or states != _last_states

	if _is_creature:
		var cb: Node = _game_object.get_node_or_null("ObjectBehavior")
		if cb:
			if (cb.current_target_name != _last_target
					or cb.current_movement != _last_movement
					or cb.current_action != _last_action
					or cb.current_action_amount != _last_action_amount):
				needs_refresh = true
			# Detect pair additions/removals
			var current_keys: Array = cb._pairs.keys()
			if current_keys != _last_pairs_keys:
				_last_pairs_keys = current_keys.duplicate()
				_refresh_pairs(cb)

	if needs_refresh:
		_refresh()

	# --- Throttled continuous update ---
	_frame_counter += 1
	if _frame_counter >= REFRESH_INTERVAL:
		_frame_counter = 0
		_refresh_dynamic()


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

	# Creature behavior: update cached values
	if _is_creature:
		var cb: Node = _game_object.get_node_or_null("ObjectBehavior")
		if cb:
			_last_target = cb.current_target_name
			_last_movement = cb.current_movement
			_last_action = cb.current_action
			_last_action_amount = cb.current_action_amount


func _refresh_dynamic() -> void:
	# Velocity (all objects are RigidBody2D)
	if _game_object is RigidBody2D:
		var vel_mag: int = int(_game_object.linear_velocity.length())
		_physics_label.text = _physics_prefix + "  v:%d" % vel_mag

	if not _is_creature:
		return
	var cb: Node = _game_object.get_node_or_null("ObjectBehavior")
	if cb == null:
		return

	# Target detail: movement, action, distance, utility, cooldown
	if cb.current_target_name.is_empty():
		_target_detail_label.text = "-> idle (no target)"
	else:
		var move_str: String = MOVE_NAMES[cb.current_movement] if cb.current_movement >= 0 and cb.current_movement < MOVE_NAMES.size() else "?"
		var act_str: String = _format_action(cb)
		_target_detail_label.text = "-> %s %s | %s  d:%d u:%.1f cd:%.1fs" % [
			move_str, cb.current_target_name, act_str,
			int(cb.current_target_distance), cb.current_best_utility, cb._action_timer
		]

	# Speeds + errors
	_speeds_label.text = "spd:%d/%d  err:%d/%d" % [
		int(cb._move_speed), int(cb._flee_speed), cb._error_count, cb.MAX_ERRORS
	]

	# Update pair highlight colors
	for tname in _pair_labels:
		var label: Label = _pair_labels[tname]
		if tname == cb.current_target_name:
			label.add_theme_color_override("font_color", COL_BEHAVIOR)
		else:
			label.add_theme_color_override("font_color", COL_DIM)


func _refresh_pairs(cb: Node) -> void:
	# Clear old labels
	for child in _pairs_container.get_children():
		child.queue_free()
	_pair_labels.clear()

	# Sort pairs by priority descending
	var sorted_names: Array = cb._pairs.keys()
	sorted_names.sort_custom(func(a: String, b: String) -> bool:
		return cb._pairs[a].get("priority", 0) > cb._pairs[b].get("priority", 0)
	)

	for tname in sorted_names:
		var label := _make_label(8, COL_DIM)
		label.text = _format_pair(tname, cb._pairs[tname])
		_pair_labels[tname] = label
		_pairs_container.add_child(label)


func _format_pair(tname: String, entry: Dictionary) -> String:
	var pri: int = entry.get("priority", 0)
	var mov: int = entry.get("movement", 2)
	var act: int = entry.get("action", 0)
	var amt: int = entry.get("amount", 0)
	var sa: int = entry.get("state_action", 0)
	var sid: int = entry.get("state_id", 0)
	var frc: int = entry.get("force", 0)

	var mov_str: String = MOVE_NAMES[mov] if mov >= 0 and mov < MOVE_NAMES.size() else "?"
	var act_str: String = ACT_NAMES[act] if act >= 0 and act < ACT_NAMES.size() else "?"
	var text: String = "%s P%d %s %s" % [tname, pri, mov_str, act_str]

	if act in [1, 2, 4] and amt > 0:
		text += ":%d" % amt

	if sa in [1, 2] and sid >= 1 and sid < StateContradictions.STATE_NAMES.size():
		text += " %s%s" % [STATE_ACT_NAMES[sa], StateContradictions.STATE_NAMES[sid]]

	if frc == 1:
		text += " kb"

	return text


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
		_last_action_amount = 0
		_last_pairs_keys = []
		_frame_counter = 0


func _exit_tree() -> void:
	if EventBus.debug_toggled.is_connected(_on_debug_toggled):
		EventBus.debug_toggled.disconnect(_on_debug_toggled)
