extends Node

var _pair_index: Dictionary = {}  # tag_a -> {tag_b -> [rules]}
var _wildcard_rules: Array = []
var _rules_loaded: bool = false


func load_rules(rules_json: Array) -> void:
	_pair_index.clear()
	_wildcard_rules.clear()

	for rule_data in rules_json:
		var rule: Dictionary = rule_data if rule_data is Dictionary else {}
		if rule.is_empty():
			Log.warn("RuleEngine: Skipping empty/invalid rule entry")
			continue

		var tags_b: Array = rule.get("tags_required_b", [])
		var tags_a: Array = rule.get("tags_required_a", [])

		if tags_b.is_empty():
			_wildcard_rules.append(rule)
		else:
			for tag_a in tags_a:
				for tag_b in tags_b:
					_index_rule(tag_a, tag_b, rule)
			if rule.get("bidirectional", false):
				for tag_a in tags_b:
					for tag_b in tags_a:
						_index_rule(tag_a, tag_b, rule)

	_rules_loaded = true
	Log.info("RuleEngine: Loaded %d rules (%d indexed pairs, %d wildcard)" % [rules_json.size(), _pair_index.size(), _wildcard_rules.size()])


func _index_rule(tag_a: String, tag_b: String, rule: Dictionary) -> void:
	if tag_a not in _pair_index:
		_pair_index[tag_a] = {}
	if tag_b not in _pair_index[tag_a]:
		_pair_index[tag_a][tag_b] = []
	_pair_index[tag_a][tag_b].append(rule)


func find_matching_rules(tags_a: Array, tags_b: Array) -> Array:
	var matched: Dictionary = {}  # rule_id -> rule (dedup)

	# Pair lookup
	for ta in tags_a:
		if ta in _pair_index:
			for tb in tags_b:
				if tb in _pair_index[ta]:
					for rule in _pair_index[ta][tb]:
						var blocked_by: Array = rule.get("tags_blocked_by", [])
						if not blocked_by.is_empty():
							var req_a: Array = rule.get("tags_required_a", [])
							var b_tags: Array = tags_b if ta in req_a else tags_a
							if _has_any_tag(b_tags, blocked_by):
								continue
						matched[rule.get("rule_id", "")] = rule

	# Wildcard rules (always checked)
	for rule in _wildcard_rules:
		if _wildcard_matches(rule, tags_a, tags_b):
			var blocked_by: Array = rule.get("tags_blocked_by", [])
			if not blocked_by.is_empty():
				var req_a: Array = rule.get("tags_required_a", [])
				var b_tags: Array = tags_b if _has_any_tag(tags_a, req_a) else tags_a
				if _has_any_tag(b_tags, blocked_by):
					continue
			matched[rule.get("rule_id", "")] = rule

	var result: Array = matched.values()
	result.sort_custom(func(a, b): return a.get("priority", 0) > b.get("priority", 0))
	return result


func _wildcard_matches(rule: Dictionary, tags_a: Array, tags_b: Array) -> bool:
	var required_a: Array = rule.get("tags_required_a", [])
	for tag in required_a:
		if tag in tags_a:
			continue
		if rule.get("bidirectional", false) and tag in tags_b:
			continue
		return false
	return true


func _has_any_tag(tags: Array, check: Array) -> bool:
	for tag in check:
		if tag in tags:
			return true
	return false


func is_loaded() -> bool:
	return _rules_loaded
