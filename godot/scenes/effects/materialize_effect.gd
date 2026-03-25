extends Node2D

const SCRAP_COUNT: int = 10
const SPAWN_RADIUS: float = 120.0
const COALESCE_DURATION: float = 1.2
const IDLE_BOB_AMPLITUDE: float = 8.0
const IDLE_BOB_PERIOD: float = 1.5
const RESOLVE_DURATION: float = 0.3
const BURST_RADIUS: float = 60.0

const CRAFT_COLORS: Array[Color] = [
	Color(0.82, 0.73, 0.55),  # tan / kraft
	Color(0.93, 0.89, 0.80),  # cream
	Color(0.60, 0.47, 0.33),  # brown paper
	Color(0.88, 0.86, 0.82),  # off-white / newsprint
	Color(0.72, 0.68, 0.62),  # newsprint grey
	Color(0.78, 0.65, 0.45),  # cardboard
	Color(0.85, 0.80, 0.70),  # parchment
]

var _scraps: Array[Sprite2D] = []
var _coalesce_tween: Tween = null
var _idle_tweens: Array[Tween] = []
var _is_resolving := false


func _ready() -> void:
	_create_scraps()
	_start_coalesce()


func resolve(scatter: bool = true) -> void:
	if _is_resolving:
		return
	_is_resolving = true
	_kill_all_tweens()

	var tween := create_tween().set_parallel(true)
	for scrap in _scraps:
		if not is_instance_valid(scrap):
			continue
		if scatter:
			var burst_dir := Vector2.from_angle(randf() * TAU)
			var burst_target: Vector2 = scrap.position + burst_dir * BURST_RADIUS
			tween.tween_property(scrap, "position", burst_target, RESOLVE_DURATION)
		tween.tween_property(scrap, "modulate:a", 0.0, RESOLVE_DURATION)

	tween.set_parallel(false)
	tween.tween_callback(queue_free)


func _create_scraps() -> void:
	for i in range(SCRAP_COUNT):
		var scrap := Sprite2D.new()
		var scrap_size: int = randi_range(4, 8)
		var image := Image.create(scrap_size, scrap_size, false, Image.FORMAT_RGBA8)
		image.fill(CRAFT_COLORS[randi() % CRAFT_COLORS.size()])
		scrap.texture = ImageTexture.create_from_image(image)

		var angle: float = randf() * TAU
		var dist: float = randf_range(SPAWN_RADIUS * 0.4, SPAWN_RADIUS)
		scrap.position = Vector2.from_angle(angle) * dist
		scrap.rotation = randf() * TAU
		scrap.modulate.a = 0.0
		add_child(scrap)
		_scraps.append(scrap)


func _start_coalesce() -> void:
	_coalesce_tween = create_tween().set_parallel(true)
	for i in range(_scraps.size()):
		var scrap: Sprite2D = _scraps[i]
		var delay: float = randf_range(0.0, 0.3)
		var duration: float = COALESCE_DURATION - delay

		# Fade in
		_coalesce_tween.tween_property(scrap, "modulate:a", 1.0, duration * 0.4).set_delay(delay)
		# Move to center
		_coalesce_tween.tween_property(
			scrap, "position", Vector2.ZERO, duration
		).set_delay(delay).set_ease(Tween.EASE_IN).set_trans(Tween.TRANS_QUAD)
		# Spin
		var spin: float = scrap.rotation + randf_range(PI, TAU * 2.0) * (1.0 if randf() > 0.5 else -1.0)
		_coalesce_tween.tween_property(scrap, "rotation", spin, duration).set_delay(delay)

	_coalesce_tween.set_parallel(false)
	_coalesce_tween.tween_callback(_start_idle)


func _start_idle() -> void:
	if _is_resolving:
		return
	for scrap in _scraps:
		if not is_instance_valid(scrap):
			continue
		var tween := create_tween().set_loops()
		var offset := Vector2(
			randf_range(-IDLE_BOB_AMPLITUDE, IDLE_BOB_AMPLITUDE),
			randf_range(-IDLE_BOB_AMPLITUDE, IDLE_BOB_AMPLITUDE)
		)
		var period: float = randf_range(IDLE_BOB_PERIOD * 0.8, IDLE_BOB_PERIOD * 1.2)
		tween.tween_property(
			scrap, "position", offset, period
		).set_ease(Tween.EASE_IN_OUT).set_trans(Tween.TRANS_SINE)
		tween.tween_property(
			scrap, "position", -offset * 0.5, period
		).set_ease(Tween.EASE_IN_OUT).set_trans(Tween.TRANS_SINE)
		_idle_tweens.append(tween)


func _exit_tree() -> void:
	_kill_all_tweens()


func _kill_all_tweens() -> void:
	if _coalesce_tween and _coalesce_tween.is_valid():
		_coalesce_tween.kill()
		_coalesce_tween = null
	for tween in _idle_tweens:
		if tween and tween.is_valid():
			tween.kill()
	_idle_tweens.clear()
