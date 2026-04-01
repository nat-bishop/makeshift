class_name TagManager
extends Node

## Shared tag management component for any taggable entity.
## Owns the tags array and TagDecay child. Emits signals for entity-specific reactions.
## Used by GameObject and EnvironmentBody to avoid duplicated tag add/remove logic.

signal tag_added(tag: String)
signal tag_removed(tag: String)
signal tags_changed(tags: Array[String])

var tags: Array[String] = []
var _tag_decay: TagDecay = null
var _owner_name: String = "?"


func _ready() -> void:
	_tag_decay = TagDecay.new()
	_tag_decay.name = "TagDecay"
	add_child(_tag_decay)


func init_tags(initial_tags: Array, owner_name: String = "?") -> void:
	_owner_name = owner_name
	tags.clear()
	for tag in initial_tags:
		tags.append(str(tag))


func add_tag(tag: String, duration: float = 0.0) -> void:
	var is_new: bool = tag not in tags
	if is_new:
		tags.append(tag)
		Log.debug("TagManager: '%s' +tag %s%s" % [_owner_name, tag, " (%.1fs)" % duration if duration > 0.0 else ""])
		tag_added.emit(tag)
		tags_changed.emit(tags)
	if duration > 0.0:
		_tag_decay.set_decay(tag, duration)


func remove_tag(tag: String) -> void:
	_tag_decay.cancel(tag)
	if tag not in tags:
		return
	Log.debug("TagManager: '%s' -tag %s" % [_owner_name, tag])
	tags.erase(tag)
	tag_removed.emit(tag)
	tags_changed.emit(tags)


func get_tags() -> Array[String]:
	return tags


func has_tag(tag: String) -> bool:
	return tag in tags
