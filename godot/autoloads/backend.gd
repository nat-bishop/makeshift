extends Node

var base_url: String = "http://127.0.0.1:8000"
var ws_url: String = "ws://127.0.0.1:8000"
var session_id: String = ""
var _ws: WebSocketPeer
var _ws_connected: bool = false
var _reconnect_timer: float = 0.0
var _reconnect_delay: float = 1.0
var _sprite_cache: Dictionary = {}  # object_id -> Texture2D
var _pending_sprites: Array = []  # object_ids waiting for sprites
var _sync_timer: float = 0.0
const SYNC_INTERVAL: float = 10.0
var offline_mode: bool = false
var _etag: String = ""
var _state_dirty: bool = false

const SAVE_PATH: String = "user://save.json"
const MAX_RECONNECT_DELAY: float = 30.0


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	_load_session_id()


func _process(delta: float) -> void:
	_process_websocket(delta)
	_process_sync_timer(delta)
	_process_reconnect(delta)


# --- Session Management ---

func create_session() -> Dictionary:
	var result: Dictionary = await _http_post("/api/sessions", {})
	if result.get("error", false):
		Log.warn("Backend: Session creation failed: %s" % result.get("message", "unknown"))
		offline_mode = true
		return result

	session_id = result.get("session_id", "")
	if session_id != "":
		_save_session_id()
		_connect_websocket()

	# Load rules from session response
	var rules: Array = result.get("rules", [])
	if not rules.is_empty():
		RuleEngine.load_rules(rules)

	Log.info("Backend: Session created id=%s" % session_id)
	return result


func restore_session(id: String) -> Dictionary:
	var result: Dictionary = await _http_get("/api/sessions/%s" % id)
	if result.get("error", false):
		Log.warn("Backend: Session restore failed for %s: %s" % [id, result.get("message", "unknown")])
		return result

	Log.info("Backend: Session restored id=%s" % id)
	session_id = id
	_save_session_id()
	_connect_websocket()

	var rules: Array = result.get("rules", [])
	if not rules.is_empty():
		RuleEngine.load_rules(rules)

	return result


func create_object(description: String) -> Dictionary:
	if session_id.is_empty():
		return {"error": true, "message": "No active session"}

	Log.info("Backend: Creating object from '%s'" % description)

	var result: Dictionary = await _http_post(
		"/api/sessions/%s/objects" % session_id,
		{"description": description}
	)

	if result.get("error", false):
		Log.warn("Backend: Object creation failed: %s" % result.get("message", "unknown"))
	else:
		var blueprint: Dictionary = result.get("blueprint", result)
		Log.info("Backend: Object created '%s' (id=%s)" % [blueprint.get("name", "?"), blueprint.get("id", "?")])
		EventBus.object_created.emit(blueprint)
		# Track pending sprite
		var object_id: String = blueprint.get("id", "")
		if object_id != "":
			_pending_sprites.append(object_id)

	return result


func fetch_rules() -> Array:
	var headers: PackedStringArray = PackedStringArray()
	if _etag != "":
		headers.append("If-None-Match: %s" % _etag)

	var result: Dictionary = await _http_get("/api/rules", headers)

	if result.get("status_code", 0) == 304:
		return []  # Not modified, use cached

	var new_etag: String = result.get("etag", "")
	if new_etag != "":
		_etag = new_etag

	var rules: Array = result.get("rules", [])
	if not rules.is_empty():
		RuleEngine.load_rules(rules)
	return rules


func sync_state(state: Dictionary) -> void:
	if session_id.is_empty() or offline_mode:
		return
	Log.debug("Backend: Syncing state to server")
	await _http_put("/api/sessions/%s/sync" % session_id, state)


func get_cached_sprite(object_id: String) -> Texture2D:
	return _sprite_cache.get(object_id, null)



# --- WebSocket ---

func _connect_websocket() -> void:
	if session_id.is_empty():
		return

	_ws = WebSocketPeer.new()
	var url: String = "%s/ws/%s" % [ws_url, session_id]
	var err: int = _ws.connect_to_url(url)
	if err != OK:
		Log.warn("Backend: WebSocket connection failed: %d" % err)
		_ws_connected = false
		_reconnect_timer = _reconnect_delay
	else:
		_ws_connected = false  # Will be set true on STATE_OPEN


