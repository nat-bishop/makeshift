class_name BehaviorDisplay

## Format verb+target behavior for display.

const VERB_PHRASES: Dictionary = {
	"destroy": "Attacks %s",
	"eat": "Eats %s",
	"investigate": "Investigates %s",
	"follow": "Follows %s",
	"protect": "Protects %s",
	"flee": "Flees from %s",
}


static func format_behavior(b: Dictionary) -> String:
	var verb: String = b.get("verb", "?")
	var target_text: String = b.get("target", "?")
	var phrase: String = VERB_PHRASES.get(verb, "%s → " + target_text)
	if "%s" in phrase:
		return phrase % target_text
	return phrase
