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
	if not target.has_method("add_tag"):
		Log.debug("WorldMutations: %s has no add_tag method, skipping" % target.name)
		return
	Log.debug("WorldMutations: apply_add_tag %s to %s%s" % [tag, target.name, " (%.1fs)" % duration if duration > 0.0 else ""])
	target.add_tag(tag, duration)


static func apply_remove_tag(target: Node, tag: String) -> void:
	if not target.has_method("remove_tag"):
		Log.debug("WorldMutations: %s has no remove_tag method, skipping" % target.name)
		return
	Log.debug("WorldMutations: apply_remove_tag %s from %s" % [tag, target.name])
	target.remove_tag(tag)


static func apply_impulse(target: Node, direction: Vector2, magnitude: float) -> void:
	var impulse: Vector2 = direction * magnitude
	if target is RigidBody2D:
		target.apply_central_impulse(impulse)
	elif target.has_method("apply_external_impulse"):
		target.apply_external_impulse(impulse)
	else:
		Log.debug("WorldMutations: %s cannot receive impulse, skipping" % target.name)
		return
	Log.debug("WorldMutations: apply_impulse to %s dir=%s mag=%.0f" % [target.name, direction, magnitude])


static func apply_dot(target: Node, damage_per_tick: float, tick_interval: float, duration: float, element_color: Color = Color.WHITE) -> void:
	if not target.has_method("take_damage"):
		Log.debug("WorldMutations: %s has no take_damage method, skipping DOT" % target.name)
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
