extends CanvasLayer

const SHADERS: Array[Dictionary] = [
	{"name": "palette_limit", "path": "res://shaders/post/palette_limit.gdshader"},
	{"name": "dither", "path": "res://shaders/post/dither.gdshader"},
	{"name": "sobel_outline", "path": "res://shaders/post/sobel_outline.gdshader"},
	{"name": "crosshatch", "path": "res://shaders/post/crosshatch.gdshader"},
	{"name": "pencil", "path": "res://shaders/post/pencil.gdshader"},
]

var _effect_rect: ColorRect
var _current_index: int = -1
var _materials: Array = []
var _enabled: bool = false


func _ready() -> void:
	layer = 5
	visible = false

	_effect_rect = ColorRect.new()
	_effect_rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	_effect_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_effect_rect)

	for entry in SHADERS:
		var mat := ShaderMaterial.new()
		mat.shader = load(entry["path"])
		_materials.append(mat)


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("toggle_post_process"):
		_enabled = !_enabled
		if _enabled and _current_index < 0:
			_current_index = 0
		_apply_shader()
		get_viewport().set_input_as_handled()

	if event.is_action_pressed("cycle_post_process"):
		if _materials.is_empty():
			return
		_current_index = (_current_index + 1) % _materials.size()
		_enabled = true
		_apply_shader()
		get_viewport().set_input_as_handled()


func _apply_shader() -> void:
	if not _enabled or _current_index < 0:
		visible = false
		Log.info("PostProcess: OFF")
		EventBus.post_process_changed.emit("OFF")
		return

	_effect_rect.material = _materials[_current_index]
	visible = true
	var name_str: String = SHADERS[_current_index]["name"]
	Log.info("PostProcess: %s" % name_str)
	EventBus.post_process_changed.emit(name_str)


func get_current_shader_name() -> String:
	if not _enabled or _current_index < 0:
		return "OFF"
	return SHADERS[_current_index]["name"]
