class_name StateVisuals

const STATE_PARTICLES: Dictionary = {
	"on_fire": {"color": Color(1, 0.5, 0), "direction": Vector2.UP, "amount": 12},
	"wet": {"color": Color(0.3, 0.5, 0.8), "direction": Vector2.DOWN, "amount": 6},
	"electrified": {"color": Color(1, 1, 0.3), "direction": Vector2.ZERO, "amount": 8},
	"poisoned": {"color": Color(0.3, 0.8, 0.3), "direction": Vector2.UP, "amount": 6},
	"corroded": {"color": Color(0.6, 0.4, 0.2), "direction": Vector2.DOWN, "amount": 4},
	"molten": {"color": Color(1, 0.3, 0), "direction": Vector2.UP, "amount": 10},
}
const STATE_SHADERS: Dictionary = {
	"frozen": "res://shaders/ice.gdshader",
	"molten": "res://shaders/ripple.gdshader",
}
const STATE_COLOR_SHIFTS: Dictionary = {
	"frozen": Color(0.5, 0.8, 1.0),
	"poisoned": Color(0.3, 0.8, 0.3),
	"corroded": Color(0.6, 0.4, 0.2),
}
const STATE_LIGHTS: Dictionary = {
	"on_fire": {"color": Color(1, 0.6, 0.2), "energy": 0.8, "texture_scale": 64.0},
	"molten": {"color": Color(1, 0.4, 0.1), "energy": 0.5, "texture_scale": 48.0},
}
