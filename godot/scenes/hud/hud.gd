extends CanvasLayer

@onready var object_creation_panel: PanelContainer = %ObjectCreationPanel
@onready var objective_label: Label = %ObjectiveLabel
@onready var _action_hint: Label = %ActionHint

var _placement_active: bool = false


func _ready() -> void:
	layer = 10
	process_mode = Node.PROCESS_MODE_ALWAYS
	object_creation_panel.visible = false
	_action_hint.visible = false

	EventBus.placement_started.connect(_on_placement_started)
	EventBus.placement_ended.connect(_on_placement_ended)
	EventBus.debug_toggled.connect(_on_debug_toggled)


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("create_object"):
		if _placement_active:
			return
		object_creation_panel.visible = !object_creation_panel.visible
		Log.debug("HUD: Creation panel %s" % ("opened" if object_creation_panel.visible else "closed"))
		if object_creation_panel.visible:
			object_creation_panel.focus_input()
			GameManager.pause_game()
		else:
			GameManager.resume_game()
		get_viewport().set_input_as_handled()


func set_objective(text: String) -> void:
	objective_label.text = text


func _on_placement_started() -> void:
	_placement_active = true
	_update_action_hint()


func _on_placement_ended() -> void:
	_placement_active = false
	_update_action_hint()


func _on_debug_toggled(enabled: bool) -> void:
	_action_hint.visible = enabled
	if enabled:
		_update_action_hint()


func _update_action_hint() -> void:
	if _placement_active:
		_action_hint.text = "Click: Place  |  Esc: Cancel"
	else:
		_action_hint.text = "Tab: Create  |  E: Kick  |  F3: Debug"
