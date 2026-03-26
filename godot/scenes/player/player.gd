extends CharacterBody2D

const SPEED: float = 300.0
const JUMP_VELOCITY: float = -400.0
const GRAVITY: float = 980.0
const PUSH_FORCE: float = 80.0
const KICK_FORCE: float = 400.0
const KICK_DAMAGE: float = 10.0
const KICK_RANGE: float = 48.0
const KICK_HEIGHT: float = 32.0
const KICK_COOLDOWN: float = 0.5
const VOID_THRESHOLD: float = 1200.0

enum State { IDLE, WALK, JUMP, FALL }

var _state: int = State.IDLE
var _input_direction: float = 0.0
var _facing: int = 1  # 1 = right, -1 = left
var _kick_cooldown_timer: float = 0.0
var _kick_query: PhysicsShapeQueryParameters2D

@onready var _anim_sprite: AnimatedSprite2D = $AnimatedSprite2D


func _ready() -> void:
	add_to_group("player")

	var kick_shape := RectangleShape2D.new()
	kick_shape.size = Vector2(KICK_RANGE, KICK_HEIGHT)
	_kick_query = PhysicsShapeQueryParameters2D.new()
	_kick_query.shape = kick_shape
	_kick_query.collision_mask = CollisionLayers.OBJECTS
	_kick_query.collide_with_bodies = true


func _physics_process(delta: float) -> void:
	_process_normal_movement(GRAVITY, SPEED, delta)
	move_and_slide()
	if global_position.y > VOID_THRESHOLD:
		EventBus.player_died.emit()
		set_physics_process(false)
		return
	_push_rigid_bodies()
	_process_kick(delta)
	_update_animation()


func _process_normal_movement(gravity: float, speed: float, delta: float) -> void:
	if not is_on_floor():
		velocity.y += gravity * delta

	if Input.is_action_just_pressed("jump") and is_on_floor():
		velocity.y = JUMP_VELOCITY

	_input_direction = Input.get_axis("move_left", "move_right")
	if _input_direction:
		velocity.x = _input_direction * speed
	else:
		velocity.x = move_toward(velocity.x, 0, speed)

	if _input_direction > 0.0:
		_facing = 1
	elif _input_direction < 0.0:
		_facing = -1


func _push_rigid_bodies() -> void:
	for i in get_slide_collision_count():
		var collision := get_slide_collision(i)
		var collider := collision.get_collider()
		if collider is RigidBody2D:
			var push_dir := -collision.get_normal()
			collider.apply_central_impulse(push_dir * PUSH_FORCE)


func _process_kick(delta: float) -> void:
	if _kick_cooldown_timer > 0.0:
		_kick_cooldown_timer -= delta

	if Input.is_action_just_pressed("kick") and _kick_cooldown_timer <= 0.0:
		_perform_kick()
		_kick_cooldown_timer = KICK_COOLDOWN


func _perform_kick() -> void:
	var space_state := get_world_2d().direct_space_state
	_kick_query.transform = Transform2D(0.0, global_position + Vector2(_facing * KICK_RANGE * 0.5, 0.0))

	var results := space_state.intersect_shape(_kick_query, 8)
	if results.is_empty():
		return

	var kick_dir := Vector2(_facing, -0.3).normalized()
	for result in results:
		var collider = result["collider"]
		if collider is RigidBody2D:
			collider.apply_central_impulse(kick_dir * KICK_FORCE)
			WorldMutations.apply_damage(collider, KICK_DAMAGE)
			Log.debug("Player: Kicked '%s'" % collider.name)


func _update_animation() -> void:
	if _input_direction > 0.0:
		_anim_sprite.flip_h = false
	elif _input_direction < 0.0:
		_anim_sprite.flip_h = true

	var new_state: int = _state
	if not is_on_floor():
		if velocity.y < 0.0:
			new_state = State.JUMP
		else:
			new_state = State.FALL
	elif abs(velocity.x) > 1.0:
		new_state = State.WALK
	else:
		new_state = State.IDLE

	if new_state != _state:
		_state = new_state
		match _state:
			State.IDLE:
				_anim_sprite.play("idle")
			State.WALK:
				_anim_sprite.play("walk")
			State.JUMP:
				_anim_sprite.play("jump")
			State.FALL:
				_anim_sprite.play("fall")


func get_effective_tags() -> Array:
	return ["LIVING"]
