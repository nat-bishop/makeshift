extends RigidBody2D

var object_id: String = ""
var blueprint: Dictionary = {}
var current_durability: int = 150
var _tag_manager: TagManager = null
var _behavior_system: Node = null
var _tag_field: Node = null

# Embedding for semantic targeting
var _identity_embedding: Array = []

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

	# Initialize tag manager
	_tag_manager = TagManager.new()
	_tag_manager.name = "TagManager"
	add_child(_tag_manager)
	_tag_manager.init_tags(bp.get("tags", []), bp.get("name", "?"))
	_tag_manager.tag_added.connect(_on_tag_added)
	_tag_manager.tags_changed.connect(_on_tags_changed)

	current_durability = bp.get("starting_durability", 150)

	# Substance-based physics
	physics_applicator.apply_from_blueprint(bp)
	object_visual.set_object_id(object_id)
	object_visual.init_programmatic_anims(tags)

	# Add to groups
	add_to_group("game_objects")
	if "LIVING" in tags:
		add_to_group("living")

	# Store identity embedding
	_identity_embedding = bp.get("identity_embedding", [])

	# Verb behavior system
	var compiled_behaviors: Array = bp.get("compiled_behaviors", [])
	if not compiled_behaviors.is_empty():
		var vbs_script = preload("res://scripts/systems/verb_behavior_system.gd")
		_behavior_system = vbs_script.new()
		_behavior_system.name = "VerbBehaviorSystem"
		add_child(_behavior_system)
		_behavior_system.init_behaviors(compiled_behaviors, self)

	# Initialize field system if object has field-emitting tags
	if FieldConfig.has_any_field_tag(tags):
		_create_tag_field(tags)

	# Debug label
	var debug_label_script: GDScript = preload("res://scripts/ui/debug_label.gd")
	var debug_label := PanelContainer.new()
	debug_label.set_script(debug_label_script)
	add_child(debug_label)
	debug_label.init(self)

	Log.info("GameObject: Initialized '%s' (id=%s) with %d tags, %d behaviors, durability=%d" % [bp.get("name", "?"), object_id, tags.size(), behaviors.size(), current_durability])

	# Notify scene after node enters tree (deferred to ensure _ready() completes first)
	call_deferred("_emit_entered_scene")


func _emit_entered_scene() -> void:
	EventBus.object_entered_scene.emit(self)


func _exit_tree() -> void:
	EventBus.object_exited_scene.emit(self)


func get_blueprint() -> Dictionary:
	return blueprint


var tags: Array[String]:
	get: return _tag_manager.tags if _tag_manager != null else []


func get_tags() -> Array[String]:
	return tags


func get_object_id() -> String:
	return object_id


func get_identity_embedding() -> Array:
	return _identity_embedding


func is_passively_pushable() -> bool:
	if "HEAVY" in tags:
		return false
	var size: String = blueprint.get("visual_descriptor", {}).get("size_category", "medium")
	return size == "tiny"


func is_heavy() -> bool:
	return "HEAVY" in tags


func take_damage(amount: float, element_color: Color = Color.WHITE) -> void:
	current_durability -= int(amount)
	Log.debug("GameObject: '%s' took %.0f damage, durability=%d" % [blueprint.get("name", object_id), amount, current_durability])
	object_visual.flash_hit(element_color)

	if current_durability <= 0:
		Log.info("GameObject: '%s' (id=%s) destroyed, final durability=%d" % [blueprint.get("name", "?"), object_id, current_durability])
		queue_free()
		return


func heal(amount: float) -> void:
	var starting: int = blueprint.get("starting_durability", 150)
	current_durability = min(current_durability + int(amount), starting)
	Log.debug("GameObject: '%s' healed %.0f, durability=%d" % [blueprint.get("name", object_id), amount, current_durability])
	object_visual.flash_hit(TagColors.HEAL)


func add_tag(tag: String, duration: float = 0.0) -> void:
	_tag_manager.add_tag(tag, duration)


func remove_tag(tag: String) -> void:
	_tag_manager.remove_tag(tag)


func _on_tag_added(tag: String) -> void:
	if tag in TagColors.COLORS:
		object_visual.spawn_particles(TagColors.get_color(tag))
	# Create tag field if this is the first field tag
	if _tag_field == null and FieldConfig.is_field_tag(tag):
		_create_tag_field(tags)


func _on_tags_changed(_updated_tags: Array[String]) -> void:
	_reapply_physics()
	object_visual.refresh_tag_visuals(tags)
	if _tag_field != null:
		_tag_field.on_tags_changed(tags)
	# Notify behavior systems to re-evaluate tag filters (no re-embedding needed)
	EventBus.object_tags_changed.emit(self)


func get_cascade_neighbors() -> Array:
	var neighbors: Array = []
	for body in cascade_area.get_overlapping_bodies():
		if body != self and body.has_method("get_tags"):
			neighbors.append(body)
	return neighbors


func _create_tag_field(current_tags: Array) -> void:
	var field_script = preload("res://scripts/systems/tag_field.gd")
	_tag_field = field_script.new()
	_tag_field.name = "TagField"
	add_child(_tag_field)
	_tag_field.init_field(self, current_tags)


func _reapply_physics() -> void:
	# Re-resolve physics with current tags (tag modifiers like HEAVY/LIGHT/FLYING
	# affect mass, gravity, friction, bounce, damping at runtime)
	var base_physics: Dictionary = SubstancePhysics.resolve_physics(blueprint)
	var modified: Dictionary = SubstancePhysics.apply_tag_modifiers(base_physics, tags)
	var size_category: String = blueprint.get("visual_descriptor", {}).get("size_category", "medium")
	physics_applicator.apply_physics(modified, size_category)


func _on_body_entered(body: Node) -> void:
	if not TagColors.is_taggable(body):
		return
	call_deferred("_resolve_deferred", body)


func _resolve_deferred(body: Node) -> void:
	if not is_instance_valid(body):
		return
	CollisionResolver.resolve_and_notify(self, body)
