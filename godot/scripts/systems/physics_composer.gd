class_name PhysicsComposer
extends RefCounted

## V3: continuous logarithmic scaling from height_cm.
## scale_from_height() gives smooth progression; size_from_height() still
## provides category labels for debug/passive-push checks.

## Reference height: 100cm object = 1.0x scale
const REFERENCE_CM: float = 100.0
## Scale floor/ceiling
const MIN_SCALE: float = 0.2
const MAX_SCALE: float = 12.0
## Height clamp for the log curve
const MIN_CM: float = 1.0
const MAX_CM: float = 5000.0

## Base sprite/collision sizes at 1.0x scale (medium reference)
const BASE_SPRITE: float = 72.0
const BASE_COLLISION: float = 56.0

## Surface type → friction coefficient (single source of truth for GDScript)
const SURFACE_FRICTION: Dictionary = {0: 0.05, 1: 0.5, 2: 1.0}


## Logarithmic scale: log2(height/100) compressed by 0.7, clamped to MIN..MAX.
static func scale_from_height(height_cm: int) -> float:
	var h: float = clampf(float(height_cm), MIN_CM, MAX_CM)
	var log_ratio: float = log(h / REFERENCE_CM) / log(2.0)  # log2
	# Map log_ratio to scale: 0 → 1.0x, each ±1 doubles/halves
	var raw_scale: float = pow(2.0, log_ratio * 0.7)  # 0.7 compresses extremes
	return clampf(raw_scale, MIN_SCALE, MAX_SCALE)


## Mass multiplier derived from continuous scale.
static func get_size_mass_multiplier(height_cm: int) -> float:
	return scale_from_height(height_cm)


## Continuous world sprite size from height_cm.
static func world_sprite_size(height_cm: int) -> float:
	return BASE_SPRITE * scale_from_height(height_cm)


## Continuous world collision size from height_cm.
static func world_collision_size(height_cm: int) -> float:
	return BASE_COLLISION * scale_from_height(height_cm)


## Category label for debug display, passive push checks, etc.
static func size_from_height(height_cm: int) -> String:
	if height_cm < 10: return "tiny"
	if height_cm < 50: return "small"
	if height_cm < 150: return "medium"
	if height_cm < 400: return "large"
	return "huge"
