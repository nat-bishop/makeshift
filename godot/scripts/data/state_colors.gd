class_name StateColors

const COLORS: Dictionary = {
	"on_fire": Color(1.0, 0.5, 0.0),
	"frozen": Color(0.5, 0.8, 1.0),
	"wet": Color(0.3, 0.5, 0.8),
	"electrified": Color(1.0, 1.0, 0.3),
	"poisoned": Color(0.3, 0.8, 0.3),
	"corroded": Color(0.6, 0.4, 0.2),
	"molten": Color(1.0, 0.3, 0.0),
}
const HEAL: Color = Color(0.3, 1.0, 0.3)

static func get_color(state: String) -> Color:
	return COLORS.get(state, Color.WHITE)

static func is_stateful(body: Node) -> bool:
	return body.has_method("get_states")
