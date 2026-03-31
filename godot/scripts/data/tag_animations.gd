class_name TagAnimations

## Procedural animations (per-frame sine/noise in _process) ────────────────

# Vertical bob (position.y sine wave)
const BOBBING: Dictionary = {
	"FLOATING": { "amplitude": 3.0, "speed": 2.0 },
}

# Rotation oscillation (rotation sine wave)
const SWAYING: Dictionary = {
	"WIND_SOURCE": { "amplitude": 0.1, "speed": 4.0 },
}

# Uniform scale pulse (scale sine wave around base)
const BREATHING: Dictionary = {
	"LIVING": { "amplitude": 0.03, "speed": 1.5 },
}

# Alpha oscillation (modulate.a sine wave)
const ALPHA_PULSE: Dictionary = {
	"GLOWING": { "base_alpha": 0.85, "amplitude": 0.15, "speed": 3.0 },
}

# Color channel sine wave (additive RGB offsets to Color.WHITE)
const COLOR_SHIFT: Dictionary = {
	"FROZEN": {
		"r_offset": -1.0, "g_offset": -1.0, "b_offset": 1.0,
		"amplitude": 0.05, "speed": 2.5,
	},
	"CORRODED": {
		"r_offset": -0.5, "g_offset": 0.5, "b_offset": -1.0,
		"amplitude": 0.04, "speed": 1.5,
	},
}

# Random color flash (timer-based, overrides color when active)
const FLASH: Dictionary = {
	"ELECTRIC": {
		"color": Color(1.2, 1.2, 0.5), "duration": 0.08,
		"min_interval": 0.5, "max_interval": 2.0,
	},
	"HEAT_SOURCE": {
		"color": Color(1.3, 0.9, 0.4), "duration": 0.05,
		"min_interval": 0.1, "max_interval": 0.4,
	},
}

# Random position noise (per-frame randf offset)
const JITTER: Dictionary = {
	"EXPLOSIVE": { "intensity": 1.5 },
	"BRITTLE": { "intensity": 0.5 },
}


## Shaders (applied once as ShaderMaterial on sprite) ──────────────────────

const _RIPPLE: Shader = preload("res://shaders/ripple.gdshader")
const _GAS: Shader = preload("res://shaders/gas.gdshader")

const SHADERS: Dictionary = {
	"LIQUID": {
		"shader": _RIPPLE,
		"params": {},
		"affects_alpha": false,
	},
	"MOLTEN": {
		"shader": _RIPPLE,
		"params": { "amplitude": 0.04, "speed": 2.0 },
		"affects_alpha": false,
	},
	"GAS": {
		"shader": _GAS,
		"params": {},
		"affects_alpha": true,
	},
}


## Ambient particles (continuous CPUParticles2D, created/removed with tags) ─

const PARTICLES: Dictionary = {
	"HEAT_SOURCE": {
		"color": Color(1.0, 0.5, 0.1, 0.8),
		"amount": 4,
		"direction": Vector2(0, -1),
		"velocity_min": 15.0, "velocity_max": 30.0,
		"spread": 30.0,
		"lifetime": 0.8,
		"scale_min": 2.0, "scale_max": 4.0,
		"gravity": Vector2(0, -20),
	},
	"TOXIC": {
		"color": Color(0.4, 0.8, 0.2, 0.7),
		"amount": 3,
		"direction": Vector2(0, -1),
		"velocity_min": 5.0, "velocity_max": 12.0,
		"spread": 50.0,
		"lifetime": 1.2,
		"scale_min": 2.0, "scale_max": 3.0,
		"gravity": Vector2(0, -10),
	},
	"ACIDIC": {
		"color": Color(0.7, 0.3, 1.0, 0.7),
		"amount": 3,
		"direction": Vector2(0, 1),
		"velocity_min": 5.0, "velocity_max": 15.0,
		"spread": 20.0,
		"lifetime": 0.6,
		"scale_min": 2.0, "scale_max": 3.0,
		"gravity": Vector2(0, 40),
	},
	"MOLTEN": {
		"color": Color(1.0, 0.4, 0.0, 0.8),
		"amount": 3,
		"direction": Vector2(0, -1),
		"velocity_min": 10.0, "velocity_max": 25.0,
		"spread": 40.0,
		"lifetime": 0.6,
		"scale_min": 2.0, "scale_max": 3.0,
		"gravity": Vector2(0, -15),
	},
}
