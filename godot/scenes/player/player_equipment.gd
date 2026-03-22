extends Node

const TRANSFERABLE_TAGS: Array[String] = [
	"HEAT_SOURCE", "COLD", "SHARP", "ELECTRIC", "MAGNETIC",
	"WIND_SOURCE", "CORROSIVE", "TOXIC", "FLOATING", "GLOWING",
	"REFLECTIVE", "INSULATING", "CONDUCTING", "STICKY",
]

const EQUIP_SLOT_MAP: Dictionary = {
	"sword": "hand", "axe": "hand", "hammer": "hand", "wand": "hand",
	"tool": "hand", "wrench": "hand", "torch": "hand", "fan": "hand",
	"shield": "back", "jetpack": "back", "cape": "back", "wings": "back",
	"helmet": "head", "crown": "head", "goggles": "head",
}

var equipped: Dictionary = {
	"hand": {},
	"back": {},
	"head": {},
}

var _cached_tags: Array = []
var _tags_dirty: bool = true


func equip(blueprint: Dictionary) -> bool:
	if not _is_equippable(blueprint):
		return false
	var slot_name: String = _get_slot(blueprint)
	if not equipped[slot_name].is_empty():
		unequip(slot_name)
	equipped[slot_name] = blueprint
	_tags_dirty = true
	EventBus.equipment_changed.emit(slot_name, blueprint)
	return true


func unequip(slot_name: String) -> Dictionary:
	if slot_name not in equipped:
		return {}
	var item: Dictionary = equipped[slot_name]
	equipped[slot_name] = {}
	_tags_dirty = true
	EventBus.equipment_changed.emit(slot_name, {})
	return item


func get_effective_tags() -> Array:
	if not _tags_dirty:
		return _cached_tags
	var tags: Array = ["LIVING"]
	for slot_name in equipped:
		var blueprint: Dictionary = equipped[slot_name]
		if blueprint.is_empty():
			continue
		var item_tags: Array = blueprint.get("tags", [])
		for tag in item_tags:
			if tag in TRANSFERABLE_TAGS and tag not in tags:
				tags.append(tag)
	_cached_tags = tags
	_tags_dirty = false
	return _cached_tags


func has_tag(tag: String) -> bool:
	return tag in get_effective_tags()


func _is_equippable(blueprint: Dictionary) -> bool:
	var tags: Array = blueprint.get("tags", [])
	return "WEARABLE" in tags or "TOOL" in tags


func _get_slot(blueprint: Dictionary) -> String:
	var visual: Dictionary = blueprint.get("visual_descriptor", {})
	var base_form: String = visual.get("base_form", "")
	return EQUIP_SLOT_MAP.get(base_form, "hand")


func get_data() -> Array:
	return [equipped.duplicate(true)]
