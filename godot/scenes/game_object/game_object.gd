extends RigidBody2D

var object_id: String = ""
var tags: Array = []
var blueprint: Dictionary = {}
var current_durability: int = 150
var _decay_timers: Dictionary = {}  # tag name -> Timer

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
	tags = bp.get("tags", [])

	current_durability = bp.get("starting_durability", 150)

	var visual_descriptor: Dictionary = bp.get("visual_descriptor", {})
	physics_applicator.apply(tags, visual_descriptor)
	object_visual.set_object_id(object_id)
	object_visual.set_placeholder(visual_descriptor)
	Log.info("GameObject: Initialized '%s' (id=%s) with %d tags, durability=%d" % [bp.get("name", "?"), object_id, tags.size(), current_durability])


func get_blueprint() -> Dictionary:
	return blueprint


func get_tags() -> Array:
	return tags


func get_object_id() -> String:
	return object_id


func take_damage(amount: float) -> void:
	current_durability -= int(amount)
	Log.debug("GameObject: '%s' took %.0f damage, durability=%d" % [blueprint.get("name", object_id), amount, current_durability])
	if current_durability <= 0:
		Log.info("GameObject: '%s' (id=%s) destroyed" % [blueprint.get("name", "?"), object_id])
		queue_free()


func add_tag(tag: String, duration: float = 0.0) -> void:
	if tag not in tags:
		tags.append(tag)
		Log.debug("GameObject: '%s' +tag %s%s" % [blueprint.get("name", object_id), tag, " (%.1fs)" % duration if duration > 0.0 else ""])
		_reapply_physics()
	if duration > 0.0:
		# Cancel existing decay timer for this tag (refresh duration)
		if tag in _decay_timers and is_instance_valid(_decay_timers[tag]):
			_decay_timers[tag].queue_free()
		var timer := Timer.new()
		timer.wait_time = duration
		timer.one_shot = true
		timer.timeout.connect(remove_tag.bind(tag))
		add_child(timer)
		timer.start()
		_decay_timers[tag] = timer


func remove_tag(tag: String) -> void:
	if tag in tags:
		Log.debug("GameObject: '%s' -tag %s" % [blueprint.get("name", object_id), tag])
	tags.erase(tag)
	_reapply_physics()


func get_cascade_neighbors() -> Array:
	var neighbors: Array = []
	for body in cascade_area.get_overlapping_bodies():
		if body != self and body.has_method("get_tags"):
			neighbors.append(body)
	return neighbors


func _reapply_physics() -> void:
	var visual_descriptor: Dictionary = blueprint.get("visual_descriptor", {})
	physics_applicator.apply(tags, visual_descriptor)


func _on_body_entered(body: Node) -> void:
	if not body.has_method("get_tags") and not body.has_method("get_effective_tags"):
		return
	CollisionResolver.resolve_collision(self, body)
