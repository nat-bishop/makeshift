class_name WorldMutations
extends RefCounted

## Shared world-mutation primitives.
## Both EffectExecutor and BehaviorExecutor route through these functions
## to ensure a single codepath for all game-state mutations.


static func apply_damage(target: Node, amount: float) -> void:
	if not target.has_method("take_damage"):
		return
	target.take_damage(amount)


static func apply_heal(target: Node, amount: float) -> void:
	if not target.has_method("heal"):
		return
	target.heal(amount)


static func apply_add_tag(target: Node, tag: String, duration: float = 0.0) -> void:
	if not target.has_method("add_tag"):
		return
	target.add_tag(tag, duration)


static func apply_remove_tag(target: Node, tag: String) -> void:
	if not target.has_method("remove_tag"):
		return
	target.remove_tag(tag)


static func apply_impulse(target: Node, direction: Vector2, magnitude: float) -> void:
	if target is not RigidBody2D:
		return
	target.apply_central_impulse(direction * magnitude)


static func apply_dot(target: Node, damage_per_tick: float, tick_interval: float, duration: float) -> void:
	if not target.has_method("take_damage"):
		return
	Log.debug("WorldMutations: DOT on %s (%.1f dmg every %.1fs for %.1fs)" % [target.name, damage_per_tick, tick_interval, duration])

	# Replace existing DOT timer instead of stacking
	var existing := target.get_node_or_null("_dot_timer")
	if existing != null:
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
			timer.queue_free()
			return
		state[0] -= 1
		WorldMutations.apply_damage(target, damage_per_tick)
	)
	timer.start()
