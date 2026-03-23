extends Node

signal interaction_triggered(source_name: String, source_tags: Array, target_name: String, target_tags: Array, effect_message: String, world_pos: Vector2)
signal object_created(blueprint: Dictionary)
signal sprite_ready(object_id: String, texture: Texture2D)
signal level_completed(level_id: int)
