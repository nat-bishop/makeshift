extends Node

var _sprite: Sprite2D
var _object_id: String = ""
var _sprite_applied: bool = false

# Programmatic animation state
var _time: float = 0.0
var _base_sprite_y: float = 0.0
var _base_sprite_scale: Vector2 = Vector2.ONE
var _programmatic_initialized: bool = false
var _hit_flash_timer: float = 0.0

# Active animation configs (rebuilt when tags change)
var _active_bobbing: Array = []
var _active_swaying: Array = []
var _active_breathing: Array = []
var _active_alpha_pulse: Array = []
var _active_color_shift: Array = []
var _active_flash: Array = []
var _active_jitter: Array = []
var _has_bouncy: bool = false
var _active_shader_affects_alpha: bool = false
var _bounce_tween: Tween = null

# Ambient particle emitters (tag -> CPUParticles2D node)
var _particle_nodes: Dictionary = {}


func _ready() -> void:
	_sprite = get_parent().get_node("Sprite2D")
	EventBus.sprite_ready.connect(_on_sprite_ready)
	set_process(false)


func _process(delta: float) -> void:
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
	_base_sprite_scale = _sprite.scale
	Log.debug("ObjectVisual: Sprite applied for %s (size=%s, scale=%.2f)" % [_object_id, size_category, _sprite.scale.x])

	# Update collision shape to match sprite's opaque region
	if parent.has_node("PhysicsApplicator"):
		parent.get_node("PhysicsApplicator").call_deferred(
			"update_shape_from_sprite", texture, world_size
		)


func _on_sprite_ready(id: String, texture: Texture2D) -> void:
	if id == _object_id:
		set_sprite(texture)


# ── Tag flag collection ──────────────────────────────────────────────────

func _update_tag_flags(tags: Array) -> void:
	_active_bobbing = _collect(tags, TagAnimations.BOBBING)
	_active_swaying = _collect(tags, TagAnimations.SWAYING)
	_active_breathing = _collect(tags, TagAnimations.BREATHING)
	_active_alpha_pulse = _collect(tags, TagAnimations.ALPHA_PULSE)
	_active_color_shift = _collect(tags, TagAnimations.COLOR_SHIFT)
	_active_jitter = _collect(tags, TagAnimations.JITTER)
	_update_flash_entries(tags)
	_has_bouncy = "BOUNCY" in tags


func _collect(tags: Array, anim_dict: Dictionary) -> Array:
	var result: Array = []
	for tag in tags:
		if tag in anim_dict:
			var entry: Dictionary = anim_dict[tag].duplicate()
			entry["tag"] = tag
			result.append(entry)
	return result


func _update_flash_entries(tags: Array) -> void:
	# Preserve timer state for tags that remain active
	var existing: Dictionary = {}
	for entry in _active_flash:
		existing[entry["tag"]] = entry
	_active_flash = []
	for tag in tags:
		if tag in TagAnimations.FLASH:
			if tag in existing:
				_active_flash.append(existing[tag])
			else:
				var entry: Dictionary = TagAnimations.FLASH[tag].duplicate()
				entry["tag"] = tag
				entry["_next_time"] = randf_range(entry["min_interval"], entry["max_interval"])
				entry["_flash_timer"] = 0.0
				_active_flash.append(entry)


func _has_any_animations() -> bool:
	return (
		not _active_bobbing.is_empty()
		or not _active_swaying.is_empty()
		or not _active_breathing.is_empty()
		or not _active_alpha_pulse.is_empty()
		or not _active_color_shift.is_empty()
		or not _active_flash.is_empty()
		or not _active_jitter.is_empty()
		or _has_bouncy
	)


func _has_color_anims() -> bool:
	return (
		not _active_alpha_pulse.is_empty()
		or not _active_color_shift.is_empty()
		or not _active_flash.is_empty()
	)


# ── Shaders ──────────────────────────────────────────────────────────────

func _apply_tag_shaders(tags: Array) -> void:
	for tag in tags:
		if tag in TagAnimations.SHADERS:
			var data: Dictionary = TagAnimations.SHADERS[tag]
			var shader: Shader = data["shader"]
			if _sprite.material is ShaderMaterial and _sprite.material.shader == shader:
				_active_shader_affects_alpha = data.get("affects_alpha", false)
				return
			var mat := ShaderMaterial.new()
			mat.shader = shader
			for param_name in data["params"]:
				mat.set_shader_parameter(param_name, data["params"][param_name])
			_sprite.material = mat
			_active_shader_affects_alpha = data.get("affects_alpha", false)
			return
	_sprite.material = null
	_active_shader_affects_alpha = false


# ── Ambient particles ────────────────────────────────────────────────────

func _update_particles(tags: Array) -> void:
	# Remove particles for tags no longer present
	for tag in _particle_nodes.keys():
		if tag not in tags:
			_particle_nodes[tag].queue_free()
			_particle_nodes.erase(tag)
	# Add particles for new tags
	for tag in tags:
		if tag in TagAnimations.PARTICLES and tag not in _particle_nodes:
			_particle_nodes[tag] = _create_particle_emitter(tag)


func _create_particle_emitter(tag: String) -> CPUParticles2D:
	var data: Dictionary = TagAnimations.PARTICLES[tag]
	var emitter := CPUParticles2D.new()
	emitter.emitting = true
	emitter.amount = data["amount"]
	emitter.lifetime = data["lifetime"]
	emitter.direction = data["direction"]
	emitter.spread = data["spread"]
	emitter.initial_velocity_min = data["velocity_min"]
	emitter.initial_velocity_max = data["velocity_max"]
	emitter.scale_amount_min = data["scale_min"]
	emitter.scale_amount_max = data["scale_max"]
	emitter.gravity = data["gravity"]
	emitter.color = data["color"]
	# Fade out over lifetime
	var ramp := Gradient.new()
	ramp.set_color(0, data["color"])
	ramp.set_color(1, Color(data["color"].r, data["color"].g, data["color"].b, 0.0))
	emitter.color_ramp = ramp
	add_child(emitter)
	return emitter


