extends CharacterBody2D

const SPEED: float = 300.0
const JUMP_VELOCITY: float = -400.0
const GRAVITY: float = 980.0
const PUSH_FORCE: float = 500.0  # continuous force (N), not per-frame impulse
const KICK_FORCE: float = 400.0
const KICK_DAMAGE: float = 10.0
const KICK_RANGE: float = 48.0
const KICK_HEIGHT: float = 32.0
const KICK_COOLDOWN: float = 0.5
const VOID_THRESHOLD: float = 1200.0
const MAX_HEALTH: int = 100
const DAMAGE_FLASH_DURATION: float = 0.15
const MOVE_ACCEL: float = 3000.0  # px/s² — snappy controls, reach 300px/s in 0.1s
const EFFECTIVE_MASS: float = 0.4  # resistance to external forces — EXTREME (800) = 5x jump
const KNOCKBACK_DECAY: float = 800.0  # px/s² — 1000px/s knockback lasts ~1.2s
const KNOCKBACK_FULL_SUPPRESSION: float = 1000.0  # knockback magnitude for maximum control loss
const KNOCKBACK_MIN_CONTROL: float = 0.15  # minimum player authority during knockback (15%)
const BOUNCE_ENERGY: float = 1.2  # springs return 120% energy (they add energy!)
const BOUNCE_MIN_SPEED: float = 50.0  # ignore micro-bounces

enum State { IDLE, WALK, JUMP, FALL, KICK }

var _state: State = State.IDLE
var _input_direction: float = 0.0
var _facing: int = 1  # 1 = right, -1 = left
var _kick_cooldown_timer: float = 0.0
var _kick_query: PhysicsShapeQueryParameters2D
var current_health: int = MAX_HEALTH
var _damage_flash_timer: float = 0.0
var _dead: bool = false
var _knockback: Vector2 = Vector2.ZERO
var _speed_modifier: float = 1.0
var _slow_count: int = 0
var _pre_slide_velocity: Vector2 = Vector2.ZERO
var _prev_contacts: Dictionary = {}  # instance_id -> true
@onready var _anim_sprite: AnimatedSprite2D = $AnimatedSprite2D


var _categories: Array = ["CREATURE"]

func _ready() -> void:
	add_to_group("player")
	add_to_group("living")
	add_to_group("game_objects")

	var kick_shape := RectangleShape2D.new()
	kick_shape.size = Vector2(KICK_RANGE, KICK_HEIGHT)
	_kick_query = PhysicsShapeQueryParameters2D.new()
	_kick_query.shape = kick_shape
	_kick_query.collision_mask = CollisionLayers.OBJECTS
	_kick_query.collide_with_bodies = true

	_anim_sprite.animation_finished.connect(_on_animation_finished)
	Log.info("Player: Spawned with %d HP" % MAX_HEALTH)


func _physics_process(delta: float) -> void:
	_process_normal_movement(GRAVITY, SPEED, delta)
	_pre_slide_velocity = velocity
	move_and_slide()
	_decay_knockback(delta)
	if global_position.y > VOID_THRESHOLD and not _dead:
		_dead = true
		current_health = 0
		Log.info("Player: Fell into void at y=%.0f" % global_position.y)
		EventBus.player_damaged.emit(float(MAX_HEALTH), current_health, MAX_HEALTH)
		EventBus.player_died.emit()
		set_physics_process(false)
		_prev_contacts.clear()
		return
	_push_rigid_bodies()
	_process_kick(delta)
	_process_damage_flash(delta)
	_update_animation()


func _process_normal_movement(gravity: float, speed: float, delta: float) -> void:
	if not is_on_floor():
		velocity.y += gravity * delta

	if Input.is_action_just_pressed("jump") and is_on_floor():
		velocity.y = JUMP_VELOCITY

	_input_direction = Input.get_axis("move_left", "move_right")
	var target_vx: float = _input_direction * speed * _speed_modifier
	var control: float = clampf(1.0 - _knockback.length() / KNOCKBACK_FULL_SUPPRESSION, KNOCKBACK_MIN_CONTROL, 1.0)
	velocity.x = move_toward(velocity.x, target_vx, MOVE_ACCEL * control * delta)

	if _input_direction > 0.0:
		_facing = 1
	elif _input_direction < 0.0:
		_facing = -1