func _process_websocket(_delta: float) -> void:
	if _ws == null:
		return

	_ws.poll()

	var state: int = _ws.get_ready_state()
	match state:
		WebSocketPeer.STATE_OPEN:
			if not _ws_connected:
				_ws_connected = true
				_reconnect_delay = 1.0
				Log.info("Backend: WebSocket connected to session %s" % session_id)
				# Re-request pending sprites
				for obj_id in _pending_sprites:
					_ws.send_text(JSON.stringify({
						"type": "request_sprite",
						"object_id": obj_id
					}))

			while _ws.get_available_packet_count() > 0:
				var packet: PackedByteArray = _ws.get_packet()
				var text: String = packet.get_string_from_utf8()
				_handle_ws_message(text)

		WebSocketPeer.STATE_CLOSING:
			pass

		WebSocketPeer.STATE_CLOSED:
			_ws_connected = false
			_reconnect_timer = _reconnect_delay


func _handle_ws_message(text: String) -> void:
	var json := JSON.new()
	var err: int = json.parse(text)
	if err != OK:
		Log.warn("Backend: Failed to parse WS message")
		return

	var data: Dictionary = json.data
	var msg_type: String = data.get("type", "")

	match msg_type:
		"sprite_ready":
			_handle_sprite_ready(data)
		"sprite_failed":
			_handle_sprite_failed(data)
		"error":
			Log.warn("Backend WS error: %s" % data.get("message", "unknown"))


func _handle_sprite_ready(data: Dictionary) -> void:
	var object_id: String = data.get("object_id", "")
	var sprite_url: String = data.get("sprite_url", "")
	if object_id.is_empty() or sprite_url.is_empty():
		Log.warn("Backend: Malformed sprite_ready message: %s" % [data])
		return

	var full_url: String = base_url + sprite_url
	Log.debug("Backend: Fetching sprite for %s from %s" % [object_id, full_url])

	var body: PackedByteArray = await _fetch_binary(full_url)
	if body.is_empty():
		Log.warn("Backend: Sprite fetch failed for %s" % object_id)
		return

	var image := Image.new()
	var load_err: int = image.load_png_from_buffer(body)
	if load_err != OK:
		Log.warn("Backend: Failed to decode sprite PNG for %s" % object_id)
		return

	var texture := ImageTexture.create_from_image(image)
	_sprite_cache[object_id] = texture
	_pending_sprites.erase(object_id)

	Log.info("Backend: Sprite ready for %s" % object_id)
	EventBus.sprite_ready.emit(object_id, texture)


func _handle_sprite_failed(data: Dictionary) -> void:
	var object_id: String = data.get("object_id", "")
	if object_id.is_empty():
		return
	var reason: String = data.get("reason", "unknown")
	_pending_sprites.erase(object_id)
	Log.warn("Backend: Sprite generation failed for %s: %s" % [object_id, reason])
	EventBus.sprite_failed.emit(object_id)


func _process_reconnect(delta: float) -> void:
	if _ws_connected or _ws == null:
		return
	if _reconnect_timer <= 0.0:
		return

	_reconnect_timer -= delta
	if _reconnect_timer <= 0.0:
		Log.debug("Backend: Reconnecting WebSocket (delay=%.1fs)" % _reconnect_delay)
		# Exponential backoff
		_reconnect_delay = minf(_reconnect_delay * 2.0, MAX_RECONNECT_DELAY)
		_connect_websocket()


# --- Sync Timer ---

func _process_sync_timer(delta: float) -> void:
	if session_id.is_empty() or offline_mode or not _state_dirty:
		return

	_sync_timer += delta
	if _sync_timer >= SYNC_INTERVAL:
		_sync_timer = 0.0
		_state_dirty = false
		_on_sync_timer()


func mark_dirty() -> void:
	_state_dirty = true


func _on_sync_timer() -> void:
	# Collect current game state from GameManager / world
	# This is a lightweight sync of object positions and states
	var state: Dictionary = _gather_game_state()
	sync_state(state)


func _gather_game_state() -> Dictionary:
	var objects: Array = []
	var world = get_tree().get_first_node_in_group("world")
	if world and world.has_method("get_objects_data"):
		objects = world.get_objects_data()

	return {
		"objects": objects,
	}


# --- HTTP Helpers ---

func _http_post(path: String, body: Dictionary) -> Dictionary:
	return await _request(HTTPClient.METHOD_POST, path, body)


func _http_get(path: String, extra_headers: PackedStringArray = PackedStringArray()) -> Dictionary:
	return await _request(HTTPClient.METHOD_GET, path, {}, extra_headers)


func _http_put(path: String, body: Dictionary) -> Dictionary:
	return await _request(HTTPClient.METHOD_PUT, path, body)


