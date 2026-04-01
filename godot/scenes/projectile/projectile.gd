extends RigidBody2D

## Simple projectile spawned by SPAWN_PROJECTILE behavior action.
## Moves in a direction, deals damage on contact, auto-destroys after lifetime.
## Carries a payload tag that participates in the rule engine on collision.

const CL = preload("res://scripts/data/collision_layers.gd")

static var _texture_cache: Dictionary = {}  # color_hex -> ImageTexture

var tags: Array = []
var _damage: float = 20.0
var _source: Node = null  # The object that spawned this projectile
var _has_hit: bool = false


func _ready() -> void:
	collision_layer = CL.OBJECTS
	collision_mask = CL.OBJECTS | CL.TERRAIN | CL.PLAYER
	contact_monitor = true
	max_contacts_reported = 1
	body_entered.connect(_on_body_entered)
	gravity_scale = 0.0  # Projectiles fly straight

	# Lifetime timer
	var lifetime_timer := Timer.new()
	lifetime_timer.wait_time = BehaviorMaps.PROJECTILE_LIFETIME
	lifetime_timer.one_shot = true
	lifetime_timer.timeout.connect(_on_lifetime_expired)
	add_child(lifetime_timer)
	lifetime_timer.start()


func init_projectile(direction: Vector2, damage: float, payload_tag: String, source: Node) -> void:
	_damage = damage
	_source = source

	# Set up tags
	tags = BehaviorMaps.PROJECTILE_BASE_TAGS.duplicate()
	if not payload_tag.is_empty():
		tags.append(payload_tag)

	# Set velocity
	linear_velocity = direction * BehaviorMaps.PROJECTILE_SPEED

	# Create placeholder visual
	_create_visual(payload_tag)

	# Set up collision shape
	var shape := CollisionShape2D.new()
	var circle := CircleShape2D.new()
	circle.radius = 8.0
	shape.shape = circle
	add_child(shape)

	var source_name: String = _source.name if _source else "unknown"
	Log.debug("Projectile: Spawned from '%s' dir=(%.1f,%.1f) dmg=%.0f tag='%s'" % [source_name, direction.x, direction.y, damage, payload_tag])


func get_tags() -> Array:
	return tags


func get_object_id() -> String:
	return "projectile_%d" % get_instance_id()


func take_damage(_amount: float) -> void:
	queue_free()


func _on_body_entered(body: Node) -> void:
	if _has_hit:
		return
	if body == _source:
		return

	_has_hit = true

	# Deal damage
	WorldMutations.apply_damage(body, _damage)
	Log.debug("Projectile: Hit '%s' for %.0f damage" % [body.name, _damage])

	# Let rule engine handle tag interactions (e.g., HOT projectile ignites FLAMMABLE)
	if body.has_method("get_tags"):
		CollisionResolver.resolve_collision(self, body)

	queue_free()


func _create_visual(payload_tag: String) -> void:
	var color: Color = TagColors.get_color(payload_tag) if not payload_tag.is_empty() else Color(0.8, 0.8, 0.8)
	var key := color.to_html()
	if key not in _texture_cache:
		var image := Image.create(16, 16, false, Image.FORMAT_RGBA8)
		image.fill(color)
		_texture_cache[key] = ImageTexture.create_from_image(image)
	var sprite := Sprite2D.new()
	sprite.texture = _texture_cache[key]
	add_child(sprite)


func _on_lifetime_expired() -> void:
	Log.debug("Projectile: Expired without hitting anything")
	queue_free()
