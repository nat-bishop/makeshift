class_name TagPhysicsMap

# Each tag maps to {priority, mass, gravity, friction, bounce}
# -1.0 means "not set" (will not override default)

const TAG_PHYSICS: Dictionary = {
	"HEAVY": {
		"priority": 8,
		"mass": 5.0,
		"gravity": 1.2,
		"friction": 0.7,
		"bounce": 0.0,
	},
	"LIGHT": {
		"priority": 7,
		"mass": 0.2,
		"gravity": 0.8,
		"friction": 0.3,
		"bounce": 0.0,
	},
	"BOUNCY": {
		"priority": 6,
		"mass": -1.0,
		"gravity": -1.0,
		"friction": 0.2,
		"bounce": 0.9,
	},
	"STICKY": {
		"priority": 6,
		"mass": -1.0,
		"gravity": -1.0,
		"friction": 2.0,
		"bounce": 0.0,
	},
	"FLOATING": {
		"priority": 9,
		"mass": -1.0,
		"gravity": -0.5,
		"friction": -1.0,
		"bounce": -1.0,
	},
	"FROZEN": {
		"priority": 6,
		"mass": 2.0,
		"gravity": -1.0,
		"friction": 0.05,
		"bounce": 0.3,
	},
	"MOLTEN": {
		"priority": 6,
		"mass": 3.0,
		"gravity": -1.0,
		"friction": 0.9,
		"bounce": 0.0,
	},
	"GAS": {
		"priority": 8,
		"mass": 0.01,
		"gravity": -1.0,
		"friction": 0.0,
		"bounce": 0.0,
	},
	"LIQUID": {
		"priority": 7,
		"mass": 0.8,
		"gravity": 1.0,
		"friction": 0.0,
		"bounce": 0.0,
	},
	"SLIPPERY": {
		"priority": 5,
		"mass": -1.0,
		"gravity": -1.0,
		"friction": 0.05,
		"bounce": -1.0,
	},
	"FLEXIBLE": {
		"priority": 4,
		"mass": -1.0,
		"gravity": -1.0,
		"friction": 0.3,
		"bounce": 0.4,
	},
	"RIGID": {
		"priority": 4,
		"mass": -1.0,
		"gravity": -1.0,
		"friction": 0.6,
		"bounce": 0.1,
	},
}
