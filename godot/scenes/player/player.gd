extends CharacterBody2D

const SPEED: float = 300.0
const JUMP_VELOCITY: float = -400.0
const GRAVITY: float = 980.0

enum State { IDLE, WALK, JUMP, FALL }

var _state: int = State.IDLE
var _input_direction: float = 0.0

@onready var _anim_sprite: AnimatedSprite2D = $AnimatedSprite2D


func _ready() -> void:
	add_to_group("player")


func _physics_process(delta: float) -> void:
	_process_normal_movement(GRAVITY, SPEED, delta)
	move_and_slide()
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
