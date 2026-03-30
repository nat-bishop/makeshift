class_name TagColors

const COLORS: Dictionary = {
	"HEAT_SOURCE": Color("#FF4444"),
	"HOT": Color("#FF4444"),
	"FLAMMABLE": Color("#FF4444"),
	"FROZEN": Color("#4488FF"),
	"COLD": Color("#4488FF"),
	"ELECTRIC": Color("#FFDD44"),
	"CONDUCTING": Color("#FFDD44"),
	"LIVING": Color("#44FF44"),
	"EXPLOSIVE": Color("#FF8844"),
	"CORROSIVE": Color("#AA44FF"),
	"TOXIC": Color("#AA44FF"),
	"MAGNETIC": Color("#448888"),
	"FLOATING": Color("#88DDFF"),
	"GLOWING": Color("#FFD700"),
	"WET": Color("#4499DD"),
}
const DEFAULT: Color = Color("#AAAAAA")
const HEAL: Color = Color("#44FF88")

static func get_color(tag: String) -> Color:
	return COLORS.get(tag, DEFAULT)
