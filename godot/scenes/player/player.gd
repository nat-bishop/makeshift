extends CharacterBody2D

const SPEED: float = 300.0
const JUMP_VELOCITY: float = -400.0
const GRAVITY: float = 980.0


func _ready() -> void:
	add_to_group("player")


func _physics_process(delta: float) -> void:
	_process_normal_movement(GRAVITY, SPEED, delta)
	move_and_slide()


func _process_normal_movement(gravity: float, speed: float, delta: float) -> void:
	if not is_on_floor():
		velocity.y += gravity * delta

	if Input.is_action_just_pressed("jump") and is_on_floor():
		velocity.y = JUMP_VELOCITY

	var direction: float = Input.get_axis("move_left", "move_right")
	if direction:
		velocity.x = direction * speed
	else:
		velocity.x = move_toward(velocity.x, 0, speed)


func get_effective_tags() -> Array:
	return ["LIVING"]
