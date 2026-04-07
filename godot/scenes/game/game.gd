extends Node2D

const MaterializeEffect: GDScript = preload("res://scenes/effects/materialize_effect.gd")
const SPAWN_OFFSET: Vector2 = Vector2(80, -32)

@onready var world: Node2D = $World
@onready var hud: CanvasLayer = $HUD
@onready var player: CharacterBody2D = $Player

var _current_level_scene: Node2D = null
var _materialize_effect: Node2D = null
var _pending_blueprint: Dictionary = {}
var _placement_active: bool = false
var _placement_ghost: Node2D = null


func _ready() -> void:
	set_process(false)
	EventBus.level_completed.connect(_on_level_completed)
	EventBus.object_created.connect(_on_object_created)
	EventBus.creation_requested.connect(_on_creation_requested)
	EventBus.creation_failed.connect(_on_creation_failed)
	EventBus.sprite_ready.connect(_on_sprite_ready)
	EventBus.sprite_failed.connect(_on_sprite_failed)
	_load_current_level()


func _process(_delta: float) -> void:
	var mouse_pos := get_global_mouse_position()
	if _materialize_effect and is_instance_valid(_materialize_effect):
		_materialize_effect.global_position = mouse_pos
	if _placement_active and is_instance_valid(_placement_ghost):
		_placement_ghost.global_position = mouse_pos


func _unhandled_input(event: InputEvent) -> void:
	if not _placement_active:
		return

	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		_confirm_placement()
		get_viewport().set_input_as_handled()
	elif event.is_action_pressed("ui_cancel"):
		_cancel_placement()
		get_viewport().set_input_as_handled()


func _get_pending_id() -> String:
	return _pending_blueprint.get("id", "")


func _load_current_level() -> void:
	var level_index: int = GameManager.current_level
	if level_index >= GameManager.LEVELS.size():
		return

	var level_path: String = GameManager.LEVELS[level_index]["scene"]
	var level_scene: PackedScene = load(level_path)
	if level_scene == null:
		Log.error("Game: Failed to load level: %s" % level_path)
		return

	_current_level_scene = level_scene.instantiate()
	world.add_child(_current_level_scene)
	world.move_child(_current_level_scene, 0)  # Behind objects
	Log.info("Game: Loaded level %d (%s)" % [level_index, level_path])

	# Position player at spawn point
	var spawn_point: Marker2D = _current_level_scene.find_child("SpawnPoint", true, false)
	if spawn_point:
		player.global_position = spawn_point.global_position
	else:
		player.global_position = Vector2(128, 0)

	# Set objective text in HUD
	if _current_level_scene.has_method("get_objective_text"):
		hud.set_objective(_current_level_scene.get_objective_text())


func _on_level_completed(_level_id: int) -> void:
	# GameManager handles level progression via its own listener
	pass


func _on_creation_requested() -> void:
	_clear_pending()
	var spawn_pos: Vector2 = get_global_mouse_position()
	var effect := Node2D.new()
	effect.set_script(MaterializeEffect)
	effect.global_position = spawn_pos
	world.add_child(effect)
	_materialize_effect = effect
	set_process(true)
	Log.debug("Game: Materialization effect started at %s" % str(spawn_pos))


func _on_object_created(blueprint: Dictionary) -> void:
	_pending_blueprint = blueprint
	var pending_id: String = _get_pending_id()

	# Sprite may already be cached (arrived via WebSocket before HTTP response)
	if pending_id != "" and Backend.get_cached_sprite(pending_id) != null:
		_begin_placement()
	else:
		Log.debug("Game: Waiting for sprite for '%s'" % blueprint.get("name", "?"))


