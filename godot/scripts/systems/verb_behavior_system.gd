extends Node

## V2 Verb Behavior System — event-driven targeting + per-frame verb execution.
##
## Perception layer: listens for object enter/exit/embedding_changed events.
##   Maintains per-behavior target lists via dot-product matching.
## Action layer: per-frame, picks best target by priority + distance, executes verb.

const MATCH_THRESHOLD: float = 0.5
const MELEE_RANGE: float = 48.0
const INVESTIGATE_RANGE: float = 128.0
const FOLLOW_RANGE: float = 64.0
const FLEE_SPEED_MULT: float = 1.5
const DESTROY_SPEED: float = 200.0
const EAT_SPEED: float = 180.0
const INVESTIGATE_SPEED: float = 80.0
const FOLLOW_SPEED: float = 160.0
const PROTECT_SPEED: float = 180.0
const FLEE_SPEED: float = 250.0
const MELEE_DAMAGE: float = 15.0
const EAT_HEAL_AMOUNT: float = 10.0
const MELEE_COOLDOWN: float = 1.0
const MAX_ERRORS: int = 5

var _owner_body: RigidBody2D
var _behaviors: Array = []  # Array of {verb, target_text, target_embedding}
var _target_lists: Array = []  # Array of Arrays — per-behavior list of matching objects
var _error_count: int = 0
var _disabled: bool = false
var _melee_timer: float = 0.0


func init_behaviors(behaviors: Array, behavior_embeddings: Array, owner: RigidBody2D) -> void:
	_owner_body = owner
	_behaviors = []
	_target_lists = []

	for i in range(behaviors.size()):
		var b: Dictionary = behaviors[i] if behaviors[i] is Dictionary else {}
		var embedding: Array = []
		if i < behavior_embeddings.size():
			embedding = behavior_embeddings[i]
		_behaviors.append({
			"verb": b.get("verb", "investigate"),
			"target_text": b.get("target", ""),
			"target_embedding": embedding,
		})
		_target_lists.append([])

	# Listen for scene events
	EventBus.object_entered_scene.connect(_on_object_entered)
	EventBus.object_exited_scene.connect(_on_object_exited)
	EventBus.object_embedding_changed.connect(_on_embedding_changed)

	# Scan existing objects already in the scene (e.g., level load)
	call_deferred("_scan_existing_objects")


func _scan_existing_objects() -> void:
	for node in _owner_body.get_tree().get_nodes_in_group("game_objects"):
		_on_object_entered(node)


func _exit_tree() -> void:
	if EventBus.object_entered_scene.is_connected(_on_object_entered):
		EventBus.object_entered_scene.disconnect(_on_object_entered)
	if EventBus.object_exited_scene.is_connected(_on_object_exited):
		EventBus.object_exited_scene.disconnect(_on_object_exited)
	if EventBus.object_embedding_changed.is_connected(_on_embedding_changed):
		EventBus.object_embedding_changed.disconnect(_on_embedding_changed)


# ---------------------------------------------------------------------------
# Perception layer (event-driven)
# ---------------------------------------------------------------------------

func _on_object_entered(game_object: Node) -> void:
	if game_object == _owner_body or not is_instance_valid(game_object):
		return
	if not game_object.has_method("get_identity_embedding"):
		return
	var obj_embedding: Array = game_object.get_identity_embedding()
	_check_object_against_all_behaviors(game_object, obj_embedding)


func _on_object_exited(game_object: Node) -> void:
	for i in range(_target_lists.size()):
		_target_lists[i].erase(game_object)


func _on_embedding_changed(game_object: Node) -> void:
	if game_object == _owner_body or not is_instance_valid(game_object):
		return
	if not game_object.has_method("get_identity_embedding"):
		return
	var obj_embedding: Array = game_object.get_identity_embedding()
	_check_object_against_all_behaviors(game_object, obj_embedding)


func _check_object_against_all_behaviors(game_object: Node, obj_embedding: Array) -> void:
	for i in range(_behaviors.size()):
		var behavior_emb: Array = _behaviors[i]["target_embedding"]
		if behavior_emb.is_empty() or obj_embedding.is_empty():
			continue
		var sim: float = _dot_product(behavior_emb, obj_embedding)
		if sim >= MATCH_THRESHOLD:
			if game_object not in _target_lists[i]:
				_target_lists[i].append(game_object)
		else:
			_target_lists[i].erase(game_object)


static func _dot_product(a: Array, b: Array) -> float:
	var result: float = 0.0
	var size: int = min(a.size(), b.size())
	for i in range(size):
		result += a[i] * b[i]
	return result


# ---------------------------------------------------------------------------
# Action layer (per-frame)
# ---------------------------------------------------------------------------

