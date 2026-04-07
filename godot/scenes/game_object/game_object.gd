extends RigidBody2D

## V3 GameObject: LLM-generated physics, states instead of tags,
## affordance instead of categories, no behavior verbs.

var object_id: String = ""
var blueprint: Dictionary = {}
var object_name: String = ""
var current_hp: int = 50
var armor: int = 30
var affordance: int = 3  # 0=carry 1=mount 2=climb 3=nothing
var autonomous: bool = false
var _state_manager: StateManager = null
var _object_field: Node = null
var _creature_behavior: Node = null

@onready var physics_applicator: Node = $PhysicsApplicator
@onready var object_visual: Node = $ObjectVisual
@onready var cascade_area: Area2D = $CascadeArea


func _ready() -> void:
	collision_layer = CollisionLayers.OBJECTS
	collision_mask = CollisionLayers.TERRAIN | CollisionLayers.PLAYER | CollisionLayers.OBJECTS
	body_entered.connect(_on_body_entered)
	contact_monitor = true
	max_contacts_reported = 4


func init_from_blueprint(bp: Dictionary) -> void:
	blueprint = bp
	object_id = bp.get("id", "")
	object_name = bp.get("name", "")

	# Destructibility
	var dest: Dictionary = bp.get("destructibility", {})
	current_hp = dest.get("hp", 50)
	armor = dest.get("armor", 30)
	var indestructible: bool = dest.get("indestructible", false)
	if indestructible:
		current_hp = 999999

	# Classification
	affordance = bp.get("affordance", 3)
	autonomous = bp.get("autonomous", false)

	# State manager (objects are born stateless)
	_state_manager = StateManager.new()
	_state_manager.name = "StateManager"
	add_child(_state_manager)
	_state_manager.init_states(object_name)
	_state_manager.state_added.connect(_on_state_added)
	_state_manager.states_changed.connect(_on_states_changed)

	# Physics from LLM-generated values
	physics_applicator.apply_from_blueprint(bp)

	# Visual
	object_visual.set_object_id(object_id)
	object_visual.init_visuals(bp)

	# Groups
	add_to_group("game_objects")
	if autonomous:
		add_to_group("living")

	# Field system
	var has_field: bool = bp.get("has_field", false)
	var field_range: int = bp.get("field_range_cm", 0)
	if has_field and field_range > 0:
		_create_object_field(field_range)

	# Creature behavior
	if autonomous:
		_create_creature_behavior()

	# Debug label
	var debug_label_script: GDScript = preload("res://scripts/ui/debug_label.gd")
	var debug_label := PanelContainer.new()
	debug_label.set_script(debug_label_script)
	add_child(debug_label)
	debug_label.init(self)

	Log.info("GameObject: Initialized '%s' (id=%s) hp=%d armor=%d affordance=%d" % [
		object_name, object_id, current_hp, armor, affordance
	])


func get_object_name() -> String:
	return object_name


func get_blueprint() -> Dictionary:
	return blueprint


func get_states() -> Array:
	return _state_manager.get_states() if _state_manager != null else []


func get_tags() -> Array[String]:
	## Compatibility: return states as "tags" for systems that expect get_tags().
	var result: Array[String] = []
	for s in get_states():
		result.append(s)
	return result


func get_object_id() -> String:
	return object_id


func take_damage(amount: float, _element_color: Color = Color.WHITE) -> void:
	# Armor reduces incoming damage. Corroded state halves armor effectiveness.
	var effective_armor: int = armor
	if _state_manager != null and _state_manager.has_state("corroded"):
		effective_armor = int(armor * 0.5)
	var effective: float = amount * (1.0 - effective_armor / 100.0)
	current_hp -= int(maxf(effective, 1.0))  # Minimum 1 damage

	object_visual.flash_hit(_element_color)

	if current_hp <= 0:
		Log.info("GameObject: '%s' destroyed" % object_name)
		queue_free()


func heal(amount: float) -> void:
	var max_hp: int = blueprint.get("destructibility", {}).get("hp", 50)
	current_hp = mini(current_hp + int(amount), max_hp)
	object_visual.flash_hit(StateVisuals.HEAL_COLOR)


func add_state(state: String, duration: float = 0.0) -> void:
	if _state_manager != null:
		_state_manager.add_state(state, duration)


func remove_state(state: String) -> void:
	if _state_manager != null:
		_state_manager.remove_state(state)


func _on_state_added(state: String) -> void:
	# Visual feedback
	if state in StateVisuals.COLORS:
		object_visual.spawn_particles(StateVisuals.COLORS[state])
	# Mark pairwise cache stale
	InteractionCache.mark_stale(object_name)
	# Frozen → immobilize
	if state == "frozen":
		freeze = true


func _on_states_changed(_updated_states: Array) -> void:
	# Refresh visuals
	object_visual.refresh_state_visuals(get_states())
	# Unfreeze if no longer frozen
	if _state_manager != null and not _state_manager.has_state("frozen"):
		freeze = false
	# Notify backend for lazy re-evaluation
	# Backend.send_state_changed(object_name, get_states())  # wired in Phase 8a


func get_cascade_neighbors() -> Array:
	var neighbors: Array = []
	for body in cascade_area.get_overlapping_bodies():
		if body != self and body.has_method("get_object_name"):
			neighbors.append(body)
	return neighbors


func _create_creature_behavior() -> void:
	var cb_script = preload("res://scripts/systems/creature_behavior.gd")
	_creature_behavior = cb_script.new()
	_creature_behavior.name = "CreatureBehavior"
	add_child(_creature_behavior)
	_creature_behavior.init_creature(self, object_name)


func _create_object_field(range_cm: int) -> void:
	var field_script = preload("res://scripts/systems/object_field.gd")
	_object_field = field_script.new()
	_object_field.name = "ObjectField"
	add_child(_object_field)
	_object_field.init_field(self, float(range_cm))


func is_passively_pushable() -> bool:
	var phys: Dictionary = blueprint.get("physics", {})
	return phys.get("mass_kg", 1.0) < 0.5


func is_heavy() -> bool:
	var phys: Dictionary = blueprint.get("physics", {})
	return phys.get("mass_kg", 1.0) > 50.0


func _on_body_entered(body: Node) -> void:
	if not body.has_method("get_object_name") and not body.has_method("get_states"):
		return
	call_deferred("_resolve_deferred", body)


func _resolve_deferred(body: Node) -> void:
	if not is_instance_valid(body):
		return
	CollisionResolver.resolve_collision(self, body)