func _fetch_binary(url: String) -> PackedByteArray:
	var http := HTTPRequest.new()
	http.timeout = 15.0
	add_child(http)

	var err: int = http.request(url)
	if err != OK:
		Log.warn("Backend: Binary fetch failed for %s: %d" % [url, err])
		http.queue_free()
		return PackedByteArray()

	var response: Array = await http.request_completed
	http.queue_free()

	var result_code: int = response[0]
	var status_code: int = response[1]
	if result_code != HTTPRequest.RESULT_SUCCESS or status_code != 200:
		Log.warn("Backend: Binary fetch error %s (result=%d, status=%d)" % [url, result_code, status_code])
		return PackedByteArray()

	return response[3]


const _METHOD_NAMES: Array[String] = ["GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", "TRACE", "PATCH"]

func _request(method: int, path: String, body: Dictionary = {}, extra_headers: PackedStringArray = PackedStringArray()) -> Dictionary:
	var url: String = base_url + path
	var method_name: String = _METHOD_NAMES[method] if method < _METHOD_NAMES.size() else str(method)
	Log.debug("Backend: %s %s" % [method_name, url])
	var headers: PackedStringArray = PackedStringArray(["Content-Type: application/json"])
	for h in extra_headers:
		headers.append(h)

	var body_str: String = ""
	if not body.is_empty():
		body_str = JSON.stringify(body)

	# Use a fresh HTTPRequest for each call to allow concurrent requests
	var http := HTTPRequest.new()
	http.timeout = 15.0
	add_child(http)

	var err: int
	if body_str.is_empty():
		err = http.request(url, headers, method)
	else:
		err = http.request(url, headers, method, body_str)

	if err != OK:
		Log.warn("Backend: HTTP request failed %s err=%d" % [path, err])
		http.queue_free()
		return {"error": true, "message": "HTTP request failed: %d" % err}

	var response: Array = await http.request_completed
	http.queue_free()

	var result_code: int = response[0]
	var status_code: int = response[1]
	var response_headers: PackedStringArray = response[2]
	var response_body: PackedByteArray = response[3]

	if result_code != HTTPRequest.RESULT_SUCCESS:
		Log.warn("Backend: HTTP error %s result=%d" % [path, result_code])
		return {"error": true, "message": "HTTP error: %d" % result_code}

	if status_code == 304:
		return {"status_code": 304}

	if status_code < 200 or status_code >= 300:
		Log.warn("Backend: HTTP %d from %s" % [status_code, path])
		return {"error": true, "message": "HTTP %d" % status_code, "status_code": status_code}

	var text: String = response_body.get_string_from_utf8()
	if text.is_empty():
		return {"status_code": status_code}

	var json := JSON.new()
	var parse_err: int = json.parse(text)
	if parse_err != OK:
		Log.warn("Backend: JSON parse error from %s" % path)
		return {"error": true, "message": "JSON parse error"}

	var result: Dictionary = json.data if json.data is Dictionary else {"data": json.data}

	# Extract ETag from response headers
	for header in response_headers:
		if header.to_lower().begins_with("etag:"):
			result["etag"] = header.substr(5).strip_edges()
			break

	result["status_code"] = status_code
	return result


# --- V2 Embedding ---

func post_embed(body: Dictionary, callback: Callable) -> void:
	## Call POST /api/embed to re-embed an object's identity after tag changes.
	## Fires callback(embedding: Array) on completion.
	var result: Dictionary = await _http_post("/api/embed", body)
	if result.has("error"):
		Log.warn("Backend: Embed request failed: %s" % result.get("message", "unknown"))
		callback.call([])
		return
	var embedding: Array = result.get("embedding", [])
	callback.call(embedding)


# --- Session Persistence ---

func _save_session_id() -> void:
	if session_id.is_empty():
		return
	var file := FileAccess.open(SAVE_PATH, FileAccess.WRITE)
	if file:
		file.store_string(JSON.stringify({"session_id": session_id}))
		file.close()
		Log.debug("Backend: Saved session_id to disk")


func _load_session_id() -> void:
	if not FileAccess.file_exists(SAVE_PATH):
		return
	var file := FileAccess.open(SAVE_PATH, FileAccess.READ)
	if file:
		var text: String = file.get_as_text()
		file.close()
		var json := JSON.new()
		if json.parse(text) == OK and json.data is Dictionary:
			session_id = json.data.get("session_id", "")
			if not session_id.is_empty():
				Log.debug("Backend: Loaded session_id=%s from disk" % session_id)
