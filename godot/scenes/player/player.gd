extends CharacterBody2D

const SPEED: float = 300.0
const JUMP_VELOCITY: float = -400.0
const GRAVITY: float = 980.0

var is_climbing: bool = false

@onready var player_equipment: Node = $PlayerEquipment
@onready var player_inventory: Node = $PlayerInventory
@onready var player_interaction: Node = $PlayerInteraction


func _physics_process(delta: float) -> void:
	var effective_gravity: float = GRAVITY
	var effective_speed: float = SPEED

	# Equipment modifiers
	if player_equipment.has_tag("FLOATING"):
		effective_gravity *= -0.3
	if player_equipment.has_tag("HEAVY"):
		effective_speed *= 0.7

	# Climbing
	if is_climbing:
		_process_climbing(effective_speed, delta)
	else:
		_process_normal_movement(effective_gravity, effective_speed, delta)

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


func _process_climbing(_speed: float, _delta: float) -> void:
	var vertical: float = 0.0
	if Input.is_action_pressed("jump"):
		vertical = -1.0
	elif Input.is_action_pressed("move_left") or Input.is_action_pressed("move_right"):
		pass

	var horizontal: float = Input.get_axis("move_left", "move_right")
	velocity.x = horizontal * _speed * 0.5
	velocity.y = vertical * _speed * 0.5

	if Input.is_action_just_pressed("jump") and horizontal != 0.0:
		is_climbing = false
		velocity.y = JUMP_VELOCITY * 0.7


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("pickup"):
		player_interaction.pickup_nearest()
	elif event.is_action_pressed("drop"):
		player_interaction.drop_item()
	elif event.is_action_pressed("equip"):
		player_interaction.equip_item()

	# Hotbar selection
	for i in range(8):
		var action_name: String = "hotbar_%d" % (i + 1)
		if event.is_action_pressed(action_name):
			player_inventory.select_slot(i)
			break


func enter_climb() -> void:
	is_climbing = true
	velocity.y = 0.0


func exit_climb() -> void:
	is_climbing = false


func get_effective_tags() -> Array:
	return player_equipment.get_effective_tags()
