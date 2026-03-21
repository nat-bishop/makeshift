extends PanelContainer

@onready var description_input: LineEdit = %DescriptionInput
@onready var create_button: Button = %CreateButton
@onready var status_label: Label = %StatusLabel

var _is_creating := false


func _ready() -> void:
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.12, 0.12, 0.15, 0.95)
	style.corner_radius_top_left = 8
	style.corner_radius_top_right = 8
	style.corner_radius_bottom_left = 8
	style.corner_radius_bottom_right = 8
	style.border_width_left = 1
	style.border_width_right = 1
	style.border_width_top = 1
	style.border_width_bottom = 1
	style.border_color = Color(0.4, 0.4, 0.5, 0.8)
	style.content_margin_left = 16
	style.content_margin_right = 16
	style.content_margin_top = 12
	style.content_margin_bottom = 12
	add_theme_stylebox_override("panel", style)

	create_button.pressed.connect(_on_create_pressed)
	description_input.text_submitted.connect(_on_text_submitted)
	status_label.text = ""


func focus_input() -> void:
	description_input.grab_focus()


func _on_create_pressed() -> void:
	_submit()


func _on_text_submitted(_text: String) -> void:
	_submit()


func _submit() -> void:
	if _is_creating:
		return

	var description := description_input.text.strip_edges()
	if description.is_empty():
		status_label.text = "Enter a description first."
		status_label.add_theme_color_override("font_color", Color(1.0, 0.6, 0.3))
		return

	_is_creating = true
	create_button.disabled = true
	status_label.text = "Creating..."
	status_label.add_theme_color_override("font_color", Color(0.7, 0.7, 0.7))

	var result: Dictionary = await Backend.create_object(description)

	_is_creating = false
	create_button.disabled = false

	if result.is_empty():
		status_label.text = "Creation failed. Try again."
		status_label.add_theme_color_override("font_color", Color(1.0, 0.3, 0.3))
	else:
		status_label.text = ""
		description_input.text = ""
		EventBus.object_created.emit(result)
		visible = false
