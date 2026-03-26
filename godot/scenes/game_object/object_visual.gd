extends Node

var _sprite: Sprite2D
var _object_id: String = ""

# Sprite sheet animation state
var _is_animated: bool = false
var _frame_count: int = 1
var _frame_duration: float = 0.0
var _anim_timer: float = 0.0

# Programmatic animation state
var _time: float = 0.0
var _base_sprite_y: float = 0.0
var _has_floating: bool = false
var _has_glowing: bool = false
var _has_bouncy: bool = false
var _has_electric: bool = false
var _has_wind_source: bool = false
var _has_frozen: bool = false
var _electric_next: float = 0.0
var _electric_flash_timer: float = 0.0
var _programmatic_initialized: bool = false


func _ready() -> void:
	_sprite = get_parent().get_node("Sprite2D")
	EventBus.sprite_ready.connect(_on_sprite_ready)


func _process(delta: float) -> void:
	# Sprite sheet frame cycling (LIVING)
	if _is_animated:
		_anim_timer += delta
		if _anim_timer >= _frame_duration:
			_anim_timer -= _frame_duration
			_sprite.frame = (_sprite.frame + 1) % _frame_count

	# Programmatic effects (tag-driven)
	if _programmatic_initialized:
		_time += delta
		_apply_programmatic_anims(delta)


func set_object_id(id: String) -> void:
	_object_id = id
	# Check if sprite is already cached
	var cached: Texture2D = Backend.get_cached_sprite(id)
	if cached != null:
		Log.debug("ObjectVisual: Cache hit for %s" % id)
		var animation: Dictionary = Backend.get_cached_animation(id)
		set_sprite(cached, animation)
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
	_sprite.scale = Vector2.ONE  # Placeholder is already at world size


func set_sprite(texture: Texture2D, animation: Dictionary = {}) -> void:
	# Configure sprite sheet animation if metadata present
	if not animation.is_empty():
		var cols: int = animation.get("columns", 1)
		var rows: int = animation.get("rows", 1)
		_frame_count = animation.get("frame_count", 1)
		var fps: int = animation.get("fps", 6)
		_sprite.hframes = cols
		_sprite.vframes = rows
		_sprite.frame = 0
		_frame_duration = 1.0 / fps
		_anim_timer = 0.0
		_is_animated = true
	else:
		_sprite.hframes = 1
		_sprite.vframes = 1
		_is_animated = false

	# Scale texture to correct world size based on size_category
	var parent := get_parent()
	var visual_descriptor: Dictionary = parent.blueprint.get("visual_descriptor", {})
	var size_category: String = visual_descriptor.get("size_category", "medium")
	var size_data: Dictionary = PhysicsComposer.get_size_data(size_category)
	var world_size: float = size_data["sprite"]
	# For sprite sheets, texture width includes all columns
	var tex_size: float = texture.get_width()
	if not animation.is_empty():
		tex_size = tex_size / animation.get("columns", 1)
	_sprite.scale = Vector2.ONE * (world_size / tex_size)

	# Crossfade from placeholder to real sprite
	var old_alpha: float = _sprite.modulate.a
	_sprite.modulate.a = 0.0
	_sprite.texture = texture

	var tween := _sprite.create_tween()
	tween.tween_property(_sprite, "modulate:a", old_alpha, 0.3)

	# Update collision shape to match sprite's opaque region
	if parent.has_node("PhysicsApplicator"):
		parent.get_node("PhysicsApplicator").call_deferred(
			"update_shape_from_sprite", texture, world_size, animation
		)


func _get_placeholder_color(tags: Array) -> Color:
	for tag in tags:
		var tag_str: String = str(tag)
		var color: Color = TagColors.get_color(tag_str)
		if color != TagColors.DEFAULT:
			return color
	return TagColors.DEFAULT


func _on_sprite_ready(id: String, texture: Texture2D, animation: Dictionary) -> void:
	if id == _object_id:
		set_sprite(texture, animation)


func init_programmatic_anims(tags: Array) -> void:
	_base_sprite_y = _sprite.position.y
	_has_floating = "FLOATING" in tags
	_has_glowing = "GLOWING" in tags
	_has_bouncy = "BOUNCY" in tags
	_has_electric = "ELECTRIC" in tags
	_has_wind_source = "WIND_SOURCE" in tags
	_has_frozen = "FROZEN" in tags

	# Apply shaders for LIQUID, GAS, MOLTEN
	if "LIQUID" in tags or "MOLTEN" in tags:
		var shader: Shader = preload("res://shaders/ripple.gdshader")
		var mat := ShaderMaterial.new()
		mat.shader = shader
		if "MOLTEN" in tags:
			mat.set_shader_parameter("amplitude", 0.04)
			mat.set_shader_parameter("speed", 2.0)
		_sprite.material = mat

	elif "GAS" in tags:
		var shader: Shader = preload("res://shaders/gas.gdshader")
		var mat := ShaderMaterial.new()
		mat.shader = shader
		_sprite.material = mat

	if _has_electric:
		_electric_next = randf_range(0.5, 2.0)

	if _has_bouncy:
		get_parent().body_entered.connect(_on_bounce_collision)

	_programmatic_initialized = true


func _apply_programmatic_anims(_delta: float) -> void:
	if _has_floating:
		_sprite.position.y = _base_sprite_y + 3.0 * sin(_time * 2.0)

	if _has_wind_source:
		_sprite.rotation = 0.1 * sin(_time * 4.0)

	# Compose modulate from all color-affecting tags to avoid conflicts
	var color := Color.WHITE
	var alpha := 1.0

	if _has_glowing:
		alpha = 0.85 + 0.15 * sin(_time * 3.0)

	if _has_frozen:
		var pulse: float = 0.05 * sin(_time * 2.5)
		color = Color(1.0 - pulse, 1.0 - pulse, 1.0 + pulse)

	if _has_electric:
		if _electric_flash_timer > 0.0:
			_electric_flash_timer -= _delta
			if _electric_flash_timer <= 0.0:
				pass
			else:
				color = Color(1.2, 1.2, 0.5)
		else:
			_electric_next -= _delta
			if _electric_next <= 0.0:
				color = Color(1.2, 1.2, 0.5)
				_electric_flash_timer = 0.08
				_electric_next = randf_range(0.5, 2.0)

	if _has_glowing or _has_frozen or _has_electric:
		_sprite.modulate = Color(color.r, color.g, color.b, alpha)


func _on_bounce_collision(_body: Node) -> void:
	if _sprite == null:
		return
	var tween := _sprite.create_tween()
	tween.tween_property(_sprite, "scale", Vector2(1.2, 0.8), 0.05)
	tween.tween_property(_sprite, "scale", Vector2(0.9, 1.1), 0.08)
	tween.tween_property(_sprite, "scale", Vector2(1.0, 1.0), 0.1)


func _exit_tree() -> void:
	if EventBus.sprite_ready.is_connected(_on_sprite_ready):
		EventBus.sprite_ready.disconnect(_on_sprite_ready)
