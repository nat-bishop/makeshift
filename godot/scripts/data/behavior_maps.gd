extends RefCounted
class_name BehaviorMaps

## Maps categorical behavior parameters to numeric engine values.
## All values chosen to produce balanced gameplay within the behavior budget system.

# --- Trigger priority (lower number = higher priority for movement conflict) ---
const TRIGGER_PRIORITY := {
	"ON_HEALTH_LOW": 1,
	"ON_TAG_ADDED": 2,
	"ON_DAMAGED": 3,
	"ON_CONTACT": 4,
	"ON_PROXIMITY": 5,
	"ON_TIMER": 6,
	"ALWAYS": 7,
}

# --- Intensity → damage amount ---
const INTENSITY_DAMAGE := {
	"MINIMAL": 5.0,
	"LOW": 10.0,
	"MEDIUM": 20.0,
	"HIGH": 40.0,
	"EXTREME": 80.0,
}

# --- Intensity → force magnitude ---
const INTENSITY_FORCE := {
	"MINIMAL": 50.0,
	"LOW": 100.0,
	"MEDIUM": 200.0,
	"HIGH": 400.0,
	"EXTREME": 800.0,
}

# --- Intensity → heal amount ---
const INTENSITY_HEAL := {
	"MINIMAL": 5.0,
	"LOW": 10.0,
	"MEDIUM": 25.0,
	"HIGH": 50.0,
	"EXTREME": 100.0,
}

# --- Intensity → explode damage (higher than direct damage) ---
const INTENSITY_EXPLODE := {
	"MINIMAL": 10.0,
	"LOW": 20.0,
	"MEDIUM": 40.0,
	"HIGH": 80.0,
	"EXTREME": 150.0,
}

# --- Range → pixel radius ---
const RANGE_PX := {
	"TOUCH": 32.0,
	"CLOSE": 64.0,
	"MEDIUM": 128.0,
	"FAR": 256.0,
}

# --- Speed → max velocity (px/s) ---
const SPEED_MAX := {
	"SLOW": 60.0,
	"MEDIUM": 120.0,
	"FAST": 200.0,
	"VERY_FAST": 300.0,
}

# --- Speed → force applied for movement ---
const SPEED_FORCE := {
	"SLOW": 200.0,
	"MEDIUM": 400.0,
	"FAST": 600.0,
	"VERY_FAST": 800.0,
}

# --- Interval → seconds ---
const INTERVAL_SECONDS := {
	"ONCE_SHORT": 1.0,
	"ONCE_MEDIUM": 3.0,
	"ONCE_LONG": 5.0,
	"SLOW": 3.0,
	"MEDIUM": 1.5,
	"FAST": 0.75,
}

# --- Which intervals are one-shot (true) vs repeating (false) ---
const INTERVAL_IS_ONCE := {
	"ONCE_SHORT": true,
	"ONCE_MEDIUM": true,
	"ONCE_LONG": true,
	"SLOW": false,
	"MEDIUM": false,
	"FAST": false,
}

# --- Parent tag → projectile payload tag ---
const PAYLOAD_TAG_MAP := {
	"HEAT_SOURCE": "HOT",
	"ELECTRIC": "ELECTRIC",
	"TOXIC": "TOXIC",
	"CORROSIVE": "CORROSIVE",
	"FROZEN": "COLD",
}

# --- Movement actions (used for conflict resolution) ---
const MOVEMENT_ACTIONS := ["MOVE_TOWARD", "MOVE_AWAY", "PATROL"]

# --- Projectile constants ---
const PROJECTILE_BASE_TAGS := ["SOLID", "LIGHT", "BREAKABLE"]
const PROJECTILE_DURABILITY := 15
const PROJECTILE_LIFETIME := 2.5
const PROJECTILE_SPEED := 250.0
