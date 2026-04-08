class_name PostProcess
extends CanvasLayer

## Post-processing shader manager. Cycles through available shaders with a key toggle.

const SHADERS: Array[String] = [
	"",  # index 0 = no post-processing
	"res://shaders/post/palette_limit.gdshader",
	"res://shaders/post/dither.gdshader",
	"res://shaders/post/sobel_outline.gdshader",
	"res://shaders/post/crosshatch.gdshader",
	"res://shaders/post/pencil.gdshader",
]

var _current_index: int = 0
var _color_rect: ColorRect


func _ready() -> void:
	layer = 100
	_color_rect = ColorRect.new()
	_color_rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	_color_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_color_rect.visible = false
	add_child(_color_rect)


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("toggle_post_process"):
		cycle_shader()


func cycle_shader() -> void:
	_current_index = (_current_index + 1) % SHADERS.size()
	if _current_index == 0:
		_color_rect.visible = false
		_color_rect.material = null
		Log.info("PostProcess: disabled")
	else:
		var shader: Shader = load(SHADERS[_current_index]) as Shader
		var mat := ShaderMaterial.new()
		mat.shader = shader
		_color_rect.material = mat
		_color_rect.visible = true
		var shader_name: String = SHADERS[_current_index].get_file().get_basename()
		Log.info("PostProcess: %s" % shader_name)
