extends Node

var _body: RigidBody2D
var _collision_shape: CollisionShape2D
var _has_sprite_shape: bool = false
var _prev_friction: float = -1.0
var _prev_bounce: float = -1.0


func _ready() -> void:
	_body = get_parent()
	_collision_shape = _body.get_node("CollisionShape2D")


func apply(tags: Array, visual_descriptor: Dictionary) -> void:
	var physics: Dictionary = PhysicsComposer.compose_physics(tags)
	var size_category: String = visual_descriptor.get("size_category", "medium")

	# Apply mass (scaled by size) and gravity
	var size_mass_mult: float = PhysicsComposer.get_size_mass_multiplier(size_category)
	_body.mass = physics["mass"] * size_mass_mult
	_body.gravity_scale = physics["gravity"]
	_body.linear_damp = physics["damping"]

	# Apply physics material (skip if unchanged to avoid waking the physics body)
	var new_friction: float = physics["friction"]
	var new_bounce: float = physics["bounce"]
	if new_friction != _prev_friction or new_bounce != _prev_bounce:
		var mat := PhysicsMaterial.new()
		mat.friction = new_friction
		mat.bounce = new_bounce
		_body.physics_material_override = mat
		_prev_friction = new_friction
		_prev_bounce = new_bounce

	Log.debug("PhysicsApplicator: Applied physics for '%s' — size=%s, mass=%.1f, friction=%.2f, bounce=%.2f, gravity=%.1f, damp=%.1f" % [_body.blueprint.get("name", ""), size_category, _body.mass, physics["friction"], physics["bounce"], physics["gravity"], physics["damping"]])

	# Configure fallback collision shape from size_category
	# Will be overridden by sprite-derived shape once sprite loads
	if not _has_sprite_shape:
		_configure_shape(size_category)


func update_shape_from_sprite(texture: Texture2D, world_size: float) -> void:
	var image: Image = texture.get_image()

	var used_rect: Rect2i = image.get_used_rect()
	if used_rect.size.x == 0 or used_rect.size.y == 0:
		return

	# Scale from texture pixels to world units
	var tex_size: float = float(image.get_width())
	var world_scale: float = world_size / tex_size

	# Offset: shift collision center to match opaque region center
	var sprite_center := Vector2(tex_size / 2.0, float(image.get_height()) / 2.0)
	var rect_center := Vector2(
		used_rect.position.x + used_rect.size.x / 2.0,
		used_rect.position.y + used_rect.size.y / 2.0
	)

	var rect := RectangleShape2D.new()
	rect.size = Vector2(used_rect.size.x, used_rect.size.y) * world_scale
	_collision_shape.shape = rect
	_collision_shape.position = (rect_center - sprite_center) * world_scale
	_has_sprite_shape = true
	Log.debug("PhysicsApplicator: Sprite shape %s offset %s" % [rect.size, _collision_shape.position])


func _configure_shape(size_category: String) -> void:
	var size_data: Dictionary = PhysicsComposer.get_size_data(size_category)
	var collision_size: int = size_data["collision"]
	var rect := RectangleShape2D.new()
	rect.size = Vector2(collision_size, collision_size)
	_collision_shape.shape = rect
	Log.debug("PhysicsApplicator: Fallback shape rect (collision_size=%d) for '%s'" % [collision_size, _body.blueprint.get("name", "")])
