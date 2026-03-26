class_name BehaviorDisplay

const TRIGGER_PHRASES: Dictionary = {
	"ALWAYS": "Always",
	"ON_TIMER": "On timer",
	"ON_PROXIMITY": "When nearby",
	"ON_CONTACT": "On contact",
	"ON_DAMAGED": "When damaged",
	"ON_HEALTH_LOW": "When health low",
	"ON_TAG_ADDED": "When %s added",
	"ON_CREATE": "On create",
	"ON_DESTROY": "On destroy",
	"ON_USE": "When used",
}

const ACTION_PHRASES: Dictionary = {
	"MOVE_TOWARD": "Moves toward %s",
	"MOVE_AWAY": "Flees from %s",
	"PATROL": "Patrols",
	"DEAL_DAMAGE": "Damages %s",
	"APPLY_FORCE": "Pushes %s",
	"ATTRACT": "Pulls %s",
	"SPAWN_PROJECTILE": "Shoots at %s",
	"EXPLODE": "Explodes",
	"HEAL": "Heals %s",
	"ADD_TAGS": "Adds %s to %s",
	"REMOVE_TAGS": "Removes %s from %s",
	"SELF_DESTRUCT": "Self-destructs",
}

const TARGET_PHRASES: Dictionary = {
	"SELF": "self",
	"NEAREST_OBJECT": "nearest object",
	"NEAREST_LIVING": "nearest creature",
	"NEAREST_PLAYER": "player",
	"CONTACT_BODY": "contact body",
}

const _DAMAGE_ACTIONS := ["DEAL_DAMAGE", "APPLY_FORCE", "ATTRACT", "SPAWN_PROJECTILE", "HEAL"]
const _MOVEMENT_ACTIONS = BehaviorMaps.MOVEMENT_ACTIONS
const _EXPLODE_ACTIONS := ["EXPLODE"]


static func format_behavior(b: Dictionary) -> String:
	var trigger: String = b.get("trigger", "?")
	var action: String = b.get("action", "?")
	var target: String = b.get("target", "SELF")

	# Build trigger phrase
	var trigger_text: String = TRIGGER_PHRASES.get(trigger, trigger)
	if trigger == "ON_TAG_ADDED":
		var tag: String = b.get("trigger_tag", "?")
		trigger_text = trigger_text % tag

	# Build action phrase
	var action_text: String = ACTION_PHRASES.get(action, action)
	var target_text: String = TARGET_PHRASES.get(target, target)
	if action in ["ADD_TAGS", "REMOVE_TAGS"]:
		var tags: Array = b.get("tags_to_apply", [])
		var tags_str: String = ", ".join(tags) if not tags.is_empty() else "?"
		action_text = action_text % [tags_str, target_text]
	elif "%s" in action_text:
		action_text = action_text % target_text

	# Append relevant param
	var param := _get_key_param(b)
	if not param.is_empty():
		action_text += " · %s" % param

	# Append condition
	var cond: Variant = b.get("condition", null)
	if cond is Dictionary:
		var cond_type: String = cond.get("condition_type", "")
		var cond_tag: String = cond.get("tag", "?")
		if cond_type == "has_tag":
			action_text += " (if has %s)" % cond_tag
		elif cond_type == "not_has_tag":
			action_text += " (if no %s)" % cond_tag
		elif cond_type == "target_has_tag":
			action_text += " (if target has %s)" % cond_tag

	return "%s · %s" % [trigger_text, action_text]


static func _get_key_param(b: Dictionary) -> String:
	var action: String = b.get("action", "")
	var intensity: String = b.get("intensity", "MEDIUM")
	var speed: String = b.get("speed", "MEDIUM")
	var range_val: String = b.get("range", "MEDIUM")

	if action in _DAMAGE_ACTIONS and intensity != "MEDIUM":
		return intensity.to_lower().capitalize()
	if action in _MOVEMENT_ACTIONS and speed != "MEDIUM":
		return speed.to_lower().replace("_", " ").capitalize()
	if action in _EXPLODE_ACTIONS:
		if intensity != "MEDIUM":
			return intensity.to_lower().capitalize()
		if range_val != "MEDIUM":
			return range_val.to_lower().capitalize()
	return ""
