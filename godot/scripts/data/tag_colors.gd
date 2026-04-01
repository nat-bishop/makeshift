class_name TagColors

const COLORS: Dictionary = {
	"HEAT_SOURCE": Color("#FF4444"),
	"HOT": Color("#FF4444"),
	"FLAMMABLE": Color("#FF4444"),
	"FROZEN": Color("#4488FF"),
	"COLD": Color("#4488FF"),
	"ELECTRIC": Color("#FFDD44"),
	"METALLIC": Color("#FFDD44"),
	"LIVING": Color("#44FF44"),
	"EXPLOSIVE": Color("#FF8844"),
	"ACIDIC": Color("#AA44FF"),
	"TOXIC": Color("#AA44FF"),
	"MAGNETIC": Color("#448888"),
	"FLYING": Color("#88DDFF"),
	"GLOWING": Color("#FFD700"),
	"WET": Color("#4499DD"),
	"BRITTLE": Color("#AADDFF"),
	"CORRODED": Color("#887744"),
}
const DEFAULT: Color = Color("#AAAAAA")
const HEAL: Color = Color("#44FF88")

static func get_color(tag: String) -> Color:
	return COLORS.get(tag, DEFAULT)


static func get_body_tags(body: Node) -> Array:
	if body.has_method("get_effective_tags"):
		return body.get_effective_tags()
	if body.has_method("get_tags"):
		return body.get_tags()
	return []


static func derive_element_color(body: Node, fallback: Color = Color.WHITE) -> Color:
	for tag in get_body_tags(body):
		if tag in COLORS:
			return COLORS[tag]
	return fallback


static func is_taggable(body: Node) -> bool:
	return body.has_method("get_tags") or body.has_method("get_effective_tags")
