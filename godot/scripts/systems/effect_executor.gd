extends Node

# Applies rule effects to game objects.
# Called by CollisionResolver for each matched rule.
# All effects are expressed as 5 primitives: DAMAGE, HEAL, ADD_TAG, REMOVE_TAG, APPLY_FORCE.


## Duration (seconds) for tags added during cascade propagation (depth > 0).
const CASCADE_TAG_DURATION: float = 10.0

func execute(rule: Dictionary, body_a: Node, body_b: Node, cascade_depth: int = 0) -> void:
	var effects: Array = rule.get("effects", [])
	var last_message: String = ""
	var tag_duration: float = CASCADE_TAG_DURATION if cascade_depth > 0 else 0.0
	Log.debug("EffectExecutor: Executing rule '%s' (%d effects, cascade_depth=%d)" % [rule.get("rule_id", "?"), effects.size(), cascade_depth])
	for effect in effects:
		if effect is not Dictionary:
			Log.debug("EffectExecutor: Skipping non-Dictionary effect in rule '%s'" % rule.get("rule_id", "?"))
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
			var tick_interval: float = effect.get("tick_interval", 0.0)
			var tick_dur: float = effect.get("tick_duration", 0.0)
			var source: Node = body_a if target == body_b else body_b
			var element_color: Color = _derive_element_color(source, Color.WHITE)
			if tick_interval > 0.0 and tick_dur > 0.0:
				Log.info("EffectExecutor: DOT %.0f on %s (every %.1fs for %.1fs)" % [amount, target.name, tick_interval, tick_dur])
				WorldMutations.apply_dot(target, amount, tick_interval, tick_dur, element_color)
			else:
				Log.info("EffectExecutor: DAMAGE %.0f on %s" % [amount, target.name])
				WorldMutations.apply_damage(target, amount, element_color)
			if target is Node2D:
				EventBus.effect_applied.emit("DAMAGE", amount, element_color, target.global_position)

		"HEAL":
			var amount: float = effect.get("damage_amount", 0.0)
			Log.info("EffectExecutor: HEAL %.0f on %s" % [amount, target.name])
			WorldMutations.apply_heal(target, amount)
			if target is Node2D:
				EventBus.effect_applied.emit("HEAL", amount, TagColors.HEAL, target.global_position)

		"ADD_TAG":
			var tag: String = effect.get("tag", "")
			if tag != "":
				var dur: float = tag_duration
				var effect_dur: float = effect.get("tag_duration", 0.0)
				if effect_dur > 0.0:
					dur = maxf(effect_dur, tag_duration)
				Log.debug("EffectExecutor: ADD_TAG %s on %s%s" % [tag, target.name, " (%.1fs)" % dur if dur > 0.0 else ""])
				WorldMutations.apply_add_tag(target, tag, dur)

		"REMOVE_TAG":
			var tag: String = effect.get("tag", "")
			if tag != "":
				Log.debug("EffectExecutor: REMOVE_TAG %s on %s" % [tag, target.name])
				WorldMutations.apply_remove_tag(target, tag)

		"APPLY_FORCE":
			var magnitude: float = effect.get("force_magnitude", 100.0)
			var source: Node = body_b if target == body_a else body_a
			var direction: Vector2 = Vector2.ZERO
			if source is Node2D and target is Node2D:
				direction = (target.global_position - source.global_position).normalized()
			Log.debug("EffectExecutor: APPLY_FORCE %.0f on %s" % [magnitude, target.name])
			WorldMutations.apply_impulse(target, direction, magnitude)

		_:
			Log.warn("EffectExecutor: Unknown effect type '%s'" % effect_type)


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
			Log.debug("EffectExecutor: Unknown target '%s', defaulting to body_b" % target_str)
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


func _derive_element_color(source: Node, fallback: Color) -> Color:
	var source_tags: Array = _get_tags(source)
	for tag in source_tags:
		if tag in TagColors.COLORS:
			return TagColors.COLORS[tag]
	return fallback
