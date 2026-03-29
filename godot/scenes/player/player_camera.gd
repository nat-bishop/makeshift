extends Camera2D

@export var look_ahead_factor: float = 0.2
@export var look_ahead_max: float = 100.0
@export var smooth_speed: float = 5.0

var _base_offset: Vector2
var _viewport: Viewport


func _ready() -> void:
	_base_offset = offset
	_viewport = get_viewport()


func _process(delta: float) -> void:
	var viewport_size := _viewport.get_visible_rect().size
	var mouse_screen := _viewport.get_mouse_position()
	var screen_center := viewport_size * 0.5
	var displacement := (mouse_screen - screen_center) / zoom

	var target_offset := displacement * look_ahead_factor
	target_offset = target_offset.limit_length(look_ahead_max)

	offset = offset.lerp(_base_offset + target_offset, 1.0 - exp(-smooth_speed * delta))
