extends Node

signal interaction_triggered(source_name: String, source_tags: Array, target_name: String, target_tags: Array, effect_message: String, world_pos: Vector2)
signal object_created(blueprint: Dictionary)
signal sprite_ready(object_id: String, texture: Texture2D)
signal level_completed(level_id: int)
signal creation_requested
signal creation_failed
signal sprite_failed(object_id: String)
signal placement_started
signal placement_ended
signal debug_toggled(enabled: bool)
signal player_died
signal player_damaged(amount: float, current: int, maximum: int)
signal player_healed(amount: float, current: int, maximum: int)
signal effect_applied(effect_type: String, amount: float, element_color: Color, world_pos: Vector2)
