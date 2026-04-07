class_name WorldMutations
extends RefCounted

## V3 world-mutation primitives.
## All game-state mutations route through here.


static func apply_damage(target: Node, amount: float, element_color: Color = Color.WHITE) -> void:
	if not target.has_method("take_damage"):
		return
	target.take_damage(amount, element_color)


static func apply_heal(target: Node, amount: float) -> void:
	if not target.has_method("heal"):
		return
	target.heal(amount)


static func apply_add_state(target: Node, state: String, duration: float = 0.0) -> void:
	if not target.has_method("add_state"):
		return
	# Directed contradictions are enforced inside StateManager.add_state()
	target.add_state(state, duration)


static func apply_remove_state(target: Node, state: String) -> void:
	if not target.has_method("remove_state"):
		return
	target.remove_state(state)


static func apply_impulse(target: Node, direction: Vector2, magnitude: float) -> void:
	var impulse: Vector2 = direction * magnitude
	if target is RigidBody2D:
		target.apply_central_impulse(impulse)
		_clamp_velocity(target)
	elif target.has_method("apply_external_impulse"):
		target.apply_external_impulse(impulse)


const _GRAVITY: float = 980.0
const MAX_VELOCITY: float = 800.0


static func apply_movement_force(body: RigidBody2D, direction: Vector2, max_speed: float, force_magnitude: float) -> void:
	var current_speed: float = body.linear_velocity.dot(direction)
	if current_speed >= max_speed:
		return
	var speed_ratio: float = clampf(current_speed / max_speed, 0.0, 1.0)
	var scaled_force: float = force_magnitude * (1.0 - speed_ratio)
	var compensated: float = friction_compensated(body, scaled_force)
	body.apply_central_force(direction * compensated)


static func apply_continuous_force(target: Node, direction: Vector2, magnitude: float) -> void:
	if target is RigidBody2D:
		var compensated: float = friction_compensated(target, magnitude)
		target.apply_central_force(direction * compensated)
	elif target.has_method("apply_external_impulse"):
		var dt: float = 1.0 / float(Engine.physics_ticks_per_second)
		target.apply_external_impulse(direction * magnitude * dt)


static func friction_compensated(body: RigidBody2D, desired_magnitude: float) -> float:
	var grav_scale: float = absf(body.gravity_scale)
	if grav_scale < 0.1:
		return desired_magnitude * body.mass
	var friction: float = 1.0
	if body.physics_material_override:
		friction = maxf(body.physics_material_override.friction, friction)
	var weight: float = body.mass * _GRAVITY * grav_scale
	var friction_force: float = friction * weight
	var sign_f: float = signf(desired_magnitude)
	return sign_f * (friction_force + absf(desired_magnitude) * body.mass)


static func _clamp_velocity(body: RigidBody2D) -> void:
	var vel: Vector2 = body.linear_velocity
	if vel.length_squared() > MAX_VELOCITY * MAX_VELOCITY:
		body.linear_velocity = vel.normalized() * MAX_VELOCITY


static func apply_dot(target: Node, damage_per_tick: float, tick_interval: float, duration: float, element_color: Color = Color.WHITE) -> void:
	if not target.has_method("take_damage"):
		return
	if tick_interval <= 0.0 or duration <= 0.0:
		return

	var existing := target.get_node_or_null("_dot_timer")
	if existing != null:
		existing.stop()
		target.remove_child(existing)
		existing.queue_free()

	var timer := Timer.new()
	timer.name = "_dot_timer"
	timer.wait_time = tick_interval
	timer.one_shot = false
	target.add_child(timer)

	var state := [int(duration / tick_interval)]
	timer.timeout.connect(func():
		if not is_instance_valid(timer):
			return
		if not is_instance_valid(target):
			timer.queue_free()
			return
		if state[0] <= 0:
			timer.queue_free()
			return
		state[0] -= 1
		WorldMutations.apply_damage(target, damage_per_tick, element_color)
	)
	timer.start()
