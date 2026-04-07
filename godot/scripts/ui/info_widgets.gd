class_name InfoWidgets


static func create_state_badge(state: String, font_size: int = 12) -> Label:
	var badge := Label.new()
	badge.text = " %s " % state
	badge.add_theme_font_size_override("font_size", font_size)
	var color: Color = StateVisuals.COLORS.get(state, Color(0.6, 0.6, 0.6))
	badge.add_theme_color_override("font_color", color)
	badge.add_theme_stylebox_override("normal", make_stylebox(Color(color, 0.15), 3, 4, 1))
	return badge


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
