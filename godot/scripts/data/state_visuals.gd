class_name StateVisuals
extends RefCounted

## V3 state-keyed visual configs. Replaces V2 TagAnimations.
## Each state maps to particle, shader, color shift, flash, and light configs.

# --- Particle configs (per state) ---
const PARTICLES: Dictionary = {
	"on_fire": {
		"color": Color(1.0, 0.5, 0.0, 0.8),
		"direction": Vector2(0, -1),
		"amount": 8,
		"speed": 40.0,
		"spread": 30.0,
	},
	"wet": {
		"color": Color(0.3, 0.5, 1.0, 0.6),
		"direction": Vector2(0, 1),
		"amount": 4,
		"speed": 20.0,
		"spread": 15.0,
	},
	"electrified": {
		"color": Color(1.0, 1.0, 0.2, 0.9),
		"direction": Vector2(0, 0),
		"amount": 6,
		"speed": 60.0,
		"spread": 180.0,
	},
	"poisoned": {
		"color": Color(0.2, 0.8, 0.1, 0.7),
		"direction": Vector2(0, -1),
		"amount": 5,
		"speed": 25.0,
		"spread": 40.0,
	},
	"corroded": {
		"color": Color(0.6, 0.4, 0.1, 0.6),
		"direction": Vector2(0, 1),
		"amount": 3,
		"speed": 15.0,
		"spread": 20.0,
	},
	"molten": {
		"color": Color(1.0, 0.4, 0.0, 0.9),
		"direction": Vector2(0, -1),
		"amount": 6,
		"speed": 30.0,
		"spread": 25.0,
	},
}

# --- Color shift (modulate tint) ---
const COLOR_SHIFT: Dictionary = {
	"frozen": Color(0.6, 0.8, 1.0, 1.0),
	"poisoned": Color(0.7, 1.0, 0.6, 1.0),
	"corroded": Color(0.8, 0.6, 0.4, 1.0),
}

# --- Flash configs ---
const FLASH: Dictionary = {
	"on_fire": {"interval": 0.3, "color": Color(1.0, 0.6, 0.0)},
	"electrified": {"interval": 0.5, "color": Color(1.0, 1.0, 0.3)},
}

# --- PointLight2D configs ---
const LIGHTS: Dictionary = {
	"on_fire": {"color": Color(1.0, 0.5, 0.0), "energy": 0.8, "range": 64.0},
	"molten": {"color": Color(1.0, 0.3, 0.0), "energy": 1.0, "range": 48.0},
}

# --- Shader states ---
# "frozen" uses ice shader, "molten" uses ripple shader
const SHADER_STATES: Dictionary = {
	"frozen": "ice",
	"molten": "ripple",
}

# --- State colors (for damage flash, debug overlay) ---
const COLORS: Dictionary = {
	"on_fire": Color(1.0, 0.5, 0.0),
	"frozen": Color(0.4, 0.7, 1.0),
	"wet": Color(0.3, 0.5, 1.0),
	"electrified": Color(1.0, 1.0, 0.2),
	"poisoned": Color(0.2, 0.8, 0.1),
	"corroded": Color(0.6, 0.4, 0.1),
	"molten": Color(1.0, 0.3, 0.0),
}

const HEAL_COLOR: Color = Color(0.3, 1.0, 0.3)

# --- Physics-derived visual thresholds ---
# These aren't state-based — they're derived from blueprint physics values at creation time.
const BOBBING_GRAVITY_THRESHOLD: int = 25  # gravity < 25 -> bobbing
const BREATHING_AUTONOMOUS: bool = true  # autonomous == true -> breathing
const SQUASH_BOUNCE_THRESHOLD: int = 60  # bounce > 60 -> squash/stretch on collision
