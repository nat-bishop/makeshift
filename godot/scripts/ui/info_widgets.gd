class_name InfoWidgets


static func create_tag_badge(tag: String, font_size: int = 12) -> Label:
	var badge := Label.new()
	badge.text = " %s " % tag
	badge.add_theme_font_size_override("font_size", font_size)
	var color: Color = StateColors.get_color(tag)
	badge.add_theme_color_override("font_color", color)
	badge.add_theme_stylebox_override("normal", make_stylebox(Color(color, 0.15), 3, 4, 1))
	badge.mouse_filter = Control.MOUSE_FILTER_STOP
	badge.tooltip_text = tag
	return badge


static func create_behavior_label(behavior: Dictionary, font_size: int = 12) -> Label:
	var label := Label.new()
	var is_implied: bool = behavior.get("implied", false)
	var prefix: String = "[implied] " if is_implied else "[signature] "
	var verb: String = behavior.get("verb", "")
	var target: String = behavior.get("target_description", "")
	label.text = prefix + verb + (" " + target if not target.is_empty() else "")
	label.add_theme_font_size_override("font_size", font_size)
	var color := Color(0.55, 0.55, 0.6) if is_implied else Color(0.85, 0.85, 0.5)
	label.add_theme_color_override("font_color", color)
	return label


static func make_stylebox(
	bg_color: Color,
	corner_radius: int,
	content_margin_h: float,
	content_margin_v: float,
	border_width: int = 0,
	border_color: Color = Color.TRANSPARENT,
) -> StyleBoxFlat:
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
