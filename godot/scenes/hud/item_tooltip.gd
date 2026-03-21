extends PanelContainer

@onready var name_label: Label = %NameLabel
@onready var tags_container: HFlowContainer = %TagsContainer
@onready var equip_section: VBoxContainer = %EquipSection
@onready var equip_tags_container: HFlowContainer = %EquipTagsContainer
@onready var durability_bar: ProgressBar = %DurabilityBar
@onready var cost_label: Label = %CostLabel


func _ready() -> void:
	visible = false
	var style := _make_stylebox(Color(0.12, 0.12, 0.15, 0.95), 6, 10, 8, 1, Color(0.4, 0.4, 0.4, 0.8))
	add_theme_stylebox_override("panel", style)


func show_for_item(blueprint: Dictionary, global_pos: Vector2) -> void:
	if blueprint.is_empty():
		visible = false
		return

	name_label.text = blueprint.get("name", "Unknown")

	# Clear and populate tags
	_clear_children(tags_container)
	var tags: Array = blueprint.get("tags", [])
	for tag in tags:
		var badge := _create_tag_badge(str(tag))
		tags_container.add_child(badge)

	# Equip section
	var is_equippable: bool = blueprint.get("is_equippable", false)
	equip_section.visible = is_equippable
	if is_equippable:
		_clear_children(equip_tags_container)
		var equip_tags: Array = blueprint.get("equip_tags", [])
		for tag in equip_tags:
			var badge := _create_tag_badge(str(tag))
			equip_tags_container.add_child(badge)

	# Durability
	var max_durability: float = blueprint.get("starting_durability", 150)
	var current_durability: float = blueprint.get("current_durability", max_durability)
	durability_bar.max_value = max_durability
	durability_bar.value = current_durability

	# Power cost
	var power_cost: int = blueprint.get("power_cost", 0)
	cost_label.text = "Cost: %d/10" % power_cost

	global_position = global_pos
	visible = true


func hide_tooltip() -> void:
	visible = false


func _create_tag_badge(tag: String) -> Label:
	var badge := Label.new()
	badge.text = " %s " % tag
	badge.add_theme_font_size_override("font_size", 11)

	var color: Color = TagColors.get_color(tag)
	badge.add_theme_color_override("font_color", color)

	var bg := _make_stylebox(Color(color, 0.15), 3, 4, 1)
	badge.add_theme_stylebox_override("normal", bg)

	return badge


func _clear_children(node: Node) -> void:
	for child in node.get_children():
		child.queue_free()


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
