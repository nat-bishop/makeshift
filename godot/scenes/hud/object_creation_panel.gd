extends PanelContainer

@onready var description_input: LineEdit = %DescriptionInput
@onready var create_button: Button = %CreateButton
@onready var status_label: Label = %StatusLabel
@onready var _creation_form: VBoxContainer = %CreationForm
@onready var _reveal_card: VBoxContainer = %RevealCard
@onready var _reveal_name: Label = %RevealName
@onready var _reveal_tags: HFlowContainer = %RevealTags
@onready var _reveal_size: Label = %RevealSize
@onready var _reveal_cost: Label = %RevealCost
@onready var _close_button: Button = %CloseButton
@onready var _behavior_section: VBoxContainer = %BehaviorSection
@onready var _behavior_list: VBoxContainer = %BehaviorList

var _is_creating := false
var _is_showing_reveal := false
var _is_hovered := false
var _fade_timer: float = -1.0

const REVEAL_TIMEOUT: float = 10.0
const FADE_DURATION: float = 0.5


func _ready() -> void:
	var style := InfoWidgets.make_stylebox(
		Color(0.12, 0.12, 0.15, 0.95), 8, 16, 12, 1, Color(0.4, 0.4, 0.5, 0.8)
	)
	add_theme_stylebox_override("panel", style)

	description_input.max_length = 500
	create_button.pressed.connect(_on_create_pressed)
	description_input.text_submitted.connect(_on_text_submitted)
	_close_button.pressed.connect(_dismiss_reveal)
	status_label.text = ""
	_reveal_card.visible = false

	mouse_entered.connect(_on_mouse_entered)
	mouse_exited.connect(_on_mouse_exited)


func focus_input() -> void:
	# Reset reveal state if panel was reopened while reveal was active
	if _is_showing_reveal:
		_is_showing_reveal = false
		_fade_timer = -1.0
		_reveal_card.modulate.a = 1.0
		_reveal_card.visible = false
		_creation_form.visible = true
	description_input.call_deferred("grab_focus")


func _process(delta: float) -> void:
	if not _is_showing_reveal or _fade_timer < 0.0 or _is_hovered:
		return
	_fade_timer -= delta
	if _fade_timer <= 0.0:
		_fade_timer = -1.0
		_auto_fade_out()


func is_busy() -> bool:
	return _is_creating


func _on_create_pressed() -> void:
	_submit()


func _on_text_submitted(_text: String) -> void:
	_submit()


func _submit() -> void:
	if _is_creating:
		return

	var description := description_input.text.strip_edges()
	if description.is_empty():
		status_label.text = "Enter a description first."
		status_label.add_theme_color_override("font_color", Color(1.0, 0.6, 0.3))
		return

	Log.info("CreationPanel: Submitting '%s' (len=%d)" % [description, description.length()])
	_is_creating = true
	create_button.disabled = true
	status_label.text = "Creating..."
	status_label.add_theme_color_override("font_color", Color(0.7, 0.7, 0.7))
	EventBus.creation_requested.emit()

	var result: Dictionary = await Backend.create_object(description)

	_is_creating = false
	create_button.disabled = false

	if result.get("error", false):
		var error_msg: String = result.get("message", "Creation failed. Try again.")
		Log.warn("CreationPanel: Creation failed: %s" % error_msg)
		status_label.text = error_msg
		status_label.add_theme_color_override("font_color", Color(1.0, 0.3, 0.3))
		EventBus.creation_failed.emit()
	else:
		status_label.text = ""
		description_input.text = ""
		var blueprint: Dictionary = result.get("blueprint", result)
		Log.info("CreationPanel: Created '%s'" % blueprint.get("name", "?"))
		_show_reveal(blueprint)


func _show_reveal(blueprint: Dictionary) -> void:
	Log.debug("CreationPanel: Showing reveal card for '%s'" % blueprint.get("name", "?"))
	_is_showing_reveal = true
	_creation_form.visible = false
	_reveal_card.modulate.a = 1.0
	_reveal_card.visible = true

	_reveal_name.text = blueprint.get("name", "Unknown")

	# Tags
	for child in _reveal_tags.get_children():
		child.queue_free()
	var tags: Array = blueprint.get("tags", [])
	for tag in tags:
		_reveal_tags.add_child(InfoWidgets.create_tag_badge(str(tag)))

	# Behaviors
	for child in _behavior_list.get_children():
		child.queue_free()
	var behaviors: Array = blueprint.get("behaviors", [])
	_behavior_section.visible = not behaviors.is_empty()
	for b in behaviors:
		_behavior_list.add_child(InfoWidgets.create_behavior_label(b))

	# Stats
	var vd: Dictionary = blueprint.get("visual_descriptor", {})
	_reveal_size.text = vd.get("size_category", "medium").to_upper()

	_reveal_cost.text = "%d tags" % tags.size()

	# Fade-in and start auto-fade timer
	_reveal_card.modulate.a = 0.0
	_fade_timer = REVEAL_TIMEOUT
	var tween := create_tween()
	tween.tween_property(_reveal_card, "modulate:a", 1.0, 0.25)


func _dismiss_reveal() -> void:
	Log.debug("CreationPanel: Reveal card dismissed")
	_is_showing_reveal = false
	_fade_timer = -1.0
	_reveal_card.modulate.a = 1.0
	_reveal_card.visible = false
	_creation_form.visible = true
	visible = false


func _auto_fade_out() -> void:
	var tween := create_tween()
	tween.tween_property(_reveal_card, "modulate:a", 0.0, FADE_DURATION)
	tween.tween_callback(func():
		if not _is_hovered:
			_dismiss_reveal()
	)


func _on_mouse_entered() -> void:
	_is_hovered = true
	if _is_showing_reveal and _reveal_card.modulate.a < 1.0:
		var tween := create_tween()
		tween.tween_property(_reveal_card, "modulate:a", 1.0, 0.1)
		_fade_timer = REVEAL_TIMEOUT


func _on_mouse_exited() -> void:
	_is_hovered = false
	if _is_showing_reveal:
		_fade_timer = REVEAL_TIMEOUT
