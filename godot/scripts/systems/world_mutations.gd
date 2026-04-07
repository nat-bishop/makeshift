class_name WorldMutations
extends RefCounted

## Shared world-mutation primitives.
## Both EffectExecutor and BehaviorExecutor route through these functions
## to ensure a single codepath for all game-state mutations.


static func apply_damage(target: Node, amount: float, element_color: Color = Color.WHITE) -> void:
	if not target.has_method("take_damage"):
		Log.debug("WorldMutations: %s has no take_damage method, skipping" % target.name)
		return
	Log.debug("WorldMutations: apply_damage %.1f to %s" % [amount, target.name])
	target.take_damage(amount, element_color)


static func apply_heal(target: Node, amount: float) -> void:
	if not target.has_method("heal"):
		Log.debug("WorldMutations: %s has no heal method, skipping" % target.name)
		return
	Log.debug("WorldMutations: apply_heal %.1f to %s" % [amount, target.name])
	target.heal(amount)


static func apply_add_tag(target: Node, tag: String, duration: float = 0.0) -> void:
	## V3 compat: routes to add_state if available, falls back to add_tag.
	apply_add_state(target, tag, duration)


static func apply_add_state(target: Node, state: String, duration: float = 0.0) -> void:
	if target.has_method("add_state"):
		target.add_state(state, duration)
	elif target.has_method("add_tag"):
		# Auto-remove contradictions using StateContradictions
		var contras: Array = StateContradictions.get_contradictions(state)
		if not contras.is_empty() and target.has_method("remove_tag"):
			var body_tags: Array = target.get_tags() if target.has_method("get_tags") else []
			for contra in contras:
				if contra in body_tags:
					target.remove_tag(contra)
		target.add_tag(state, duration)
	else:
		Log.debug("WorldMutations: %s has no add_state/add_tag method, skipping" % target.name)
		return
	Log.debug("WorldMutations: apply_add_state %s to %s%s" % [state, target.name, " (%.1fs)" % duration if duration > 0.0 else ""])


static func apply_remove_tag(target: Node, tag: String) -> void:
	## V3 compat: routes to remove_state if available, falls back to remove_tag.
	apply_remove_state(target, tag)


static func apply_remove_state(target: Node, state: String) -> void:
	if target.has_method("remove_state"):
		target.remove_state(state)
	elif target.has_method("remove_tag"):
		target.remove_tag(state)
	else:
		Log.debug("WorldMutations: %s has no remove_state/remove_tag method, skipping" % target.name)
		return
	Log.debug("WorldMutations: apply_remove_state %s from %s" % [state, target.name])


static func apply_impulse(target: Node, direction: Vector2, magnitude: float) -> void:
	var impulse: Vector2 = direction * magnitude
	if target is RigidBody2D:
		target.apply_central_impulse(impulse)
		# Clamp pre-integration velocity as a soft cap — the impulse itself is queued
		# for the next physics step, but this prevents accumulation across multiple
		# impulses in the same frame from compounding to extreme velocities.
		_clamp_velocity(target)
	elif target.has_method("apply_external_impulse"):
		target.apply_external_impulse(impulse)
	else:
		Log.debug("WorldMutations: %s cannot receive impulse, skipping" % target.name)
		return
	Log.debug("WorldMutations: apply_impulse to %s dir=%s mag=%.0f" % [target.name, direction, magnitude])


const _GRAVITY: float = 980.0
const MAX_VELOCITY: float = 800.0


static func apply_movement_force(body: RigidBody2D, direction: Vector2, max_speed: float, force_magnitude: float) -> void:
	## Apply friction-compensated force for AI movement with velocity clamping.
	## Used by BehaviorExecutor for MOVE_TOWARD, MOVE_AWAY, PATROL.
	var current_speed: float = body.linear_velocity.dot(direction)
	if current_speed >= max_speed:
		return  # Already at/above target speed in movement direction

	# Scale force down as we approach max speed for smooth deceleration
	var speed_ratio: float = clampf(current_speed / max_speed, 0.0, 1.0)
	var scaled_force: float = force_magnitude * (1.0 - speed_ratio)
	var compensated: float = friction_compensated(body, scaled_force)
	body.apply_central_force(direction * compensated)


static func apply_continuous_force(target: Node, direction: Vector2, magnitude: float) -> void:
	## Apply friction-compensated continuous force. Works for both RigidBody2D and
	## CharacterBody2D (via apply_external_impulse scaled by delta).
	if target is RigidBody2D:
		var compensated: float = friction_compensated(target, magnitude)
		target.apply_central_force(direction * compensated)
	elif target.has_method("apply_external_impulse"):
		var dt: float = 1.0 / float(Engine.physics_ticks_per_second)
		target.apply_external_impulse(direction * magnitude * dt)


static func friction_compensated(body: RigidBody2D, desired_magnitude: float) -> float:
	## Scale force to overcome ground friction so forces actually move objects.
	## Treats desired_magnitude as a target acceleration (px/s²), then adds enough
	## force on top to cancel out friction.
	var grav_scale: float = absf(body.gravity_scale)
	if grav_scale < 0.1:
		# Airborne / FLYING: no ground friction to overcome, just scale by mass
		return desired_magnitude * body.mass
	var friction: float = 1.0  # Assume ground default (MAX combine mode)
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
		Log.debug("WorldMutations: %s has no take_damage method, skipping DOT" % target.name)
		return
	if tick_interval <= 0.0 or duration <= 0.0:
		Log.warn("WorldMutations: Invalid DOT params interval=%.2f duration=%.2f on %s, skipping" % [tick_interval, duration, target.name])
		return
	Log.debug("WorldMutations: DOT on %s (%.1f dmg every %.1fs for %.1fs)" % [target.name, damage_per_tick, tick_interval, duration])

	# Replace existing DOT timer instead of stacking.
	# Must remove_child() before queue_free() — queue_free() leaves the node in the
	# tree until end of frame, causing Godot to auto-rename the replacement timer.
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

	# Array wrapper: GDScript lambdas capture primitives by value,
	# so an int can't be mutated across calls.
	var state := [int(duration / tick_interval)]
	timer.timeout.connect(func():
		if not is_instance_valid(timer):
			return
		if not is_instance_valid(target):
			timer.queue_free()
			return
		if state[0] <= 0:
			Log.debug("WorldMutations: DOT finished on %s" % target.name)
			timer.queue_free()
			return
		state[0] -= 1
		WorldMutations.apply_damage(target, damage_per_tick, element_color)
	)
	timer.start()
