extends Node

## V3 ObjectVisual: state-keyed visuals + physics-derived animations.
## Replaces tag-keyed TagAnimations with StateVisuals.

var _sprite: Sprite2D
var _object_id: String = ""
var _sprite_applied: bool = false

# Programmatic animation state
var _time: float = 0.0
var _base_sprite_y: float = 0.0
var _base_sprite_scale: Vector2 = Vector2.ONE
var _programmatic_initialized: bool = false
var _hit_flash_timer: float = 0.0

# Physics-derived flags (set once at creation from blueprint values)
var _has_bobbing: bool = false  # gravity < 25
var _has_breathing: bool = false  # autonomous
var _has_bounce_squash: bool = false  # bounce > 60
var _bounce_tween: Tween = null

# State-driven visual state
var _active_color_shift: Color = Color.WHITE
var _active_flash_configs: Array = []
var _particle_nodes: Dictionary = {}  # state -> CPUParticles2D
var _light_nodes: Dictionary = {}  # state -> PointLight2D


func _ready() -> void:
	_sprite = get_parent().get_node("Sprite2D")
	EventBus.sprite_ready.connect(_on_sprite_ready)
	set_process(false)


func _process(delta: float) -> void:
	if _programmatic_initialized:
		_time += delta
		_apply_anims(delta)


func set_object_id(id: String) -> void:
	_object_id = id
	var cached: Texture2D = Backend.get_cached_sprite(id)
	if cached != null:
		set_sprite(cached)


func set_sprite(texture: Texture2D) -> void:
	if _sprite_applied:
		return
	_sprite_applied = true

	var parent := get_parent()
	var phys: Dictionary = parent.blueprint.get("physics", {})
	var height_cm: int = phys.get("height_cm", 30)
	var size_category: String = PhysicsComposer.size_from_height(height_cm)
	var size_data: Dictionary = PhysicsComposer.get_size_data(size_category)
	var world_size: float = size_data["sprite"]
	var tex_size: float = texture.get_width()
	_sprite.scale = Vector2.ONE * (world_size / tex_size)
	_sprite.texture = texture
	_base_sprite_scale = _sprite.scale

	if parent.has_node("PhysicsApplicator"):
		parent.get_node("PhysicsApplicator").call_deferred(
			"update_shape_from_sprite", texture, world_size
		)


func _on_sprite_ready(id: String, texture: Texture2D) -> void:
	if id == _object_id:
		set_sprite(texture)


# ── Init and refresh ─────────────────────────────────────────────────────

func init_visuals(bp: Dictionary) -> void:
	## Called once at creation. Sets up physics-derived animations.
	_base_sprite_y = _sprite.position.y
	_base_sprite_scale = _sprite.scale

	var phys: Dictionary = bp.get("physics", {})
	_has_bobbing = phys.get("gravity", 50) < StateVisuals.BOBBING_GRAVITY_THRESHOLD
	_has_breathing = bp.get("autonomous", false)
	_has_bounce_squash = phys.get("bounce", 10) > StateVisuals.SQUASH_BOUNCE_THRESHOLD

	if _has_bounce_squash:
		get_parent().body_entered.connect(_on_bounce_collision)

	if _has_bobbing or _has_breathing:
		_programmatic_initialized = true
		set_process(true)


func refresh_state_visuals(states: Array) -> void:
	## Called when states change. Updates particles, color, lights.
	_update_state_particles(states)
	_update_state_color(states)
	_update_state_lights(states)
	_update_state_flash(states)

	# Enable processing if we have flash animations or physics-derived anims
	var needs_process: bool = _has_bobbing or _has_breathing or not _active_flash_configs.is_empty()
	if needs_process:
		_programmatic_initialized = true
		set_process(true)
	elif not _has_bobbing and not _has_breathing:
		_sprite.modulate = _active_color_shift
		_programmatic_initialized = false
		set_process(false)


# ── State-driven visuals ─────────────────────────────────────────────────

