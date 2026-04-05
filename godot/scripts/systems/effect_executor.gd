extends Node

# Applies rule effects to game objects.
# Called by CollisionResolver for each matched rule.
# V2: reads combat_profile/substance_profile from blueprints for parameterized damage.

const DYNAMIC_TAG_DURATION: float = 10.0


func execute(rule: Dictionary, body_a: Node, body_b: Node, cascade_depth: int = 0) -> void:
	var effects: Array = rule.get("effects", [])
	var last_message: String = ""
	var tag_duration: float = DYNAMIC_TAG_DURATION if cascade_depth > 0 else 0.0
	Log.debug("EffectExecutor: Executing rule '%s' (%d effects, cascade_depth=%d)" % [rule.get("rule_id", "?"), effects.size(), cascade_depth])
	var rule_id: String = rule.get("rule_id", "")
	for effect in effects:
		if effect is not Dictionary:
			Log.debug("EffectExecutor: Skipping non-Dictionary effect in rule '%s'" % rule_id)
			continue
		var targets: Array[Node] = _get_targets(effect, body_a, body_b)
		var effect_type: String = effect.get("effect_type", "")

		for target in targets:
			_apply_effect(effect_type, effect, target, body_a, body_b, tag_duration, rule_id)

		var msg: String = effect.get("message", "")
		if msg != "":
			last_message = msg

	if last_message != "":
		var tags_a: Array = TagColors.get_body_tags(body_a)
		var tags_b: Array = TagColors.get_body_tags(body_b)
		var collision_pos: Vector2 = _get_collision_position(body_a, body_b)
		EventBus.interaction_triggered.emit(
			body_a.name, tags_a, body_b.name, tags_b, last_message, collision_pos
		)


func _apply_effect(effect_type: String, effect: Dictionary, target: Node, body_a: Node, body_b: Node, tag_duration: float = 0.0, rule_id: String = "") -> void:
	match effect_type:
		"DAMAGE":
			var amount: float = _resolve_damage(effect, body_a, body_b, target, rule_id)
			var tick_interval: float = effect.get("tick_interval", 0.0)
			var tick_dur: float = effect.get("tick_duration", 0.0)
			var source: Node = body_a if target == body_b else body_b
			var element_color: Color = TagColors.derive_element_color(source)
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
			var magnitude: float = _resolve_force(effect, body_a, body_b, target, rule_id)
			var source: Node = body_b if target == body_a else body_a
			var direction: Vector2 = Vector2.ZERO
			if source is Node2D and target is Node2D:
				direction = (target.global_position - source.global_position).normalized()
			Log.debug("EffectExecutor: APPLY_FORCE %.0f on %s" % [magnitude, target.name])
			WorldMutations.apply_impulse(target, direction, magnitude)

		"APPLY_SLOW":
			pass  # Continuous per-frame effect handled by TagField

		_:
			Log.warn("EffectExecutor: Unknown effect type '%s'" % effect_type)


func _resolve_damage(effect: Dictionary, body_a: Node, body_b: Node, target: Node, rule_id: String = "") -> float:
	## V2: parameterized damage from combat_profile/substance_profile.
	var base_amount: float = effect.get("damage_amount", 0.0)

	# Get source and target blueprints
	var source: Node = body_a if target == body_b else body_b
	var source_bp: Dictionary = source.blueprint if source.has_method("get_blueprint") else {}
	var target_bp: Dictionary = target.blueprint if target.has_method("get_blueprint") else {}
	var source_combat: Dictionary = source_bp.get("combat_profile", {})
	var target_profile: Dictionary = target_bp.get("substance_profile", {})

	# Parameterized rules — use combat/substance profiles when available
	match rule_id:
		"sharp_living_cut", "sharp_breakable_damage":
			if source_combat.has("melee_damage"):
				return source_combat["melee_damage"]
		"heavy_breakable_crush":
			if source_combat.has("crush_damage"):
				return source_combat["crush_damage"]
		"heat_flammable_ignite":
			var fire_coeff: float = source_combat.get("fire_dps_coefficient", 0.0)
			var burn_rate: float = target_profile.get("burn_rate", 0.5)
			if fire_coeff > 0.0:
				return fire_coeff * burn_rate
		"electric_metallic_electrify":
			var conductivity: float = target_profile.get("conductivity", 0.5)
			return 30.0 * conductivity
		"reflective_heat_reflect":
			var heat_output: float = source_bp.get("substance_profile", {}).get("heat_output", 0.0)
			return 10.0 * heat_output

	return base_amount


func _resolve_force(effect: Dictionary, body_a: Node, body_b: Node, target: Node, rule_id: String = "") -> float:
	## V2: parameterized force from substance_profile.
	var base_magnitude: float = effect.get("force_magnitude", 100.0)

	var target_bp: Dictionary = target.blueprint if target.has_method("get_blueprint") else {}
	var target_profile: Dictionary = target_bp.get("substance_profile", {})

	match rule_id:
		"wind_light_push":
			var mass: float = target_profile.get("mass", 1.0)
			if mass > 0.0:
				return 45.0 * (0.3 / mass)

	return base_magnitude


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


func _get_collision_position(body_a: Node, body_b: Node) -> Vector2:
	if body_a is Node2D and body_b is Node2D:
		return (body_a.global_position + body_b.global_position) / 2.0
	return Vector2.ZERO
