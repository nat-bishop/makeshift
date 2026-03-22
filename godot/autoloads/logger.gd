extends Node

enum Level { DEBUG, INFO, WARN, ERROR }

var current_level: Level = Level.DEBUG


func _ready() -> void:
	if not OS.is_debug_build():
		current_level = Level.WARN


func debug(msg: String) -> void:
	if current_level <= Level.DEBUG:
		print_rich("[color=gray][DEBUG] %s[/color]" % msg)


func info(msg: String) -> void:
	if current_level <= Level.INFO:
		print_rich("[color=cyan][INFO][/color] %s" % msg)


func warn(msg: String) -> void:
	if current_level <= Level.WARN:
		print_rich("[color=yellow][WARN][/color] %s" % msg)
		push_warning(msg)


func error(msg: String) -> void:
	if current_level <= Level.ERROR:
		print_rich("[color=red][ERROR][/color] %s" % msg)
		push_error(msg)
