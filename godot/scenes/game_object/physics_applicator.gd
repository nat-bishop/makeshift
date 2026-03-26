extends Node

var _body: RigidBody2D
var _collision_shape: CollisionShape2D
var _has_sprite_shape: bool = false


func _ready() -> void:
	_body = get_parent()
	_collision_shape = _body.get_node("CollisionShape2D")


func apply(tags: Array, visual_descriptor: Dictionary) -> void:
	var physics: Dictionary = PhysicsComposer.compose_physics(tags)

	# Apply mass and gravity
	_body.mass = physics["mass"]
	_body.gravity_scale = physics["gravity"]

	# Apply physics material
	var mat := PhysicsMaterial.new()
	mat.friction = physics["friction"]
	mat.bounce = physics["bounce"]
	_body.physics_material_override = mat

	# Configure collision shape from size_category and base_form
	# Skip if already using a sprite-derived shape
	if not _has_sprite_shape:
		var size_category: String = visual_descriptor.get("size_category", "medium")
		var base_form: String = visual_descriptor.get("base_form", "box")
		_configure_shape(size_category, base_form)


func update_shape_from_sprite(texture: Texture2D, world_size: float, animation: Dictionary = {}) -> void:
	var image: Image = texture.get_image()

	# For sprite sheets, extract just the first frame for collision
	if not animation.is_empty():
		var cols: int = animation.get("columns", 1)
		var rows: int = animation.get("rows", 1)
		var fw: int = image.get_width() / cols
		var fh: int = image.get_height() / rows
		image = image.get_region(Rect2i(0, 0, fw, fh))

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


func _configure_shape(size_category: String, base_form: String) -> void:
	var size_data: Dictionary = PhysicsComposer.get_size_data(size_category)
	var collision_size: int = size_data["collision"]
	var shape_type: String = PhysicsComposer.shape_from_base_form(base_form)

	match shape_type:
		"capsule":
			var capsule := CapsuleShape2D.new()
			capsule.radius = collision_size * 0.25
			capsule.height = collision_size
			_collision_shape.shape = capsule
		"circle":
			var circle := CircleShape2D.new()
			circle.radius = collision_size * 0.5
			_collision_shape.shape = circle
		_:
			var rect := RectangleShape2D.new()
			rect.size = Vector2(collision_size, collision_size)
			_collision_shape.shape = rect
