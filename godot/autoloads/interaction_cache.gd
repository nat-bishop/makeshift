extends Node
## Client-side cache for object behaviors.
## Flat dict, no staleness tracking — server pushes updates, client overwrites.
## Behaviors: per subject x target behavioral data (session-local on backend).

var _behavior: Dictionary = {}       # "subject::target" -> {movement, priority, action, ...}


func _normalize(name: String) -> String:
	var parts: PackedStringArray = name.strip_edges().to_lower().split(" ", false)
	return " ".join(parts)


func directed_key(subject: String, target: String) -> String:
	return "%s::%s" % [_normalize(subject), _normalize(target)]


# --- Object behavior ---

func store_behavior(subject: String, target: String, entry: Dictionary) -> void:
	_behavior[directed_key(subject, target)] = entry


func lookup_behavior(subject_name: String, target_name: String) -> Dictionary:
	return _behavior.get(directed_key(subject_name, target_name), {})


# --- Bulk loading from backend WS messages ---

func load_behavior_batch(subject_name: String, behaviors: Array) -> void:
	for b in behaviors:
		var target: String = b.get("target_name", "")
		if target.is_empty():
			target = b.get("target", "")
		if not target.is_empty():
			store_behavior(subject_name, target, b)