func _physics_process(delta: float) -> void:
	if _disabled or not is_instance_valid(_owner_body):
		return

	_melee_timer = maxf(0.0, _melee_timer - delta)

	# Walk behaviors in priority order (first in list = highest priority)
	for i in range(_behaviors.size()):
		var targets: Array = _target_lists[i]
		# Clean invalid references
		var j: int = 0
		while j < targets.size():
			if not is_instance_valid(targets[j]):
				targets.remove_at(j)
			else:
				j += 1

		if targets.is_empty():
			continue

		var verb: String = _behaviors[i]["verb"]
		var nearest: Node = _find_nearest(targets)
		if nearest == null:
			continue

		var success: bool = _execute_verb(verb, nearest, delta)
		if not success:
			_error_count += 1
			if _error_count >= MAX_ERRORS:
				_disabled = true
				Log.warn("VerbBehaviorSystem: Disabled after %d errors on '%s'" % [MAX_ERRORS, _owner_body.blueprint.get("name", "?")])
		else:
			_error_count = 0
		return  # Only execute the highest-priority behavior with targets


func _find_nearest(targets: Array) -> Node:
	var best: Node = null
	var best_dist: float = INF
	for t in targets:
		if not is_instance_valid(t) or not (t is Node2D):
			continue
		var d: float = _owner_body.global_position.distance_squared_to(t.global_position)
		if d < best_dist:
			best_dist = d
			best = t
	return best


func _execute_verb(verb: String, target: Node, delta: float) -> bool:
	if not (target is Node2D):
		return false

	match verb:
		"destroy":
			_move_toward(target, DESTROY_SPEED, delta)
			if _in_range(target, MELEE_RANGE) and _melee_timer <= 0.0:
				_attack(target)
				_melee_timer = MELEE_COOLDOWN
			return true

		"eat":
			_move_toward(target, EAT_SPEED, delta)
			if _in_range(target, MELEE_RANGE) and _melee_timer <= 0.0:
				_consume(target)
				_melee_timer = MELEE_COOLDOWN
			return true

		"investigate":
			if not _in_range(target, INVESTIGATE_RANGE):
				_move_toward(target, INVESTIGATE_SPEED, delta)
			return true

		"follow":
			if not _in_range(target, FOLLOW_RANGE):
				_move_toward(target, FOLLOW_SPEED, delta)
			return true

		"protect":
			# Follow the target + attack nearby HOSTILE threats
			if not _in_range(target, FOLLOW_RANGE):
				_move_toward(target, PROTECT_SPEED, delta)
			# Scan for threats near the protected target
			var threat: Node = _find_nearest_threat(target as Node2D)
			if threat != null and _melee_timer <= 0.0:
				if _in_range(threat as Node2D, MELEE_RANGE):
					_attack(threat)
					_melee_timer = MELEE_COOLDOWN
				else:
					_move_toward(threat as Node2D, DESTROY_SPEED, delta)
			return true

		"flee":
			_move_away(target, FLEE_SPEED, delta)
			return true

	return false


func _move_toward(target: Node2D, speed: float, _delta: float) -> void:
	var direction: Vector2 = (target.global_position - _owner_body.global_position).normalized()
	var desired: Vector2 = direction * speed
	var force: Vector2 = (desired - _owner_body.linear_velocity) * _owner_body.mass
	_owner_body.apply_central_force(force)


func _move_away(target: Node2D, speed: float, _delta: float) -> void:
	var direction: Vector2 = (_owner_body.global_position - target.global_position).normalized()
	var desired: Vector2 = direction * speed
	var force: Vector2 = (desired - _owner_body.linear_velocity) * _owner_body.mass
	_owner_body.apply_central_force(force)


func _in_range(target: Node2D, range_px: float) -> bool:
	return _owner_body.global_position.distance_to(target.global_position) <= range_px


func _find_nearest_threat(protected_target: Node2D) -> Node:
	## Find the nearest HOSTILE object near the protected target.
	const PROTECT_RADIUS: float = 192.0
	var best: Node = null
	var best_dist: float = INF
	for node in _owner_body.get_tree().get_nodes_in_group("game_objects"):
		if node == _owner_body or node == protected_target:
			continue
		if not is_instance_valid(node) or not (node is Node2D):
			continue
		if not node.has_method("get_tags"):
			continue
		var node_tags: Array = node.get_tags()
		if "HOSTILE" not in node_tags:
			continue
		var d: float = protected_target.global_position.distance_to(node.global_position)
		if d < PROTECT_RADIUS and d < best_dist:
			best_dist = d
			best = node
	return best


func _attack(target: Node) -> void:
	var damage: float = MELEE_DAMAGE
	# Use combat_profile if available
	var combat: Dictionary = _owner_body.blueprint.get("combat_profile", {})
	if combat.has("melee_damage"):
		damage = combat["melee_damage"]
	if target.has_method("take_damage"):
		var color: Color = TagColors.derive_element_color(_owner_body)
		target.take_damage(damage, color)


func _consume(target: Node) -> void:
	# Damage target, heal self, destroy target if health low
	_attack(target)
	if _owner_body.has_method("heal"):
		_owner_body.heal(EAT_HEAL_AMOUNT)
