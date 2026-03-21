extends Node

var _body: RigidBody2D
var _collision_shape: CollisionShape2D


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
	var size_category: String = visual_descriptor.get("size_category", "medium")
	var base_form: String = visual_descriptor.get("base_form", "box")
	_configure_shape(size_category, base_form)


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