func _update_state_particles(states: Array) -> void:
	for state_key in _particle_nodes.keys():
		if state_key not in states:
			_particle_nodes[state_key].queue_free()
			_particle_nodes.erase(state_key)
	for state_key in states:
		if state_key in StateVisuals.PARTICLES and state_key not in _particle_nodes:
			_particle_nodes[state_key] = _create_state_particles(state_key)


func _create_state_particles(state_key: String) -> CPUParticles2D:
	var data: Dictionary = StateVisuals.PARTICLES[state_key]
	var emitter := CPUParticles2D.new()
	emitter.emitting = true
	emitter.amount = data["amount"]
	emitter.lifetime = 1.0
	emitter.direction = data["direction"]
	emitter.spread = data["spread"]
	emitter.initial_velocity_min = data["speed"] * 0.5
	emitter.initial_velocity_max = data["speed"]
	emitter.scale_amount_min = 0.3
	emitter.scale_amount_max = 0.6
	emitter.gravity = data["direction"] * -50.0
	emitter.color = data["color"]
	var ramp := Gradient.new()
	ramp.set_color(0, data["color"])
	ramp.set_color(1, Color(data["color"].r, data["color"].g, data["color"].b, 0.0))
	emitter.color_ramp = ramp
	add_child(emitter)
	return emitter


func _update_state_color(states: Array) -> void:
	_active_color_shift = Color.WHITE
	for state_key in states:
		if state_key in StateVisuals.COLOR_SHIFT:
			_active_color_shift = StateVisuals.COLOR_SHIFT[state_key]
			break  # First match wins
	if _hit_flash_timer <= 0.0:
		_sprite.modulate = _active_color_shift


func _update_state_lights(states: Array) -> void:
	for state_key in _light_nodes.keys():
		if state_key not in states:
			_light_nodes[state_key].queue_free()
			_light_nodes.erase(state_key)
	for state_key in states:
		if state_key in StateVisuals.LIGHTS and state_key not in _light_nodes:
			_light_nodes[state_key] = _create_state_light(state_key)


func _create_state_light(state_key: String) -> PointLight2D:
	var data: Dictionary = StateVisuals.LIGHTS[state_key]
	var light := PointLight2D.new()
	light.color = data["color"]
	light.energy = data["energy"]
	light.texture = preload("res://icon.svg")  # Fallback — replace with light texture
	light.texture_scale = data["range"] / 128.0
	add_child(light)
	return light


func _update_state_flash(states: Array) -> void:
	_active_flash_configs = []
	for state_key in states:
		if state_key in StateVisuals.FLASH:
			var cfg: Dictionary = StateVisuals.FLASH[state_key].duplicate()
			cfg["_next_time"] = cfg["interval"]
			cfg["_flash_timer"] = 0.0
			_active_flash_configs.append(cfg)


# ── Per-frame animation ──────────────────────────────────────────────────

func _apply_anims(delta: float) -> void:
	# Bobbing (physics-derived: gravity < 25)
	if _has_bobbing:
		_sprite.position.y = _base_sprite_y + 3.0 * sin(_time * PI)

	# Breathing (physics-derived: autonomous)
	if _has_breathing and not (_bounce_tween and _bounce_tween.is_running()):
		var pulse: float = 0.03 * sin(_time * (2.0 * PI / 3.0))
		_sprite.scale = _base_sprite_scale + Vector2(pulse, pulse)

	# Flash (state-driven)
	if _hit_flash_timer > 0.0:
		_hit_flash_timer -= delta
	elif not _active_flash_configs.is_empty():
		var color: Color = _active_color_shift
		for cfg in _active_flash_configs:
			if cfg["_flash_timer"] > 0.0:
				cfg["_flash_timer"] -= delta
				if cfg["_flash_timer"] > 0.0:
					color = cfg["color"]
			else:
				cfg["_next_time"] -= delta
				if cfg["_next_time"] <= 0.0:
					color = cfg["color"]
					cfg["_flash_timer"] = 0.1
					cfg["_next_time"] = cfg["interval"]
		_sprite.modulate = color


# ── Event-triggered effects ──────────────────────────────────────────────

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
	if _has_bounce_squash and get_parent().body_entered.is_connected(_on_bounce_collision):
		get_parent().body_entered.disconnect(_on_bounce_collision)
