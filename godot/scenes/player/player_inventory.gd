extends Node

const MAX_SLOTS: int = 8

var slots: Array = []
var selected_slot: int = 0


func _ready() -> void:
	slots.resize(MAX_SLOTS)
	for i in range(MAX_SLOTS):
		slots[i] = {}


func add_item(blueprint: Dictionary) -> int:
	for i in range(MAX_SLOTS):
		if slots[i].is_empty():
			slots[i] = blueprint
			EventBus.inventory_changed.emit(i, blueprint)
			return i
	return -1


func remove_item(slot: int) -> Dictionary:
	if slot < 0 or slot >= MAX_SLOTS:
		return {}
	var item: Dictionary = slots[slot]
	slots[slot] = {}
	EventBus.inventory_changed.emit(slot, {})
	return item


func get_item(slot: int) -> Dictionary:
	if slot < 0 or slot >= MAX_SLOTS:
		return {}
	return slots[slot]


func get_selected_item() -> Dictionary:
	return get_item(selected_slot)


func select_slot(slot: int) -> void:
	if slot >= 0 and slot < MAX_SLOTS:
		selected_slot = slot


func has_item(slot: int) -> bool:
	if slot < 0 or slot >= MAX_SLOTS:
		return false
	return not slots[slot].is_empty()
