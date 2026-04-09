extends Node

## V3 Physics Applicator: reads LLM-generated physics directly from blueprint.
## No substance profiles, no tag modifiers. Physics are fixed at creation time.

var _body: RigidBody2D
var _collision_shape: CollisionShape2D
var _has_sprite_shape: bool = false


func _ready() -> void:
	_body = get_parent()
	_collision_shape = _body.get_node("CollisionShape2D")


func apply_from_blueprint(bp: Dictionary) -> void:
	var phys: Dictionary = bp.get("physics", {})
	var mass_kg: float = phys.get("mass_kg", 1.0)
	var height_cm: int = phys.get("height_cm", 30)
	var surface: int = phys.get("surface", 1)
	var bounce_100: int = phys.get("bounce", 10)
	var gravity_100: int = phys.get("gravity", 50)

	var scale: float = PhysicsComposer.scale_from_height(height_cm)
	var size_cat: String = PhysicsComposer.size_from_height(height_cm)

	# Mass (real-world kg * continuous scale)
	_body.mass = mass_kg * scale

	# Gravity: piecewise linear mapping
	#   0-50 -> -1.0 to 1.0 (floating up to normal)
	#   50-100 -> 1.0 to 2.0 (normal to extra heavy)
	_body.gravity_scale = _gravity_to_scale(gravity_100)

	# Damping: derived from height and mass
	_body.linear_damp = clampf(float(height_cm) / (mass_kg * 100.0 + 10.0), 0.0, 10.0)

	# Physics material
	var mat := PhysicsMaterial.new()
	var friction_val: float = PhysicsComposer.SURFACE_FRICTION.get(surface, 0.5)
	mat.friction = friction_val
	mat.bounce = bounce_100 / 100.0
	_body.physics_material_override = mat

	# Fallback collision shape from continuous scale
	if not _has_sprite_shape:
		_configure_shape(height_cm)

	Log.debug("PhysicsApplicator: '%s' mass=%.2f gravity=%.2f friction=%.2f bounce=%.2f damp=%.2f size=%s scale=%.2f" % [
		bp.get("name", "?"), _body.mass, _body.gravity_scale,
		mat.friction, mat.bounce, _body.linear_damp, size_cat, scale
	])


func _gravity_to_scale(g: int) -> float:
	if g <= 50:
		return lerpf(-1.0, 1.0, float(g) / 50.0)
	return lerpf(1.0, 2.0, float(g - 50) / 50.0)


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


func _configure_shape(height_cm: int) -> void:
	var collision_size: float = PhysicsComposer.world_collision_size(height_cm)
	var rect := RectangleShape2D.new()
	rect.size = Vector2(collision_size, collision_size)
	_collision_shape.shape = rect
