extends RigidBody2D

var object_id: String = ""
var blueprint: Dictionary = {}
var current_durability: int = 100
var _state_manager: StateManager = null
var _behavior_system: Node = null
var _field_system: Node = null
var _autonomous: bool = false
var _states: Array = []

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

	# Initialize state manager
	_state_manager = StateManager.new()
	_state_manager.name = "StateManager"
	add_child(_state_manager)
	_state_manager.init_states(bp.get("states", []), bp.get("name", "?"))
	_state_manager.state_added.connect(_on_state_added)
	_state_manager.states_changed.connect(_on_states_changed)
	_states = _state_manager.states

	# Durability from blueprint hp (scale to game units)
	var hp: int = bp.get("hp", 50)
	current_durability = hp * 2 if hp > 0 else 9999
	if bp.get("indestructible", false):
		current_durability = 99999

	# Classification
	_autonomous = bp.get("autonomous", false)

	# V3 physics — read directly from blueprint
	physics_applicator.apply_from_blueprint(bp)
	object_visual.set_object_id(object_id)
	object_visual.init_from_blueprint(bp)

	# Add to groups
	add_to_group("game_objects")
	if _autonomous:
		add_to_group("living")

	# Field system
	if bp.get("has_field", false):
		_create_field_system(bp)

	# Debug label
	var debug_label_script: GDScript = preload("res://scripts/ui/debug_label.gd")
	var debug_label := PanelContainer.new()
	debug_label.set_script(debug_label_script)
	add_child(debug_label)
	debug_label.init(self)

	Log.info("GameObject: V3 init '%s' (id=%s) hp=%d, autonomous=%s" % [bp.get("name", "?"), object_id, current_durability, _autonomous])

	# Notify scene after node enters tree
	call_deferred("_emit_entered_scene")


func _emit_entered_scene() -> void:
	EventBus.object_entered_scene.emit(self)


func _exit_tree() -> void:
	EventBus.object_exited_scene.emit(self)


func get_blueprint() -> Dictionary:
	return blueprint


# V3: states replace tags
func get_states() -> Array:
	return _states


# Backward compat alias
func get_tags() -> Array:
	return _states


var tags: Array:
	get: return _states


func get_object_id() -> String:
	return object_id


func get_categories() -> Array:
	# V3: no explicit categories — autonomous objects are CREATURE
	if _autonomous:
		return ["CREATURE"]
	return []


func is_passively_pushable() -> bool:
	var size: String = blueprint.get("visual_descriptor", {}).get("size_category", "medium")
	return size == "tiny" and blueprint.get("mass_kg", 1.0) < 2.0


func is_heavy() -> bool:
	return blueprint.get("mass_kg", 1.0) > 20.0


func take_damage(amount: float, element_color: Color = Color.WHITE) -> void:
	if blueprint.get("indestructible", false):
		return
	current_durability -= int(amount)
	Log.debug("GameObject: '%s' took %.0f damage, durability=%d" % [blueprint.get("name", object_id), amount, current_durability])
	object_visual.flash_hit(element_color)

	if current_durability <= 0:
		Log.info("GameObject: '%s' (id=%s) destroyed" % [blueprint.get("name", "?"), object_id])
		queue_free()
		return


func heal(amount: float) -> void:
	var max_dur: int = blueprint.get("hp", 50) * 2
	current_durability = min(current_durability + int(amount), max_dur)
	Log.debug("GameObject: '%s' healed %.0f, durability=%d" % [blueprint.get("name", object_id), amount, current_durability])
	object_visual.flash_hit(StateColors.HEAL)


func add_state(state: String, duration: float = 0.0) -> void:
	_state_manager.add_state(state, duration)


func remove_state(state: String) -> void:
	_state_manager.remove_state(state)


# Backward compat aliases
func add_tag(tag: String, duration: float = 0.0) -> void:
	add_state(tag, duration)


func remove_tag(tag: String) -> void:
	remove_state(tag)


func _on_state_added(state: String) -> void:
	if state in StateColors.COLORS:
		object_visual.spawn_particles(StateColors.get_color(state))


func _on_states_changed(updated_states: Array) -> void:
	_states = updated_states
	object_visual.refresh_state_visuals(_states)
	if _field_system != null:
		_field_system.on_states_changed(_states)
	EventBus.object_tags_changed.emit(self)
	# Debounce re-evaluation requests to avoid LLM API spam during cascades
	_schedule_reevaluation()


var _reeval_pending: bool = false

func _schedule_reevaluation() -> void:
	if _reeval_pending:
		return
	_reeval_pending = true
	get_tree().create_timer(0.5).timeout.connect(func():
		_reeval_pending = false
		Backend.request_reevaluation(object_id, "state_change")
	)


func get_cascade_neighbors() -> Array:
	var neighbors: Array = []
	for body in cascade_area.get_overlapping_bodies():
		if body != self and (body.has_method("get_states") or body.has_method("get_tags")):
			neighbors.append(body)
	return neighbors


func _create_field_system(bp: Dictionary) -> void:
	var field_script = preload("res://scripts/systems/field_system.gd")
	_field_system = field_script.new()
	_field_system.name = "FieldSystem"
	add_child(_field_system)
	_field_system.init_field(self, bp)


func _on_body_entered(body: Node) -> void:
	if not (body.has_method("get_states") or body.has_method("get_tags")):
		return
	call_deferred("_resolve_deferred", body)


func _resolve_deferred(body: Node) -> void:
	if not is_instance_valid(body):
		return
	CollisionResolver.resolve_and_notify(self, body)
