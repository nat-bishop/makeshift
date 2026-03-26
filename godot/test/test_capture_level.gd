extends SceneTree
## Capture level 1 visuals by simulating the real game startup flow.
## Run: cd godot && godot --write-movie screenshots/level1/frame.png \
##      --fixed-fps 10 --quit-after 30 --script test/test_capture_level.gd 2>&1

var _frame: int = 0
var _started: bool = false


func _initialize() -> void:
	print("CAPTURE: Waiting for main menu to load...")


func _process(_delta: float) -> bool:
	_frame += 1

	# Frame 5: trigger game start (gives autoloads time to initialize)
	if _frame == 5 and not _started:
		_started = true
		var root := get_root()
		for child in root.get_children():
			if child.name == "GameManager":
				print("CAPTURE: Starting game via GameManager.start_game(0)")
				child.start_game(0)
				break

	# Frame 15: log what we see
	if _frame == 15:
		var root := get_root()
		var player := _find_node_by_name(root, "Player")
		if player:
			print("ASSERT PASS: Player at %s" % str(player.global_position))
		else:
			print("ASSERT FAIL: Player not found")

		var level := _find_node_by_name(root, "Level01")
		if level:
			print("ASSERT PASS: Level01 loaded")
		else:
			print("ASSERT FAIL: Level01 not found")

	return false


func _find_node_by_name(node: Node, target: String) -> Node:
	if node.name == target:
		return node
	for child in node.get_children():
		var found := _find_node_by_name(child, target)
		if found:
			return found
	return null
