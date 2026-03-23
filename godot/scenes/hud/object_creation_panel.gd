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
@onready var _reveal_equip: Label = %RevealEquip

var _is_creating := false
var _is_showing_reveal := false


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
	_reveal_card.visible = false


func focus_input() -> void:
	description_input.grab_focus()


func _unhandled_input(event: InputEvent) -> void:
	if _is_showing_reveal and event is InputEventKey and event.pressed:
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

	_is_creating = true
	create_button.disabled = true
	status_label.text = "Creating..."
	status_label.add_theme_color_override("font_color", Color(0.7, 0.7, 0.7))

	var result: Dictionary = await Backend.create_object(description)

	_is_creating = false
	create_button.disabled = false

	if result.get("error", false):
		var error_msg: String = result.get("message", "Creation failed. Try again.")
		status_label.text = error_msg
		status_label.add_theme_color_override("font_color", Color(1.0, 0.3, 0.3))
	else:
		status_label.text = ""
		description_input.text = ""
		var blueprint: Dictionary = result.get("blueprint", result)
		_show_reveal(blueprint)


func _show_reveal(blueprint: Dictionary) -> void:
	_is_showing_reveal = true
	_creation_form.visible = false
	_reveal_card.visible = true

	# Name
	_reveal_name.text = blueprint.get("name", "Unknown")

	# Tags
	_clear_children(_reveal_tags)
	var tags: Array = blueprint.get("tags", [])
	for tag in tags:
		var badge := _create_tag_badge(str(tag))
		_reveal_tags.add_child(badge)

	# Size
	var vd: Dictionary = blueprint.get("visual_descriptor", {})
	var size_cat: String = vd.get("size_category", "medium")
	_reveal_size.text = size_cat.to_upper()

	# Cost
	var power_cost: int = blueprint.get("power_cost", 0)
	_reveal_cost.text = "%d / 10" % power_cost

	# Equip info
	var is_equippable: bool = blueprint.get("is_equippable", false)
	if is_equippable:
		var slot: String = blueprint.get("equip_slot", "")
		_reveal_equip.text = "Equip: %s" % slot
		_reveal_equip.visible = true
	else:
		_reveal_equip.visible = false

	# Animate in
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

	var bg := StyleBoxFlat.new()
	bg.bg_color = Color(color, 0.15)
	bg.corner_radius_top_left = 3
	bg.corner_radius_top_right = 3
	bg.corner_radius_bottom_left = 3
	bg.corner_radius_bottom_right = 3
	bg.content_margin_left = 4
	bg.content_margin_right = 4
	bg.content_margin_top = 1
	bg.content_margin_bottom = 1
	badge.add_theme_stylebox_override("normal", bg)

	return badge


func _clear_children(node: Node) -> void:
	for child in node.get_children():
		child.queue_free()
