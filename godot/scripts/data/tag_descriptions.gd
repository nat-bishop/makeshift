class_name TagDescriptions

const DESCRIPTIONS: Dictionary = {
	# Physical State
	"SOLID": "Holds its shape. Standard physical material.",
	"LIQUID": "Flows and pools. Low friction, no bounce.",
	"GAS": "Near-weightless. Floats and disperses.",
	"RIGID": "Stiff and durable. Resists deformation.",
	"FLEXIBLE": "Bends without breaking. Moderate bounce.",
	"HEAVY": "High mass. Hard to move, hits hard.",
	"LIGHT": "Low mass. Easy to push around.",
	# Temperature
	"FROZEN": "Ice-cold. Slippery surface, shatters easily.",
	"COLD": "Chilly. Can freeze flammable things.",
	"HOT": "Burning hot. Ignites flammable objects.",
	"MOLTEN": "Liquid fire. Extremely heavy and sticky.",
	# Energy
	"FLAMMABLE": "Catches fire from heat sources.",
	"HEAT_SOURCE": "Radiates heat. Ignites nearby flammables.",
	"ELECTRIC": "Carries charge. Zaps conducting objects.",
	"MAGNETIC": "Attracts and repels metal objects.",
	"EXPLOSIVE": "Detonates under the right conditions.",
	# Surface
	"SHARP": "Cuts on contact. Deals extra damage.",
	"STICKY": "Slows everything nearby. High friction, strong drag.",
	"SLIPPERY": "Nearly frictionless. Hard to grip.",
	"REFLECTIVE": "Bounces light and some effects.",
	# Mechanical
	"BOUNCY": "Springs off surfaces. High restitution.",
	"BREAKABLE": "Fragile. Low durability.",
	# Environmental
	"FLOATING": "Defies gravity. Hovers in place.",
	"WIND_SOURCE": "Generates air currents.",
	"CORROSIVE": "Dissolves materials over time.",
	"TOXIC": "Poisons living things on contact.",
	"WET": "Damp. Freezes easier, conducts electricity better, resists fire. Dries near heat.",
	# Special
	"LIVING": "Alive. Can be targeted by behaviors.",
	"HOSTILE": "Aggressive. Danger aura deals damage and knockback at close range.",
	"GLOWING": "Emits soft light.",
	"CONDUCTING": "Transfers electricity between objects.",
	"INSULATING": "Blocks electrical transfer.",
}


static func get_description(tag: String) -> String:
	return DESCRIPTIONS.get(tag, "")
