extends Node

var _sprite: Sprite2D
var _object_id: String = ""


func _ready() -> void:
	_sprite = get_parent().get_node("Sprite2D")
	EventBus.sprite_ready.connect(_on_sprite_ready)


func set_object_id(id: String) -> void:
	_object_id = id
	# Check if sprite is already cached
	var cached: Texture2D = Backend.get_cached_sprite(id)
	if cached != null:
		Log.debug("ObjectVisual: Cache hit for %s" % id)
		set_sprite(cached)
	else:
		Log.debug("ObjectVisual: No cached sprite for %s, using placeholder" % id)


func set_placeholder(visual_descriptor: Dictionary) -> void:
	var tags: Array = get_parent().tags
	var size_category: String = visual_descriptor.get("size_category", "medium")
	var size_data: Dictionary = PhysicsComposer.get_size_data(size_category)
	var sprite_size: int = size_data["sprite"]

	var color: Color = _get_placeholder_color(tags)
	var image := Image.create(sprite_size, sprite_size, false, Image.FORMAT_RGBA8)
	image.fill(color)
	var texture := ImageTexture.create_from_image(image)
	_sprite.texture = texture


func set_sprite(texture: Texture2D) -> void:
	# Crossfade from placeholder to real sprite
	var old_alpha: float = _sprite.modulate.a
	_sprite.modulate.a = 0.0
	_sprite.texture = texture

	var tween := _sprite.create_tween()
	tween.tween_property(_sprite, "modulate:a", old_alpha, 0.3)


func _get_placeholder_color(tags: Array) -> Color:
	for tag in tags:
		var tag_str: String = str(tag)
		var color: Color = TagColors.get_color(tag_str)
		if color != TagColors.DEFAULT:
			return color
	return TagColors.DEFAULT


func _on_sprite_ready(id: String, texture: Texture2D) -> void:
	if id == _object_id:
		set_sprite(texture)


func _exit_tree() -> void:
	if EventBus.sprite_ready.is_connected(_on_sprite_ready):
		EventBus.sprite_ready.disconnect(_on_sprite_ready)
