extends Node

# Applies rule effects to game objects.
# Called by CollisionResolver for each matched rule.


## Duration (seconds) for tags added during cascade propagation (depth > 0).
const CASCADE_TAG_DURATION: float = 10.0

func execute(rule: Dictionary, body_a: Node, body_b: Node, cascade_depth: int = 0) -> void:
	var effects: Array = rule.get("effects", [])
	var last_message: String = ""
	var tag_duration: float = CASCADE_TAG_DURATION if cascade_depth > 0 else 0.0
	for effect in effects:
		if effect is not Dictionary:
			continue
		var targets: Array[Node] = _get_targets(effect, body_a, body_b)
		var effect_type: String = effect.get("effect_type", "")

		for target in targets:
			_apply_effect(effect_type, effect, target, body_a, body_b, tag_duration)

		var msg: String = effect.get("message", "")
		if msg != "":
			last_message = msg

	if last_message != "":
		var tags_a: Array = _get_tags(body_a)
		var tags_b: Array = _get_tags(body_b)
		var collision_pos: Vector2 = _get_collision_position(body_a, body_b)
		EventBus.interaction_triggered.emit(
			body_a.name, tags_a, body_b.name, tags_b, last_message, collision_pos
		)


func _apply_effect(effect_type: String, effect: Dictionary, target: Node, body_a: Node, body_b: Node, tag_duration: float = 0.0) -> void:
	match effect_type:
		"DAMAGE":
			var amount: float = effect.get("damage_amount", 0.0)
			if target.has_method("take_damage"):
				target.take_damage(amount)

		"DESTROY":
			if target.has_method("take_damage"):
				target.take_damage(99999.0)

		"IGNITE":
			if target.has_method("add_tag"):
				target.add_tag("HEAT_SOURCE", tag_duration)
				target.add_tag("HOT", tag_duration)
			_apply_dot(target, effect.get("damage_amount", 10.0), 1.0, 5.0)

		"EXTINGUISH":
			if target.has_method("remove_tag"):
				target.remove_tag("HEAT_SOURCE")
				target.remove_tag("HOT")

		"FREEZE":
			if target.has_method("add_tag") and target.has_method("remove_tag"):
				target.add_tag("FROZEN", tag_duration)
				target.add_tag("RIGID", tag_duration)
				target.remove_tag("LIQUID")

		"MELT":
			if target.has_method("remove_tag") and target.has_method("add_tag"):
				target.remove_tag("FROZEN")
				target.remove_tag("RIGID")
				target.add_tag("LIQUID", tag_duration)

		"APPLY_FORCE":
			var magnitude: float = effect.get("force_magnitude", 100.0)
			_apply_impulse(target, body_a, body_b, magnitude)

		"ADD_TAG":
			var tags_to_add: Array = effect.get("tags_to_add", [])
			if target.has_method("add_tag"):
				for tag in tags_to_add:
					target.add_tag(tag, tag_duration)

		"REMOVE_TAG":
			var tags_to_remove: Array = effect.get("tags_to_remove", [])
			if target.has_method("remove_tag"):
				for tag in tags_to_remove:
					target.remove_tag(tag)

		"CORRODE":
			var amount: float = effect.get("damage_amount", 15.0)
			_apply_dot(target, amount, 1.0, 3.0)

		"ELECTRIFY":
			var amount: float = effect.get("damage_amount", 30.0)
			if target.has_method("take_damage"):
				target.take_damage(amount)

		"SPAWN":
			var desc: String = effect.get("spawn_description", "unknown object")
			_spawn_placeholder(target.global_position, desc)

		"TRANSFORM", "CHANGE_PROPERTY":
			var tags_to_add: Array = effect.get("tags_to_add", [])
			var tags_to_remove: Array = effect.get("tags_to_remove", [])
			if target.has_method("add_tag"):
				for tag in tags_to_add:
					target.add_tag(tag, tag_duration)
			if target.has_method("remove_tag"):
				for tag in tags_to_remove:
					target.remove_tag(tag)


func _get_targets(effect: Dictionary, body_a: Node, body_b: Node) -> Array[Node]:
	var targets: Array[Node] = []
	var target_str: String = effect.get("target", "b")
	match target_str:
		"a":
			targets.append(body_a)
		"b":
			targets.append(body_b)
		"both":
			targets.append(body_a)
			targets.append(body_b)
		_:
			targets.append(body_b)
	return targets


func _get_tags(body: Node) -> Array:
	if body.has_method("get_effective_tags"):
		return body.get_effective_tags()
	if body.has_method("get_tags"):
		return body.get_tags()
	return []


func _get_collision_position(body_a: Node, body_b: Node) -> Vector2:
	if body_a is Node2D and body_b is Node2D:
		return (body_a.global_position + body_b.global_position) / 2.0
	return Vector2.ZERO


func _apply_impulse(target: Node, body_a: Node, body_b: Node, magnitude: float) -> void:
	if target is not RigidBody2D:
		return
	var source: Node = body_b if target == body_a else body_a
	if source is Node2D and target is Node2D:
		var direction: Vector2 = (target.global_position - source.global_position).normalized()
		target.apply_central_impulse(direction * magnitude)


func _apply_dot(target: Node, damage_per_tick: float, tick_interval: float, duration: float) -> void:
	if not target.has_method("take_damage"):
		return
	var timer := Timer.new()
	timer.wait_time = tick_interval
	timer.one_shot = false
	target.add_child(timer)

	var ticks_remaining: int = int(duration / tick_interval)
	timer.timeout.connect(func():
		if not is_instance_valid(timer):
			return
		if not is_instance_valid(target):
			timer.queue_free()
			return
		if ticks_remaining <= 0:
			timer.queue_free()
			return
		ticks_remaining -= 1
		target.take_damage(damage_per_tick)
	)
	timer.start()


func _spawn_placeholder(pos: Vector2, description: String) -> void:
	Log.warn("EffectExecutor: SPAWN effect stub - '%s' at %s" % [description, str(pos)])
