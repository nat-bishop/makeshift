extends CanvasLayer

@onready var hotbar: HBoxContainer = %Hotbar
@onready var object_creation_panel: PanelContainer = %ObjectCreationPanel
@onready var objective_label: Label = %ObjectiveLabel
@onready var item_tooltip: PanelContainer = %ItemTooltip


func _ready() -> void:
	layer = 10
	object_creation_panel.visible = false
	item_tooltip.visible = false

	hotbar.slot_hovered.connect(_on_slot_hovered)
	hotbar.slot_unhovered.connect(_on_slot_unhovered)


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("create_object"):
		object_creation_panel.visible = !object_creation_panel.visible
		if object_creation_panel.visible:
			object_creation_panel.focus_input()
		get_viewport().set_input_as_handled()


func set_objective(text: String) -> void:
	objective_label.text = text


func _on_slot_hovered(index: int) -> void:
	var item_data: Dictionary = hotbar._slot_data[index]
	if item_data.is_empty() or not item_data.has("name"):
		item_tooltip.hide_tooltip()
		return
	# Position tooltip above the hovered slot
	var slot: Control = hotbar._slots[index]
	var slot_global_pos := slot.global_position
	var tooltip_pos := Vector2(slot_global_pos.x, slot_global_pos.y - 10)
	item_tooltip.show_for_item(item_data, tooltip_pos)


func _on_slot_unhovered() -> void:
	item_tooltip.hide_tooltip()
