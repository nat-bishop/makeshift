class_name StateVisuals
extends RefCounted

## V3 state-keyed visual configs. 4 states: burning, frozen, wet, electrified.
## Each state maps to particle, shader, color shift, flash, and light configs.

# --- Particle configs (per state) ---
const PARTICLES: Dictionary = {
	"burning": {
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
}

# --- Color shift (modulate tint) ---
const COLOR_SHIFT: Dictionary = {
	"frozen": Color(0.6, 0.8, 1.0, 1.0),
}

# --- Flash configs ---
const FLASH: Dictionary = {
	"burning": {"interval": 0.3, "color": Color(1.0, 0.6, 0.0)},
	"electrified": {"interval": 0.5, "color": Color(1.0, 1.0, 0.3)},
}

# --- PointLight2D configs ---
const LIGHTS: Dictionary = {
	"burning": {"color": Color(1.0, 0.5, 0.0), "energy": 0.8, "range": 64.0},
}

# --- Shader states ---
const SHADER_STATES: Dictionary = {
	"frozen": "ice",
}

# --- State colors (for damage flash, debug overlay) ---
const COLORS: Dictionary = {
	"burning": Color(1.0, 0.5, 0.0),
	"frozen": Color(0.4, 0.7, 1.0),
	"wet": Color(0.3, 0.5, 1.0),
	"electrified": Color(1.0, 1.0, 0.2),
}

const HEAL_COLOR: Color = Color(0.3, 1.0, 0.3)

# --- State mechanics constants (shared by game_object + player) ---
const BURNING_DOT: float = 5.0
const BURNING_TICK: float = 1.0
const BURNING_DURATION: float = 10.0
const ELECTRIFIED_DOT: float = 8.0
const ELECTRIFIED_TICK: float = 1.5
const ELECTRIFIED_DURATION: float = 8.0
const WET_FRICTION: float = 0.05
const WET_SPEED_MULT: float = 0.5
const FROZEN_DAMAGE_MULT: float = 2.0

# --- Physics-derived visual thresholds ---
# These aren't state-based — they're derived from blueprint physics values at creation time.
const BOBBING_GRAVITY_THRESHOLD: int = 25  # gravity < 25 -> bobbing
const BREATHING_AUTONOMOUS: bool = true  # autonomous == true -> breathing
const SQUASH_BOUNCE_THRESHOLD: int = 60  # bounce > 60 -> squash/stretch on collision
