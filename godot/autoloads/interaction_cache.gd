extends Node
## Client-side cache for collision rules and creature behaviors.
## Two flat dicts, no staleness tracking — server pushes updates, client overwrites.
## Collision rules: force-only pairwise data (persistent on backend).
## Behaviors: creature AI decisions (session-local on backend).

var _collision: Dictionary = {}      # "a::b" -> {force_on_b: int}
var _behavior: Dictionary = {}       # "creature::target" -> {movement, priority, action, ...}
var _pending_evals: Dictionary = {}  # "a::b" -> true (dedup for lazy eval requests)


func _normalize(name: String) -> String:
	var parts: PackedStringArray = name.strip_edges().to_lower().split(" ", false)
	return " ".join(parts)


func pair_key(a: String, b: String) -> String:
	var na: String = _normalize(a)
	var nb: String = _normalize(b)
	if na > nb:
		return "%s::%s" % [nb, na]
	return "%s::%s" % [na, nb]


# --- Collision rules (force only) ---

func store_collision(a: String, b: String, entry: Dictionary) -> void:
	var key: String = pair_key(a, b)
	_collision[key] = entry
	_pending_evals.erase(key)


func lookup_collision(a: String, b: String) -> Dictionary:
	return _collision.get(pair_key(a, b), {})


func request_collision_eval(name_a: String, name_b: String) -> void:
	## Request lazy evaluation from backend on cache miss.
	## Deduplicates: won't send the same pair twice until result arrives.
	var key: String = pair_key(name_a, name_b)
	if key in _pending_evals:
		return
	_pending_evals[key] = true
	Backend.send_collision_request(name_a, name_b)


# --- Creature behavior ---

func store_behavior(creature: String, target: String, entry: Dictionary) -> void:
	_behavior[pair_key(creature, target)] = entry


func lookup_behavior(creature_name: String, target_name: String) -> Dictionary:
	return _behavior.get(pair_key(creature_name, target_name), {})


# --- Bulk loading from backend WS messages ---

func load_collision_batch(entries: Array) -> void:
	for e in entries:
		var a: String = e.get("name_a", "")
		var b: String = e.get("name_b", "")
		if a != "" and b != "":
			store_collision(a, b, e)


func load_behavior_batch(creature_name: String, behaviors: Array) -> void:
	for b in behaviors:
		var target: String = b.get("target_name", "")
		if target.is_empty():
			target = b.get("target", "")
		if not target.is_empty():
			store_behavior(creature_name, target, b)
