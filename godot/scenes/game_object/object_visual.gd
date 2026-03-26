extends Node

var _sprite: Sprite2D
var _object_id: String = ""
var _sprite_applied: bool = false

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
var _hit_flash_timer: float = 0.0


func _ready() -> void:
	_sprite = get_parent().get_node("Sprite2D")
	EventBus.sprite_ready.connect(_on_sprite_ready)
	set_process(false)


func _process(delta: float) -> void:
	# Programmatic effects (tag-driven)
	if _programmatic_initialized:
		_time += delta
		_apply_programmatic_anims(delta)


func set_object_id(id: String) -> void:
	_object_id = id
	# Check if sprite is already cached
	var cached: Texture2D = Backend.get_cached_sprite(id)
	if cached != null:
		Log.debug("ObjectVisual: Sprite already loaded for %s" % id)
		set_sprite(cached)
	else:
		Log.debug("ObjectVisual: No cached sprite for %s, waiting for signal" % id)


func set_sprite(texture: Texture2D) -> void:
	if _sprite_applied:
		Log.debug("ObjectVisual: Sprite already applied for %s, ignoring duplicate" % _object_id)
		return
	_sprite_applied = true

	# Scale texture to correct world size based on size_category
	var parent := get_parent()
	var visual_descriptor: Dictionary = parent.blueprint.get("visual_descriptor", {})
	var size_category: String = visual_descriptor.get("size_category", "medium")
	var size_data: Dictionary = PhysicsComposer.get_size_data(size_category)
	var world_size: float = size_data["sprite"]
	var tex_size: float = texture.get_width()
	_sprite.scale = Vector2.ONE * (world_size / tex_size)
	_sprite.texture = texture
	Log.debug("ObjectVisual: Sprite applied for %s (size=%s, scale=%.2f)" % [_object_id, size_category, _sprite.scale.x])

	# Update collision shape to match sprite's opaque region
	if parent.has_node("PhysicsApplicator"):
		parent.get_node("PhysicsApplicator").call_deferred(
			"update_shape_from_sprite", texture, world_size
		)


func _on_sprite_ready(id: String, texture: Texture2D) -> void:
	if id == _object_id:
		set_sprite(texture)


func _update_tag_flags(tags: Array) -> void:
	_has_floating = "FLOATING" in tags
	_has_glowing = "GLOWING" in tags
	_has_bouncy = "BOUNCY" in tags
	_has_electric = "ELECTRIC" in tags
	_has_wind_source = "WIND_SOURCE" in tags
	_has_frozen = "FROZEN" in tags


func _apply_tag_shaders(tags: Array) -> void:
	if "LIQUID" in tags or "MOLTEN" in tags:
		if not (_sprite.material is ShaderMaterial and _sprite.material.shader == preload("res://shaders/ripple.gdshader")):
			var shader: Shader = preload("res://shaders/ripple.gdshader")
			var mat := ShaderMaterial.new()
			mat.shader = shader
			if "MOLTEN" in tags:
				mat.set_shader_parameter("amplitude", 0.04)
				mat.set_shader_parameter("speed", 2.0)
			_sprite.material = mat
	elif "GAS" in tags:
		if not (_sprite.material is ShaderMaterial and _sprite.material.shader == preload("res://shaders/gas.gdshader")):
			var shader: Shader = preload("res://shaders/gas.gdshader")
			var mat := ShaderMaterial.new()
			mat.shader = shader
			_sprite.material = mat
	else:
		_sprite.material = null


func init_programmatic_anims(tags: Array) -> void:
	_base_sprite_y = _sprite.position.y
	_update_tag_flags(tags)
	_apply_tag_shaders(tags)

	if _has_electric:
		_electric_next = randf_range(0.5, 2.0)

	if _has_bouncy:
		get_parent().body_entered.connect(_on_bounce_collision)

	if _has_floating or _has_glowing or _has_bouncy or _has_electric or _has_wind_source or _has_frozen:
		_programmatic_initialized = true
		set_process(true)


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

	if _hit_flash_timer > 0.0:
		_hit_flash_timer -= _delta
	elif _has_glowing or _has_frozen or _has_electric:
		_sprite.modulate = Color(color.r, color.g, color.b, alpha)


func flash_hit(color: Color) -> void:
	if _sprite == null:
		return
	_hit_flash_timer = 0.15
	var original: Color = _sprite.modulate
	var tween := _sprite.create_tween()
	tween.tween_property(_sprite, "modulate", color, 0.07)
	tween.tween_property(_sprite, "modulate", original, 0.08)


func spawn_particles(color: Color, count: int = 5) -> void:
	if _sprite == null:
		return
	var center: Vector2 = _sprite.position
	for i in range(count):
		var particle := ColorRect.new()
		particle.size = Vector2(4, 4)
		particle.color = color
		particle.position = center - Vector2(2, 2)
		add_child(particle)

		var angle: float = randf() * TAU
		var dir := Vector2(cos(angle), sin(angle) - 0.5).normalized()
		var end_pos: Vector2 = particle.position + dir * 30.0

		var tween := particle.create_tween()
		tween.set_parallel(true)
		tween.tween_property(particle, "position", end_pos, 0.5)
		tween.tween_property(particle, "modulate:a", 0.0, 0.5)
		tween.set_parallel(false)
		tween.tween_callback(particle.queue_free)


func refresh_tag_visuals(tags: Array) -> void:
	_update_tag_flags(tags)
	_apply_tag_shaders(tags)

	if _has_electric and _electric_next <= 0.0:
		_electric_next = randf_range(0.5, 2.0)

	# Enable/disable processing based on active animated tags
	var needs_process: bool = _has_floating or _has_glowing or _has_bouncy or _has_electric or _has_wind_source or _has_frozen
	if needs_process:
		_programmatic_initialized = true
		set_process(true)
	elif _programmatic_initialized:
		# Reset sprite state when no animated tags remain
		_sprite.modulate = Color.WHITE
		_sprite.position.y = _base_sprite_y
		_sprite.rotation = 0.0
		_programmatic_initialized = false
		set_process(false)


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
	if _has_bouncy and get_parent().body_entered.is_connected(_on_bounce_collision):
		get_parent().body_entered.disconnect(_on_bounce_collision)
