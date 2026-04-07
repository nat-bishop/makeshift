extends Node
## Client-side in-memory cache for pairwise interactions and creature behaviors.
## Receives entries from the backend via WebSocket and stores them for
## O(1) lookup at collision time.

var _pairwise: Dictionary = {}   # "a::b" -> Dictionary
var _creature: Dictionary = {}   # "creature::target" -> Dictionary
var _stale: Dictionary = {}      # "a::b" -> true


func _normalize(name: String) -> String:
	return name.strip_edges().to_lower()


func pair_key(a: String, b: String) -> String:
	var na: String = _normalize(a)
	var nb: String = _normalize(b)
	if na > nb:
		return "%s::%s" % [nb, na]
	return "%s::%s" % [na, nb]


# --- Pairwise cache ---

func store_pairwise(a: String, b: String, entry: Dictionary) -> void:
	var key: String = pair_key(a, b)
	_pairwise[key] = entry
	_stale.erase(key)


func lookup_pairwise(a: String, b: String) -> Dictionary:
	var key: String = pair_key(a, b)
	if key in _stale:
		return {}
	return _pairwise.get(key, {})


func mark_stale(object_name: String) -> void:
	var n: String = _normalize(object_name)
	for key in _pairwise.keys():
		var parts: PackedStringArray = key.split("::")
		if parts.size() == 2 and (parts[0] == n or parts[1] == n):
			_stale[key] = true


func clear_stale(a: String, b: String) -> void:
	_stale.erase(pair_key(a, b))


# --- Creature behavior cache ---

func store_creature(creature: String, target: String, entry: Dictionary) -> void:
	_creature[pair_key(creature, target)] = entry


func lookup_creature(creature: String, target: String) -> Dictionary:
	return _creature.get(pair_key(creature, target), {})


# --- Bulk loading from backend WS messages ---

func load_pairwise_batch(entries: Array) -> void:
	for e in entries:
		var a: String = e.get("name_a", "")
		var b: String = e.get("name_b", "")
		if a != "" and b != "":
			store_pairwise(a, b, e)


func load_creature_batch(creature_name: String, behaviors: Array) -> void:
	for b in behaviors:
		var target: String = b.get("target", "")
		if target != "":
			store_creature(creature_name, target, b)
