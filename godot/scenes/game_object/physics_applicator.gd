extends Node

var _body: RigidBody2D
var _collision_shape: CollisionShape2D
var _has_sprite_shape: bool = false
var _prev_friction: float = -1.0
var _prev_bounce: float = -1.0


func _ready() -> void:
	_body = get_parent()
	_collision_shape = _body.get_node("CollisionShape2D")


func apply_from_blueprint(bp: Dictionary) -> void:
	## V3: Read physics directly from blueprint fields (LLM-generated).
	var mass_kg: float = bp.get("mass_kg", 1.0)
	var friction_pct: int = bp.get("friction", 50)
	var bounce_pct: int = bp.get("bounce", 0)
	var gravity_pct: int = bp.get("gravity", 50)
	var height_cm: int = bp.get("height_cm", 50)

	# Damping: light large things (feather) = high, heavy small (bullet) = low
	var damping: float = clampf(float(height_cm) / (mass_kg * 100.0 + 10.0), 0.0, 10.0)

	# Gravity: 0 -> -0.5 (floats), 50 -> 1.0 (normal), 100 -> 2.0 (heavy)
	var gravity_scale: float = lerpf(-0.5, 2.0, gravity_pct / 100.0)

	var size_cat: String = bp.get("visual_descriptor", {}).get("size_category", "medium")
	var mass_mult: float = PhysicsComposer.get_size_mass_multiplier(size_cat)

	apply_physics({
		"mass": mass_kg * mass_mult,
		"gravity": gravity_scale,
		"friction": friction_pct / 100.0,
		"bounce": bounce_pct / 100.0,
		"damping": damping,
	}, size_cat)


func apply_physics(physics: Dictionary, size_category: String) -> void:
	_body.mass = physics["mass"]
	_body.gravity_scale = physics["gravity"]
	_body.linear_damp = physics["damping"]

	var new_friction: float = physics["friction"]
	var new_bounce: float = physics["bounce"]
	if new_friction != _prev_friction or new_bounce != _prev_bounce:
		var mat := PhysicsMaterial.new()
		mat.friction = new_friction
		mat.bounce = new_bounce
		_body.physics_material_override = mat
		_prev_friction = new_friction
		_prev_bounce = new_bounce

	Log.debug("PhysicsApplicator: V3 physics for '%s' — size=%s, mass=%.1f, friction=%.2f, bounce=%.2f, gravity=%.1f, damp=%.1f" % [_body.blueprint.get("name", ""), size_category, _body.mass, physics["friction"], physics["bounce"], physics["gravity"], physics["damping"]])

	if not _has_sprite_shape:
		_configure_shape(size_category)


func update_shape_from_sprite(texture: Texture2D, world_size: float) -> void:
	var image: Image = texture.get_image()

	var used_rect: Rect2i = image.get_used_rect()
	if used_rect.size.x == 0 or used_rect.size.y == 0:
		return

	var tex_size: float = float(image.get_width())
	var world_scale: float = world_size / tex_size

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
