extends Node

enum Level { DEBUG, INFO, WARN, ERROR }

var current_level: Level = Level.DEBUG
var file_logging_enabled: bool = true

const LOG_DIR: String = "user://logs/"
const FLUSH_INTERVAL: float = 1.0
var _log_file: FileAccess = null
var _flush_timer: float = 0.0


func _ready() -> void:
	if not OS.is_debug_build():
		current_level = Level.WARN
	_open_log_file()


func _process(delta: float) -> void:
	if _log_file:
		_flush_timer += delta
		if _flush_timer >= FLUSH_INTERVAL:
			_flush_timer = 0.0
			_log_file.flush()


func _exit_tree() -> void:
	if _log_file:
		_log_file.flush()
		_log_file.close()
		_log_file = null


func debug(msg: String) -> void:
	var needs_console := current_level <= Level.DEBUG
	if not _log_file and not needs_console:
		return
	var ts := _timestamp()
	_write_to_file("DEBUG", msg, ts)
	if needs_console:
		print_rich("[color=gray]%s [DEBUG] %s[/color]" % [ts, msg])


func info(msg: String) -> void:
	var needs_console := current_level <= Level.INFO
	if not _log_file and not needs_console:
		return
	var ts := _timestamp()
	_write_to_file("INFO", msg, ts)
	if needs_console:
		print_rich("%s [color=cyan][INFO][/color] %s" % [ts, msg])


func warn(msg: String) -> void:
	var needs_console := current_level <= Level.WARN
	if not _log_file and not needs_console:
		return
	var ts := _timestamp()
	_write_to_file("WARN", msg, ts)
	if needs_console:
		print_rich("%s [color=yellow][WARN][/color] %s" % [ts, msg])
		push_warning(msg)


func error(msg: String) -> void:
	var ts := _timestamp()
	_write_to_file("ERROR", msg, ts)
	if current_level <= Level.ERROR:
		print_rich("%s [color=red][ERROR][/color] %s" % [ts, msg])
		push_error(msg)


func _timestamp() -> String:
	return Time.get_datetime_string_from_system(true)


func _open_log_file() -> void:
	if not file_logging_enabled:
		return
	DirAccess.make_dir_recursive_absolute(LOG_DIR)
	var datetime := Time.get_datetime_string_from_system(true).replace(":", "").replace("-", "").replace("T", "_")
	var path := LOG_DIR + datetime + ".log"
	_log_file = FileAccess.open(path, FileAccess.WRITE)
	if _log_file:
		_log_file.store_line("%s [INFO] Log file opened" % _timestamp())


func _write_to_file(level: String, msg: String, ts: String) -> void:
	if _log_file:
		_log_file.store_line("%s [%s] %s" % [ts, level, msg])