func _on_sprite_ready(id: String, _texture: Texture2D) -> void:
	if id != _get_pending_id() or _get_pending_id() == "":
		return

	if _placement_active and is_instance_valid(_placement_ghost):
		var sprite: Sprite2D = _placement_ghost.get_node("Sprite2D")
		sprite.texture = _texture
		var vd: Dictionary = _pending_blueprint.get("visual_descriptor", {})
		var world_size: float = PhysicsComposer.get_size_data(vd.get("size_category", "medium"))["sprite"]
		sprite.scale = Vector2.ONE * (world_size / _texture.get_width())
	else:
		_begin_placement()


func _on_sprite_failed(id: String) -> void:
	if id == _get_pending_id():
		Log.warn("Game: Sprite failed for '%s', placing with placeholder" % _pending_blueprint.get("name", "?"))
		_begin_placement()


func _on_creation_failed() -> void:
	if _materialize_effect and is_instance_valid(_materialize_effect):
		_materialize_effect.resolve(true)
		_materialize_effect = null
		Log.debug("Game: Materialization effect cancelled (creation failed)")
	_pending_blueprint = {}
	set_process(false)


func _begin_placement() -> void:
	var ghost_start_pos: Vector2 = player.global_position + SPAWN_OFFSET
	if _materialize_effect and is_instance_valid(_materialize_effect):
		ghost_start_pos = _materialize_effect.global_position
		_materialize_effect.resolve()
		_materialize_effect = null

	_placement_ghost = _create_placement_ghost()
	_placement_ghost.global_position = ghost_start_pos
	world.add_child(_placement_ghost)
	_placement_active = true
	set_process(true)
	EventBus.placement_started.emit()
	Log.debug("Game: Placement mode started for '%s'" % _pending_blueprint.get("name", "?"))


func _create_placement_ghost() -> Node2D:
	var ghost := Node2D.new()
	var sprite := Sprite2D.new()
	sprite.name = "Sprite2D"
	ghost.add_child(sprite)

	var pending_id: String = _get_pending_id()
	var cached: Texture2D = Backend.get_cached_sprite(pending_id) if pending_id != "" else null
	if cached:
		sprite.texture = cached
		var vd: Dictionary = _pending_blueprint.get("visual_descriptor", {})
		var world_size: float = PhysicsComposer.get_size_data(vd.get("size_category", "medium"))["sprite"]
		sprite.scale = Vector2.ONE * (world_size / cached.get_width())
	else:
		var phys: Dictionary = _pending_blueprint.get("physics", {})
		var height_cm: int = phys.get("height_cm", 30)
		var size_category: String = PhysicsComposer.size_from_height(height_cm)
		var size_data: Dictionary = PhysicsComposer.get_size_data(size_category)
		var sprite_size: int = size_data["sprite"]
		var color := Color(0.6, 0.7, 0.8, 0.8)  # Neutral placeholder
		var image := Image.create(sprite_size, sprite_size, false, Image.FORMAT_RGBA8)
		image.fill(color)
		sprite.texture = ImageTexture.create_from_image(image)

	ghost.modulate = Color(0.7, 0.9, 1.0, 0.5)
	return ghost


func _confirm_placement() -> void:
	var final_pos: Vector2 = _placement_ghost.global_position
	var blueprint: Dictionary = _pending_blueprint

	_end_placement()

	Log.info("Game: Placed '%s' at (%.0f, %.0f)" % [blueprint.get("name", "?"), final_pos.x, final_pos.y])
	world.spawn_object(blueprint, final_pos)


func _cancel_placement() -> void:
	_end_placement()
	Log.debug("Game: Placement cancelled")


func _end_placement() -> void:
	if is_instance_valid(_placement_ghost):
		_placement_ghost.queue_free()
		_placement_ghost = null
	_placement_active = false
	set_process(false)
	_pending_blueprint = {}
	EventBus.placement_ended.emit()


func _clear_pending() -> void:
	if _placement_active:
		_end_placement()
	if _materialize_effect and is_instance_valid(_materialize_effect):
		_materialize_effect.queue_free()
		_materialize_effect = null
	_pending_blueprint = {}
	if not _placement_active:
		set_process(false)
