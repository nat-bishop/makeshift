extends Node2D
## Base class for all levels. Provides spawn point, goal area, and objective.

@export var level_id: int = 0
@export var objective_text: String = ""
@export var next_level_path: String = ""

@onready var spawn_point: Marker2D = $SpawnPoint
@onready var goal_area: Area2D = $Goal


func _ready() -> void:
	goal_area.body_entered.connect(_on_goal_body_entered)


func get_objective_text() -> String:
	return objective_text


func _on_goal_body_entered(body: Node) -> void:
	if body is CharacterBody2D and body.has_method("get_effective_tags"):
		EventBus.level_completed.emit(level_id)
