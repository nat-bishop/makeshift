class_name FieldConfig extends RefCounted

## Maps field-emitting tags to their range category and field mode.
## Range is how far the field extends; mode is continuous (per-frame force)
## or periodic (timer-based rule evaluation).

# --- Range categories (pixels) ---
const RANGE_PX := {
	"CLOSE": 64.0,
	"MEDIUM": 96.0,
	"FAR": 192.0,
}

# --- Periodic tick interval (seconds) ---
const PERIODIC_INTERVAL: float = 2.0

# --- Per-frame force scale for continuous fields ---
# Continuous fields read force_magnitude from the rule's APPLY_FORCE effect.
# No separate scaling needed — rule authors set the value for per-frame use.

# --- Tag → field properties ---
# mode: "continuous" = per-frame apply_central_force, "periodic" = timer-based rule eval
const FIELD_TAGS := {
	"WIND_SOURCE":  {"range": "FAR",    "mode": "continuous"},
	"MAGNETIC":     {"range": "MEDIUM", "mode": "continuous"},
	"GLOWING":      {"range": "MEDIUM", "mode": "continuous"},
	"HEAT_SOURCE":  {"range": "CLOSE",  "mode": "periodic"},
	"HOT":          {"range": "CLOSE",  "mode": "periodic"},
	"ELECTRIC":     {"range": "CLOSE",  "mode": "periodic"},
	"COLD":         {"range": "CLOSE",  "mode": "periodic"},
	"TOXIC":        {"range": "MEDIUM", "mode": "periodic"},
	"LIQUID":       {"range": "CLOSE",  "mode": "periodic"},
}

static func is_field_tag(tag: String) -> bool:
	return tag in FIELD_TAGS

static func has_any_field_tag(tags: Array) -> bool:
	for tag in tags:
		if tag in FIELD_TAGS:
			return true
	return false

static func get_range_px(tag: String) -> float:
	var entry: Dictionary = FIELD_TAGS.get(tag, {})
	var cat: String = entry.get("range", "MEDIUM")
	return RANGE_PX.get(cat, 96.0)

static func is_continuous(tag: String) -> bool:
	var entry: Dictionary = FIELD_TAGS.get(tag, {})
	return entry.get("mode", "periodic") == "continuous"

static func get_max_range_px(tags: Array) -> float:
	var max_r: float = 0.0
	for tag in tags:
		if tag in FIELD_TAGS:
			var r: float = get_range_px(tag)
			if r > max_r:
				max_r = r
	return max_r
