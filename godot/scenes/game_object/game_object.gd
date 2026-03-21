extends RigidBody2D

var object_id: String = ""
var object_name: String = ""
var tags: Array = []
var blueprint: Dictionary = {}
var current_durability: int = 150

var _collision_cooldowns: Dictionary = {}  # body_id -> time_remaining
const COLLISION_COOLDOWN: float = 0.5

@onready var physics_applicator: Node = $PhysicsApplicator
@onready var object_visual: Node = $ObjectVisual
@onready var cascade_area: Area2D = $CascadeArea


func _ready() -> void:
	collision_layer = 4  # Objects layer
	collision_mask = 1 | 2 | 4  # Terrain + Player + Objects
	body_entered.connect(_on_body_entered)
	contact_monitor = true
	max_contacts_reported = 4


func _physics_process(delta: float) -> void:
	# Update collision cooldowns
	var to_remove: Array = []
	for body_id in _collision_cooldowns:
		_collision_cooldowns[body_id] -= delta
		if _collision_cooldowns[body_id] <= 0.0:
			to_remove.append(body_id)
	for body_id in to_remove:
		_collision_cooldowns.erase(body_id)


func init_from_blueprint(bp: Dictionary) -> void:
	blueprint = bp
	object_id = bp.get("id", "")
	object_name = bp.get("name", "Unknown")
	tags = bp.get("tags", [])

	current_durability = bp.get("starting_durability", 150)

	var visual_descriptor: Dictionary = bp.get("visual_descriptor", {})
	physics_applicator.apply(tags, visual_descriptor)
	object_visual.set_object_id(object_id)
	object_visual.set_placeholder(visual_descriptor)


func get_blueprint() -> Dictionary:
	return blueprint


func get_tags() -> Array:
	return tags


func take_damage(amount: int) -> void:
	current_durability -= amount
	if current_durability <= 0:
		queue_free()


func add_tag(tag: String) -> void:
	if tag not in tags:
		tags.append(tag)
		_reapply_physics()


func remove_tag(tag: String) -> void:
	tags.erase(tag)
	_reapply_physics()


func _reapply_physics() -> void:
	var visual_descriptor: Dictionary = blueprint.get("visual_descriptor", {})
	physics_applicator.apply(tags, visual_descriptor)


func _on_body_entered(body: Node) -> void:
	var body_id: int = body.get_instance_id()

	# Check cooldown
	if body_id in _collision_cooldowns:
		return
	_collision_cooldowns[body_id] = COLLISION_COOLDOWN

	# Get other body's tags
	var other_tags: Array = []
	if body.has_method("get_tags"):
		other_tags = body.get_tags()
	elif body.has_method("get_effective_tags"):
		other_tags = body.get_effective_tags()
	else:
		return

	# Find matching rules
	var rules: Array = RuleEngine.find_matching_rules(tags, other_tags)
	if rules.is_empty():
		return

	# Resolve via CollisionResolver if it exists
	var collision_resolver = get_node_or_null("/root/CollisionResolver")
	if collision_resolver and collision_resolver.has_method("resolve"):
		collision_resolver.resolve(self, body, rules)


func get_cascade_neighbors() -> Array:
	var neighbors: Array = []
	for body in cascade_area.get_overlapping_bodies():
		if body != self and body.has_method("get_tags"):
			neighbors.append(body)
	return neighbors
