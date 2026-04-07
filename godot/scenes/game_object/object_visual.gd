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

# V3: Physics-derived animation flags
var _do_bobbing: bool = false
var _bobbing_amplitude: float = 3.0
var _bobbing_speed: float = 2.0
var _do_breathing: bool = false
var _breathing_amplitude: float = 0.03
var _breathing_speed: float = 1.5
var _has_bouncy: bool = false
var _bounce_tween: Tween = null

# State visual nodes
var _particle_nodes: Dictionary = {}
var _state_light: PointLight2D = null
var _active_color_shift: Color = Color.WHITE
var _has_color_shift: bool = false


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


# ── V3: Blueprint-driven init ───────────────────────────────────────────

func init_from_blueprint(bp: Dictionary) -> void:
	_base_sprite_y = _sprite.position.y
	_base_sprite_scale = _sprite.scale

	# Physics-derived animations
	var gravity_pct: int = bp.get("gravity", 50)
	if gravity_pct < 25:
		_do_bobbing = true

	if bp.get("autonomous", false):
		_do_breathing = true

	var bounce_pct: int = bp.get("bounce", 0)
	if bounce_pct > 60:
		_has_bouncy = true
		get_parent().body_entered.connect(_on_bounce_collision)

	if _do_bobbing or _do_breathing or _has_bouncy:
		_programmatic_initialized = true
		set_process(true)


# ── V3: State-driven visuals ────────────────────────────────────────────

func refresh_state_visuals(states: Array) -> void:
	_clear_state_effects()
	_has_color_shift = false
	_active_color_shift = Color.WHITE

	for state in states:
		if state in StateVisuals.STATE_PARTICLES:
			_add_state_particles(state, StateVisuals.STATE_PARTICLES[state])
		if state in StateVisuals.STATE_SHADERS:
			_apply_shader_path(StateVisuals.STATE_SHADERS[state])
		if state in StateVisuals.STATE_COLOR_SHIFTS:
			_active_color_shift = StateVisuals.STATE_COLOR_SHIFTS[state]
			_has_color_shift = true
		if state in StateVisuals.STATE_LIGHTS:
			_add_state_light(StateVisuals.STATE_LIGHTS[state])

	# Update modulate for color shift
	if _has_color_shift:
		_sprite.modulate = _active_color_shift
	elif _hit_flash_timer <= 0.0:
		_sprite.modulate = Color.WHITE


func _clear_state_effects() -> void:
	# Remove particle nodes
	for key in _particle_nodes.keys():
		_particle_nodes[key].queue_free()
	_particle_nodes.clear()
	# Remove light
	if _state_light != null:
		_state_light.queue_free()
		_state_light = null
	# Clear shader
	if _sprite != null:
		_sprite.material = null


func _add_state_particles(state: String, data: Dictionary) -> void:
	var emitter := CPUParticles2D.new()
	emitter.emitting = true
	emitter.amount = data["amount"]
	emitter.lifetime = 1.0
	emitter.direction = data["direction"]
	emitter.spread = 30.0
	emitter.initial_velocity_min = 10.0
	emitter.initial_velocity_max = 30.0
	emitter.scale_amount_min = 1.0
	emitter.scale_amount_max = 2.0
	emitter.gravity = Vector2(0, -20) if data["direction"] == Vector2.UP else Vector2(0, 20)
	emitter.color = data["color"]
	# Fade out over lifetime
	var ramp := Gradient.new()
	ramp.set_color(0, data["color"])
	ramp.set_color(1, Color(data["color"].r, data["color"].g, data["color"].b, 0.0))
	emitter.color_ramp = ramp
	add_child(emitter)
	_particle_nodes[state] = emitter


func _apply_shader_path(shader_path: String) -> void:
	if _sprite == null:
		return
	var shader_res = load(shader_path)
	if shader_res == null:
		return
	var mat := ShaderMaterial.new()
	mat.shader = shader_res
	_sprite.material = mat


func _add_state_light(data: Dictionary) -> void:
	if _state_light != null:
		_state_light.queue_free()
	_state_light = PointLight2D.new()
	_state_light.color = data["color"]
	_state_light.energy = data["energy"]
	_state_light.texture = preload("res://icon.svg")  # fallback light texture
	_state_light.texture_scale = data["texture_scale"] / 128.0
	add_child(_state_light)


# ── Per-frame animation ─────────────────────────────────────────────────

func _apply_programmatic_anims(delta: float) -> void:
	# Bobbing
	if _do_bobbing:
		_sprite.position.y = _base_sprite_y + _bobbing_amplitude * sin(_time * _bobbing_speed)

	# Breathing
	if _do_breathing and not (_bounce_tween and _bounce_tween.is_running()):
		var pulse: float = _breathing_amplitude * sin(_time * _breathing_speed)
		_sprite.scale = _base_sprite_scale + Vector2(pulse, pulse)

	# Hit flash countdown
	if _hit_flash_timer > 0.0:
		_hit_flash_timer -= delta


# ── Event-triggered effects ─────────────────────────────────────────────

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
