extends Node

signal interaction_triggered(source_name: String, source_tags: Array, target_name: String, target_tags: Array, effect_message: String, world_pos: Vector2)
signal object_created(blueprint: Dictionary)
signal object_destroyed(object_id: String)
signal sprite_ready(object_id: String, texture: Texture2D)
signal level_completed(level_id: int)
signal inventory_changed(slot: int, item: Dictionary)
signal equipment_changed(slot_name: String, item: Dictionary)
signal session_started(session_id: String)
signal creation_started(description: String)
signal creation_finished(blueprint: Dictionary)
signal creation_failed(error: String)
