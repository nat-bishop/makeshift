extends PanelContainer

@onready var description_input: LineEdit = %DescriptionInput
@onready var create_button: Button = %CreateButton
@onready var status_label: Label = %StatusLabel
@onready var _creation_form: VBoxContainer = %CreationForm
@onready var _reveal_card: VBoxContainer = %RevealCard
@onready var _reveal_name: Label = %RevealName
@onready var _reveal_tags: HFlowContainer = %RevealTags
@onready var _reveal_size: Label = %RevealSize
@onready var _reveal_cost: Label = %RevealCost

var _is_creating := false
var _is_showing_reveal := false


func _ready() -> void:
	var style := _make_stylebox(
		Color(0.12, 0.12, 0.15, 0.95), 8, 16, 12, 1, Color(0.4, 0.4, 0.5, 0.8)
	)
	add_theme_stylebox_override("panel", style)

	description_input.max_length = 500
	create_button.pressed.connect(_on_create_pressed)
	description_input.text_submitted.connect(_on_text_submitted)
	status_label.text = ""
	_reveal_card.visible = false


func focus_input() -> void:
	description_input.grab_focus()


func _unhandled_input(event: InputEvent) -> void:
	if _is_showing_reveal and event.is_pressed():
		_dismiss_reveal()
		get_viewport().set_input_as_handled()


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

	Log.info("CreationPanel: Creating object from '%s'" % description)
	_is_creating = true
	create_button.disabled = true
	status_label.text = "Creating..."
	status_label.add_theme_color_override("font_color", Color(0.7, 0.7, 0.7))
	EventBus.creation_requested.emit()

	var result: Dictionary = await Backend.create_object(description)

	_is_creating = false
	create_button.disabled = false

	if result.get("error", false):
		var error_msg: String = result.get("message", "Creation failed. Try again.")
		Log.warn("CreationPanel: Creation failed: %s" % error_msg)
		status_label.text = error_msg
		status_label.add_theme_color_override("font_color", Color(1.0, 0.3, 0.3))
		EventBus.creation_failed.emit()
	else:
		status_label.text = ""
		description_input.text = ""
		var blueprint: Dictionary = result.get("blueprint", result)
		Log.info("CreationPanel: Created '%s'" % blueprint.get("name", "?"))
		_show_reveal(blueprint)


func _show_reveal(blueprint: Dictionary) -> void:
	_is_showing_reveal = true
	_creation_form.visible = false
	_reveal_card.visible = true

	_reveal_name.text = blueprint.get("name", "Unknown")

	for child in _reveal_tags.get_children():
		child.queue_free()
	var tags: Array = blueprint.get("tags", [])
	for tag in tags:
		var badge := _create_tag_badge(str(tag))
		_reveal_tags.add_child(badge)

	var vd: Dictionary = blueprint.get("visual_descriptor", {})
	_reveal_size.text = vd.get("size_category", "medium").to_upper()

	var power_cost: int = blueprint.get("power_cost", 0)
	_reveal_cost.text = "%d / 10" % power_cost

	_reveal_card.modulate.a = 0.0
	var tween := create_tween()
	tween.tween_property(_reveal_card, "modulate:a", 1.0, 0.25)


func _dismiss_reveal() -> void:
	_is_showing_reveal = false
	_reveal_card.visible = false
	_creation_form.visible = true
	visible = false


func _create_tag_badge(tag: String) -> Label:
	var badge := Label.new()
	badge.text = " %s " % tag
	badge.add_theme_font_size_override("font_size", 12)
	var color: Color = TagColors.get_color(tag)
	badge.add_theme_color_override("font_color", color)
	badge.add_theme_stylebox_override("normal", _make_stylebox(Color(color, 0.15), 3, 4, 1))
	return badge


static func _make_stylebox(bg_color: Color, corner_radius: int, content_margin_h: float, content_margin_v: float, border_width: int = 0, border_color: Color = Color.TRANSPARENT) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = bg_color
	style.corner_radius_top_left = corner_radius
	style.corner_radius_top_right = corner_radius
	style.corner_radius_bottom_left = corner_radius
	style.corner_radius_bottom_right = corner_radius
	style.content_margin_left = content_margin_h
	style.content_margin_right = content_margin_h
	style.content_margin_top = content_margin_v
	style.content_margin_bottom = content_margin_v
	if border_width > 0:
		style.border_width_left = border_width
		style.border_width_right = border_width
		style.border_width_top = border_width
		style.border_width_bottom = border_width
		style.border_color = border_color
	return style
