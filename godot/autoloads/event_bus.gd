extends Node

@warning_ignore("unused_signal")
signal interaction_triggered(source_name: String, source_tags: Array, target_name: String, target_tags: Array, effect_message: String, world_pos: Vector2)
@warning_ignore("unused_signal")
signal object_created(blueprint: Dictionary)
@warning_ignore("unused_signal")
signal sprite_ready(object_id: String, texture: Texture2D)
@warning_ignore("unused_signal")
signal level_completed(level_id: int)
@warning_ignore("unused_signal")
signal creation_requested
@warning_ignore("unused_signal")
signal creation_failed
@warning_ignore("unused_signal")
signal sprite_failed(object_id: String)
@warning_ignore("unused_signal")
signal placement_started
@warning_ignore("unused_signal")
signal placement_ended
@warning_ignore("unused_signal")
signal debug_toggled(enabled: bool)
@warning_ignore("unused_signal")
signal player_died
@warning_ignore("unused_signal")
signal player_damaged(amount: float, current: int, maximum: int)
@warning_ignore("unused_signal")
signal player_healed(amount: float, current: int, maximum: int)
@warning_ignore("unused_signal")
signal effect_applied(effect_type: String, amount: float, element_color: Color, world_pos: Vector2)
@warning_ignore("unused_signal")
signal object_entered_scene(game_object: Node)
@warning_ignore("unused_signal")
signal object_exited_scene(game_object: Node)
@warning_ignore("unused_signal")
signal object_tags_changed(game_object: Node)
@warning_ignore("unused_signal")
signal post_process_changed(shader_name: String)