func _push_rigid_bodies() -> void:
	var current_contacts: Dictionary = {}
	for i in get_slide_collision_count():
		var collision := get_slide_collision(i)
		var collider := collision.get_collider()
		if collider is RigidBody2D:
			var cid: int = collider.get_instance_id()
			if cid in current_contacts:
				continue
			current_contacts[cid] = true
			# Push — continuous, every frame
			if collider.has_method("is_passively_pushable") and collider.is_passively_pushable():
				var push_dir := -collision.get_normal()
				collider.apply_central_force(push_dir * PUSH_FORCE)
			# Entry-only effects (first frame of new contact)
			if cid not in _prev_contacts:
				if collider.has_method("get_tags") and "BOUNCY" in collider.get_tags():
					var normal := collision.get_normal()
					var impact_speed: float = maxf(-_pre_slide_velocity.dot(normal), 0.0)
					if impact_speed > BOUNCE_MIN_SPEED:
						velocity = normal * impact_speed * BOUNCE_ENERGY
				CollisionResolver.resolve_and_notify(self, collider)
	_prev_contacts = current_contacts


func _process_kick(delta: float) -> void:
	if _kick_cooldown_timer > 0.0:
		_kick_cooldown_timer -= delta

	if Input.is_action_just_pressed("kick") and _kick_cooldown_timer <= 0.0:
		_perform_kick()
		_kick_cooldown_timer = KICK_COOLDOWN


func _perform_kick() -> void:
	_state = State.KICK
	_anim_sprite.play(&"kick")

	var space_state := get_world_2d().direct_space_state
	_kick_query.transform = Transform2D(0.0, global_position + Vector2(_facing * KICK_RANGE * 0.5, 0.0))

	var results := space_state.intersect_shape(_kick_query, 8)
	if results.is_empty():
		Log.debug("Player: Kick whiffed — nothing in range")
		return

	var kick_dir := Vector2(_facing, -0.3).normalized()
	for result in results:
		var collider = result["collider"]
		if collider is RigidBody2D:
			if not collider.has_method("is_heavy") or not collider.is_heavy():
				collider.apply_central_impulse(kick_dir * KICK_FORCE)
			WorldMutations.apply_damage(collider, KICK_DAMAGE)
			CollisionResolver.resolve_and_notify(self, collider)
			Log.debug("Player: Kicked '%s'" % collider.name)


func _on_animation_finished() -> void:
	if _state == State.KICK:
		_state = State.IDLE  # re-evaluate on next frame via _update_animation


func _update_animation() -> void:
	if _input_direction > 0.0:
		_anim_sprite.flip_h = false
	elif _input_direction < 0.0:
		_anim_sprite.flip_h = true

	# Let kick animation play through before resuming normal state
	if _state == State.KICK:
		return

	var new_state: State = _state
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


func take_damage(amount: float, _element_color: Color = Color.WHITE) -> void:
	if _dead:
		return
	current_health = max(0, current_health - int(amount))
	_damage_flash_timer = DAMAGE_FLASH_DURATION
	Log.debug("Player: Took %.0f damage, %d/%d HP remaining" % [amount, current_health, MAX_HEALTH])
	EventBus.player_damaged.emit(amount, current_health, MAX_HEALTH)
	if current_health <= 0:
		_dead = true
		Log.info("Player: Died from damage")
		EventBus.player_died.emit()
		set_physics_process(false)
		_prev_contacts.clear()


func heal(amount: float) -> void:
	current_health = min(current_health + int(amount), MAX_HEALTH)
	Log.debug("Player: Healed %.0f, %d/%d HP" % [amount, current_health, MAX_HEALTH])
	EventBus.player_healed.emit(amount, current_health, MAX_HEALTH)


func _process_damage_flash(delta: float) -> void:
	if _damage_flash_timer > 0.0:
		_damage_flash_timer -= delta
		var t: float = _damage_flash_timer / DAMAGE_FLASH_DURATION
		_anim_sprite.modulate = Color(1.0, 1.0 - 0.6 * t, 1.0 - 0.6 * t)
		if _damage_flash_timer <= 0.0:
			_anim_sprite.modulate = Color.WHITE


func apply_external_impulse(impulse: Vector2) -> void:
	if _dead:
		return
	var vel_change: Vector2 = impulse / EFFECTIVE_MASS
	velocity += vel_change
	_knockback += vel_change


func _decay_knockback(delta: float) -> void:
	_knockback = _knockback.move_toward(Vector2.ZERO, KNOCKBACK_DECAY * delta)
	if is_on_floor() and _knockback.y > 0.0:
		_knockback.y = 0.0


func apply_speed_modifier(factor: float) -> void:
	_slow_count += 1
	# Use the strongest slow (lowest factor) across all active sources
	_speed_modifier = minf(_speed_modifier, factor)


func clear_speed_modifier() -> void:
	_slow_count = maxi(0, _slow_count - 1)
	if _slow_count == 0:
		_speed_modifier = 1.0


func get_tags() -> Array:
	return ["LIVING"]


func get_categories() -> Array:
	return _categories


func get_effective_tags() -> Array:
	return ["LIVING"]
