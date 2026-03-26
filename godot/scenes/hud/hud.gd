extends CanvasLayer

@onready var object_creation_panel: PanelContainer = %ObjectCreationPanel
@onready var objective_label: Label = %ObjectiveLabel


func _ready() -> void:
	layer = 10
	process_mode = Node.PROCESS_MODE_ALWAYS
	object_creation_panel.visible = false


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("create_object"):
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
