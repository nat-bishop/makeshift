extends RigidBody2D

var object_id: String = ""
var tags: Array[String] = []
var blueprint: Dictionary = {}
var current_durability: int = 150
var _tag_decay: TagDecay = null
var _behavior_executor: Node = null
var _tag_field: Node = null

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

	_tag_decay = TagDecay.new()
	_tag_decay.name = "TagDecay"
	add_child(_tag_decay)
	var raw_tags: Array = bp.get("tags", [])
	tags.clear()
	for tag in raw_tags:
		tags.append(str(tag))

	current_durability = bp.get("starting_durability", 150)

	var visual_descriptor: Dictionary = bp.get("visual_descriptor", {})
	physics_applicator.apply(tags, visual_descriptor)
	object_visual.set_object_id(object_id)
	object_visual.init_programmatic_anims(tags)

	# Add to groups for behavior target resolution
	add_to_group("game_objects")
	if "LIVING" in tags:
		add_to_group("living")

	# Initialize behavior system if behaviors present
	var behaviors: Array = bp.get("behaviors", [])
	if not behaviors.is_empty():
		var executor_script = preload("res://scripts/systems/behavior_executor.gd")
		_behavior_executor = executor_script.new()
		_behavior_executor.name = "BehaviorExecutor"
		add_child(_behavior_executor)
		_behavior_executor.init_behaviors(behaviors, self)

	# Initialize field system if object has field-emitting tags
	if FieldConfig.has_any_field_tag(tags):
		_create_tag_field(tags)

	# Debug label for overlay
	var debug_label_script: GDScript = preload("res://scripts/ui/debug_label.gd")
	var debug_label := PanelContainer.new()
	debug_label.set_script(debug_label_script)
	add_child(debug_label)
	debug_label.init(self)

	Log.info("GameObject: Initialized '%s' (id=%s) with %d tags, %d behaviors, durability=%d" % [bp.get("name", "?"), object_id, tags.size(), behaviors.size(), current_durability])


func get_blueprint() -> Dictionary:
	return blueprint


func get_tags() -> Array[String]:
	return tags


func get_object_id() -> String:
	return object_id


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
		if _behavior_executor != null:
			_behavior_executor.fire_trigger("ON_DESTROY")
		Log.info("GameObject: '%s' (id=%s) destroyed, final durability=%d" % [blueprint.get("name", "?"), object_id, current_durability])
		queue_free()
		return

	# Fire damage-related behavior triggers
	if _behavior_executor != null:
		_behavior_executor.fire_trigger("ON_DAMAGED")
		var starting: int = blueprint.get("starting_durability", 150)
		if current_durability < starting / 2:
			_behavior_executor.fire_trigger("ON_HEALTH_LOW")


func heal(amount: float) -> void:
	var starting: int = blueprint.get("starting_durability", 150)
	current_durability = min(current_durability + int(amount), starting)
	Log.debug("GameObject: '%s' healed %.0f, durability=%d" % [blueprint.get("name", object_id), amount, current_durability])
	object_visual.flash_hit(TagColors.HEAL)


func add_tag(tag: String, duration: float = 0.0) -> void:
	var is_new: bool = tag not in tags
	if is_new:
		tags.append(tag)
		Log.debug("GameObject: '%s' +tag %s%s" % [blueprint.get("name", object_id), tag, " (%.1fs)" % duration if duration > 0.0 else ""])
		_reapply_physics()
		object_visual.refresh_tag_visuals(tags)
		if tag in TagColors.COLORS:
			object_visual.spawn_particles(TagColors.get_color(tag))
		if _behavior_executor != null:
			_behavior_executor.on_tag_added(tag)
		# Update or create tag field for dynamic field tags (e.g., fire spread)
		if _tag_field != null:
			_tag_field.on_tags_changed(tags)
		elif FieldConfig.has_any_field_tag(tags):
			_create_tag_field(tags)
	if duration > 0.0:
		_tag_decay.set_decay(tag, duration)
	if is_new:
		Log.debug("GameObject: '%s' tags now: %s" % [blueprint.get("name", object_id), tags])


func remove_tag(tag: String) -> void:
	_tag_decay.cancel(tag)
	if tag not in tags:
		return
	Log.debug("GameObject: '%s' -tag %s" % [blueprint.get("name", object_id), tag])
	tags.erase(tag)
	Log.debug("GameObject: '%s' tags now: %s" % [blueprint.get("name", object_id), tags])
	_reapply_physics()
	object_visual.refresh_tag_visuals(tags)
	if _tag_field != null:
		_tag_field.on_tags_changed(tags)


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
	var visual_descriptor: Dictionary = blueprint.get("visual_descriptor", {})
	physics_applicator.apply(tags, visual_descriptor)


func fire_behavior_trigger(trigger_name: String, source: Node = null) -> void:
	if _behavior_executor != null:
		_behavior_executor.fire_trigger(trigger_name, source)


func _on_body_entered(body: Node) -> void:
	if not TagColors.is_taggable(body):
		return
	# Defer to avoid "Can't change state while flushing queries" —
	# collision resolution can chain to add_tag → _reapply_physics → new shapes.
	call_deferred("_resolve_deferred", body)


func _resolve_deferred(body: Node) -> void:
	if not is_instance_valid(body):
		return
	CollisionResolver.resolve_collision(self, body)
	if _behavior_executor != null:
		_behavior_executor.fire_trigger("ON_CONTACT", body)