# ── Init and refresh ─────────────────────────────────────────────────────

func init_programmatic_anims(tags: Array) -> void:
	_base_sprite_y = _sprite.position.y
	_base_sprite_scale = _sprite.scale
	_update_tag_flags(tags)
	_apply_tag_shaders(tags)
	_update_particles(tags)

	if _has_bouncy:
		get_parent().body_entered.connect(_on_bounce_collision)

	if _has_any_animations():
		_programmatic_initialized = true
		set_process(true)


func refresh_tag_visuals(tags: Array) -> void:
	_update_tag_flags(tags)
	_apply_tag_shaders(tags)
	_update_particles(tags)

	var needs_process: bool = _has_any_animations()
	if needs_process:
		_programmatic_initialized = true
		set_process(true)
	elif _programmatic_initialized:
		# Reset sprite state when no animated tags remain
		_sprite.modulate = Color.WHITE
		_sprite.position.y = _base_sprite_y
		_sprite.position.x = 0.0
		_sprite.rotation = 0.0
		_sprite.scale = _base_sprite_scale
		_programmatic_initialized = false
		set_process(false)


# ── Per-frame animation ──────────────────────────────────────────────────

func _apply_programmatic_anims(delta: float) -> void:
	# Position
	var pos_y_offset: float = _calc_bobbing()
	var jitter_offset: Vector2 = _calc_jitter()
	_sprite.position.y = _base_sprite_y + pos_y_offset + jitter_offset.y
	_sprite.position.x = jitter_offset.x

	# Rotation
	_sprite.rotation = _calc_swaying()

	# Scale (skip if bounce tween is running — it owns scale briefly)
	if not (_bounce_tween and _bounce_tween.is_running()):
		_sprite.scale = _base_sprite_scale + _calc_breathing()

	# Color/alpha composition
	var color := Color.WHITE
	var alpha := 1.0
	if not _active_shader_affects_alpha:
		alpha = _calc_alpha_pulse(alpha)
	color = _calc_color_shift(color)
	color = _calc_flash(color, delta)

	if _hit_flash_timer > 0.0:
		_hit_flash_timer -= delta
	elif _has_color_anims():
		_sprite.modulate = Color(color.r, color.g, color.b, alpha)


func _calc_bobbing() -> float:
	var offset := 0.0
	for entry in _active_bobbing:
		offset += entry["amplitude"] * sin(_time * entry["speed"])
	return offset


func _calc_swaying() -> float:
	var rotation := 0.0
	for entry in _active_swaying:
		rotation += entry["amplitude"] * sin(_time * entry["speed"])
	return rotation


func _calc_breathing() -> Vector2:
	var scale_delta := Vector2.ZERO
	for entry in _active_breathing:
		var pulse: float = entry["amplitude"] * sin(_time * entry["speed"])
		scale_delta += Vector2(pulse, pulse)
	return scale_delta


func _calc_alpha_pulse(current_alpha: float) -> float:
	for entry in _active_alpha_pulse:
		current_alpha = entry["base_alpha"] + entry["amplitude"] * sin(_time * entry["speed"])
	return current_alpha


func _calc_color_shift(color: Color) -> Color:
	for entry in _active_color_shift:
		var pulse: float = entry["amplitude"] * sin(_time * entry["speed"])
		color.r += entry["r_offset"] * pulse
		color.g += entry["g_offset"] * pulse
		color.b += entry["b_offset"] * pulse
	return color


func _calc_flash(color: Color, delta: float) -> Color:
	for entry in _active_flash:
		if entry["_flash_timer"] > 0.0:
			entry["_flash_timer"] -= delta
			if entry["_flash_timer"] > 0.0:
				color = entry["color"]
		else:
			entry["_next_time"] -= delta
			if entry["_next_time"] <= 0.0:
				color = entry["color"]
				entry["_flash_timer"] = entry["duration"]
				entry["_next_time"] = randf_range(entry["min_interval"], entry["max_interval"])
	return color


func _calc_jitter() -> Vector2:
	var offset := Vector2.ZERO
	for entry in _active_jitter:
		offset.x += randf_range(-1.0, 1.0) * entry["intensity"]
		offset.y += randf_range(-1.0, 1.0) * entry["intensity"]
	return offset


# ── Event-triggered effects (not data-driven) ───────────────────────────

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


func _on_bounce_collision(_body: Node) -> void:
	if _sprite == null:
		return
	if _bounce_tween and _bounce_tween.is_valid():
		_bounce_tween.kill()
	var base: Vector2 = _base_sprite_scale
	_bounce_tween = _sprite.create_tween()
	_bounce_tween.tween_property(_sprite, "scale", base * Vector2(1.2, 0.8), 0.05)
	_bounce_tween.tween_property(_sprite, "scale", base * Vector2(0.9, 1.1), 0.08)
	_bounce_tween.tween_property(_sprite, "scale", base, 0.1)


func _exit_tree() -> void:
	if EventBus.sprite_ready.is_connected(_on_sprite_ready):
		EventBus.sprite_ready.disconnect(_on_sprite_ready)
	if _has_bouncy and get_parent().body_entered.is_connected(_on_bounce_collision):
		get_parent().body_entered.disconnect(_on_bounce_collision)
