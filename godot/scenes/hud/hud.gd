extends CanvasLayer

@onready var object_creation_panel: PanelContainer = %ObjectCreationPanel
@onready var objective_label: Label = %ObjectiveLabel


func _ready() -> void:
	layer = 10
	object_creation_panel.visible = false


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("create_object"):
		object_creation_panel.visible = !object_creation_panel.visible
		if object_creation_panel.visible:
			object_creation_panel.focus_input()
		get_viewport().set_input_as_handled()


func set_objective(text: String) -> void:
	objective_label.text = text
