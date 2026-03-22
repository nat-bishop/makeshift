extends HBoxContainer

const SLOT_COUNT := 8
const SLOT_SIZE := Vector2(64, 64)
const NORMAL_COLOR := Color(0.2, 0.2, 0.2, 0.8)
const SELECTED_COLOR := Color(0.8, 0.7, 0.2, 0.9)
const HOVER_COLOR := Color(0.4, 0.4, 0.4, 0.8)

var _selected_index: int = 0
var _slots: Array[PanelContainer] = []
var _slot_data: Array[Dictionary] = []

signal slot_hovered(index: int)
signal slot_unhovered()


func _ready() -> void:
	_slot_data.resize(SLOT_COUNT)
	for i in SLOT_COUNT:
		_slot_data[i] = {}

	add_theme_constant_override("separation", 4)

	for i in SLOT_COUNT:
		var slot := _create_slot(i)
		add_child(slot)
		_slots.append(slot)

	_update_selection_visuals()
	EventBus.inventory_changed.connect(_on_inventory_changed)
	EventBus.slot_selected.connect(_on_slot_selected)


func _create_slot(index: int) -> PanelContainer:
	var panel := PanelContainer.new()
	panel.custom_minimum_size = SLOT_SIZE

	var style := StyleBoxFlat.new()
	style.bg_color = NORMAL_COLOR
	style.corner_radius_top_left = 4
	style.corner_radius_top_right = 4
	style.corner_radius_bottom_left = 4
	style.corner_radius_bottom_right = 4
	style.border_width_left = 2
	style.border_width_right = 2
	style.border_width_top = 2
	style.border_width_bottom = 2
	style.border_color = Color(0.4, 0.4, 0.4, 0.6)
	panel.add_theme_stylebox_override("panel", style)

	var margin := MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 4)
	margin.add_theme_constant_override("margin_right", 4)
	margin.add_theme_constant_override("margin_top", 4)
	margin.add_theme_constant_override("margin_bottom", 4)
	panel.add_child(margin)

	var vbox := VBoxContainer.new()
	vbox.alignment = BoxContainer.ALIGNMENT_CENTER
	margin.add_child(vbox)

	var icon := TextureRect.new()
	icon.name = "Icon"
	icon.custom_minimum_size = Vector2(40, 40)
	icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	vbox.add_child(icon)

	var label := Label.new()
	label.name = "SlotNumber"
	label.text = str(index + 1)
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.add_theme_font_size_override("font_size", 10)
	label.add_theme_color_override("font_color", Color(0.7, 0.7, 0.7))
	vbox.add_child(label)

	panel.mouse_entered.connect(_on_slot_mouse_entered.bind(index))
	panel.mouse_exited.connect(_on_slot_mouse_exited)
	panel.gui_input.connect(_on_slot_gui_input.bind(index))

	return panel


func update_slot(index: int, item_data: Dictionary) -> void:
	if index < 0 or index >= SLOT_COUNT:
		return
	_slot_data[index] = item_data
	var slot := _slots[index]
	var icon: TextureRect = slot.find_child("Icon", true, false)
	if icon:
		if item_data.has("texture"):
			icon.texture = item_data["texture"]
		else:
			icon.texture = null


func set_selected(index: int) -> void:
	_selected_index = clampi(index, 0, SLOT_COUNT - 1)
	_update_selection_visuals()


func get_selected_index() -> int:
	return _selected_index


func get_selected_item() -> Dictionary:
	return _slot_data[_selected_index]


func get_slot_data(index: int) -> Dictionary:
	if index < 0 or index >= SLOT_COUNT:
		return {}
	return _slot_data[index]


func get_slot_control(index: int) -> PanelContainer:
	if index < 0 or index >= SLOT_COUNT:
		return null
	return _slots[index]


func _update_selection_visuals() -> void:
	for i in _slots.size():
		var style: StyleBoxFlat = _slots[i].get_theme_stylebox("panel")
		if i == _selected_index:
			style.border_color = SELECTED_COLOR
			style.border_width_left = 3
			style.border_width_right = 3
			style.border_width_top = 3
			style.border_width_bottom = 3
		else:
			style.border_color = Color(0.4, 0.4, 0.4, 0.6)
			style.border_width_left = 2
			style.border_width_right = 2
			style.border_width_top = 2
			style.border_width_bottom = 2


func _on_slot_mouse_entered(index: int) -> void:
	if index != _selected_index:
		var style: StyleBoxFlat = _slots[index].get_theme_stylebox("panel")
		style.bg_color = HOVER_COLOR
	slot_hovered.emit(index)


func _on_slot_mouse_exited() -> void:
	for i in _slots.size():
		var style: StyleBoxFlat = _slots[i].get_theme_stylebox("panel")
		style.bg_color = NORMAL_COLOR
	slot_unhovered.emit()


func _on_slot_gui_input(event: InputEvent, index: int) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		# Route through inventory so the slot_selected signal keeps everything in sync
		var player = get_tree().get_first_node_in_group("player")
		if player and player.has_node("PlayerInventory"):
			player.get_node("PlayerInventory").select_slot(index)
		else:
			set_selected(index)


func _on_inventory_changed(slot: int, item: Dictionary) -> void:
	update_slot(slot, item)


func _on_slot_selected(slot: int) -> void:
	set_selected(slot)
