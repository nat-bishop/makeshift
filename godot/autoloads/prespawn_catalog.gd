extends Node
## Hand-authored catalog of prespawned level objects.
##
## Loaded once from res://data/prespawns.json at autoload startup. Levels look
## up entries by type_id via `build_blueprint()` and pass the result to
## BaseLevel._spawn_prespawn (which handles runtime id assignment + spawn).
##
## Adding a new prespawn type:
##   1. Bake a sprite PNG into godot/assets/prespawn/ via
##      `python backend/scripts/bake_prespawn_sprite.py`.
##   2. Add an entry to res://data/prespawns.json (fields below).
##   3. Reference it from a level with `_spawn_prespawn("type_id", pos)`.

const CATALOG_PATH: String = "res://data/prespawns.json"

var _entries: Dictionary = {}


func _ready() -> void:
	_load_catalog()


func _load_catalog() -> void:
	if not FileAccess.file_exists(CATALOG_PATH):
		Log.warn("PrespawnCatalog: Missing %s" % CATALOG_PATH)
		return
	var file := FileAccess.open(CATALOG_PATH, FileAccess.READ)
	if file == null:
		Log.warn("PrespawnCatalog: Failed to open %s" % CATALOG_PATH)
		return
	var text: String = file.get_as_text()
	file.close()
	var parsed: Variant = JSON.parse_string(text)
	if not parsed is Dictionary:
		Log.warn("PrespawnCatalog: %s is not a JSON object" % CATALOG_PATH)
		return
	_entries = parsed
	Log.info("PrespawnCatalog: Loaded %d entries" % _entries.size())


func build_blueprint(type_id: String, overrides: Dictionary = {}) -> Dictionary:
	## Build a full GameObject blueprint for `type_id`, merging in `overrides`
	## and preloading the baked sprite. Returns {} if the type is unknown.
	if not _entries.has(type_id):
		return {}

	var bp: Dictionary = (_entries[type_id] as Dictionary).duplicate(true)
	_deep_merge(bp, overrides)

	var sprite_path: String = bp.get("sprite", "")
	if sprite_path != "":
		var texture: Texture2D = load(sprite_path) as Texture2D
		if texture != null:
			bp["_preloaded_sprite"] = texture
		else:
			Log.warn("PrespawnCatalog: Failed to load sprite '%s' for '%s'" % [sprite_path, type_id])

	return bp


func _deep_merge(target: Dictionary, source: Dictionary) -> void:
	for key in source.keys():
		var sv: Variant = source[key]
		if sv is Dictionary and target.get(key, null) is Dictionary:
			_deep_merge(target[key], sv)
		else:
			target[key] = sv
