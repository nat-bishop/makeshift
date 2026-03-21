extends Node

var player: CharacterBody2D
var interaction_area: Area2D
var nearby_objects: Array = []

@onready var inventory: Node = $"../PlayerInventory"
@onready var equipment: Node = $"../PlayerEquipment"


func _ready() -> void:
	player = get_parent()
	interaction_area = player.get_node("InteractionArea")
	interaction_area.body_entered.connect(_on_body_entered)
	interaction_area.body_exited.connect(_on_body_exited)


func _on_body_entered(body: Node2D) -> void:
	if body != player and body.has_method("get_tags"):
		nearby_objects.append(body)


func _on_body_exited(body: Node2D) -> void:
	nearby_objects.erase(body)


func pickup_nearest() -> bool:
	if nearby_objects.is_empty():
		return false

	var closest: Node2D = null
	var closest_dist: float = INF
	for obj in nearby_objects:
		if not is_instance_valid(obj):
			continue
		var dist: float = player.global_position.distance_to(obj.global_position)
		if dist < closest_dist:
			closest_dist = dist
			closest = obj

	if closest == null:
		return false

	if not closest.has_method("get_blueprint"):
		return false

	var blueprint: Dictionary = closest.get_blueprint()
	var slot: int = inventory.add_item(blueprint)
	if slot == -1:
		return false

	nearby_objects.erase(closest)
	closest.queue_free()
	return true


func drop_item() -> void:
	var item: Dictionary = inventory.remove_item(inventory.selected_slot)
	if item.is_empty():
		return
	_spawn_object_in_world(item)


func equip_item() -> void:
	var item: Dictionary = inventory.get_selected_item()
	if item.is_empty():
		return
	if equipment.equip(item):
		inventory.remove_item(inventory.selected_slot)


func _spawn_object_in_world(blueprint: Dictionary) -> void:
	var game_object_scene: PackedScene = load("res://scenes/game_object/game_object.tscn")
	if game_object_scene == null:
		return
	var obj: Node2D = game_object_scene.instantiate()
	var drop_offset := Vector2(50.0 * sign(player.velocity.x) if player.velocity.x != 0.0 else 50.0, -20.0)
	obj.global_position = player.global_position + drop_offset
	if obj.has_method("init_from_blueprint"):
		obj.init_from_blueprint(blueprint)
	var world: Node = player.get_tree().current_scene
	world.add_child(obj)
