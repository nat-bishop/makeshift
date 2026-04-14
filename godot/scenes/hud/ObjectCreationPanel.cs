using Godot;
using Makeshift.Autoloads;
using Makeshift.Models;
using Makeshift.UI;

namespace Makeshift.Scenes.Hud;

/// <summary>
/// Top-of-screen object creation panel. Issues a creation request via
/// <see cref="Backend.CreateObjectAsync(string)"/>, shows a "creating..."
/// status, then reveals a card with the blueprint tags, behaviors and stats
/// before auto-fading.
/// </summary>
public sealed partial class ObjectCreationPanel : PanelContainer
{
    private const float RevealTimeout = 10.0f;
    private const float FadeDuration = 0.5f;

    private LineEdit _descriptionInput = null!;
    private Button _createButton = null!;
    private Label _statusLabel = null!;
    private VBoxContainer _creationForm = null!;
    private VBoxContainer _revealCard = null!;
    private Label _revealName = null!;
    private HFlowContainer _revealTags = null!;
    private Label _revealSize = null!;
    private Label _revealCost = null!;
    private Button _closeButton = null!;
    private VBoxContainer _behaviorSection = null!;
    private VBoxContainer _behaviorList = null!;

    private bool _isCreating;
    private bool _isShowingReveal;
    private bool _isHovered;
    private float _fadeTimer = -1.0f;

    public override void _Ready()
    {
        _descriptionInput = GetNode<LineEdit>("%DescriptionInput");
        _createButton = GetNode<Button>("%CreateButton");
        _statusLabel = GetNode<Label>("%StatusLabel");
        _creationForm = GetNode<VBoxContainer>("%CreationForm");
        _revealCard = GetNode<VBoxContainer>("%RevealCard");
        _revealName = GetNode<Label>("%RevealName");
        _revealTags = GetNode<HFlowContainer>("%RevealTags");
        _revealSize = GetNode<Label>("%RevealSize");
        _revealCost = GetNode<Label>("%RevealCost");
        _closeButton = GetNode<Button>("%CloseButton");
        _behaviorSection = GetNode<VBoxContainer>("%BehaviorSection");
        _behaviorList = GetNode<VBoxContainer>("%BehaviorList");

        var style = InfoWidgets.MakeStylebox(
            new Color(0.12f, 0.12f, 0.15f, 0.95f), 8, 16, 12, 1, new Color(0.4f, 0.4f, 0.5f, 0.8f));
        AddThemeStyleboxOverride("panel", style);

        _descriptionInput.MaxLength = 500;
        _createButton.Pressed += OnCreatePressed;
        _descriptionInput.TextSubmitted += OnTextSubmitted;
        _closeButton.Pressed += DismissReveal;
        _statusLabel.Text = "";
        _revealCard.Visible = false;

        MouseEntered += OnMouseEntered;
        MouseExited += OnMouseExited;
    }

    public void FocusInput()
    {
        // Reset reveal state if panel was reopened while reveal was active.
        if (_isShowingReveal)
        {
            _isShowingReveal = false;
            _fadeTimer = -1.0f;
            _revealCard.Modulate = new Color(_revealCard.Modulate, 1.0f);
            _revealCard.Visible = false;
            _creationForm.Visible = true;
        }
        _descriptionInput.CallDeferred(Control.MethodName.GrabFocus);
    }

    public override void _Process(double delta)
    {
        if (!_isShowingReveal || _fadeTimer < 0.0f || _isHovered)
        {
            return;
        }
        _fadeTimer -= (float)delta;
        if (_fadeTimer <= 0.0f)
        {
            _fadeTimer = -1.0f;
            AutoFadeOut();
        }
    }

    public bool IsBusy() => _isCreating;

    private void OnCreatePressed() => _ = SubmitAsync();

    private void OnTextSubmitted(string _text) => _ = SubmitAsync();

    private async System.Threading.Tasks.Task SubmitAsync()
    {
        if (_isCreating)
        {
            return;
        }

        var description = _descriptionInput.Text.StripEdges();
        if (string.IsNullOrEmpty(description))
        {
            _statusLabel.Text = "Enter a description first.";
            _statusLabel.AddThemeColorOverride("font_color", new Color(1.0f, 0.6f, 0.3f));
            return;
        }

        Logger.Instance.Info($"CreationPanel: Submitting '{description}' (len={description.Length})");
        _isCreating = true;
        _createButton.Disabled = true;
        _statusLabel.Text = "Creating...";
        _statusLabel.AddThemeColorOverride("font_color", new Color(0.7f, 0.7f, 0.7f));
        EventBus.Instance.EmitSignal(EventBus.SignalName.CreationRequested);

        var result = await Backend.Instance.CreateObjectAsync(description);

        _isCreating = false;
        _createButton.Disabled = false;

        if (result.GetBoolOrDefault("error"))
        {
            var errorMsg = result.GetStringOrDefault("message", "Creation failed. Try again.");
            Logger.Instance.Warn($"CreationPanel: Creation failed: {errorMsg}");
            _statusLabel.Text = errorMsg;
            _statusLabel.AddThemeColorOverride("font_color", new Color(1.0f, 0.3f, 0.3f));
            EventBus.Instance.EmitSignal(EventBus.SignalName.CreationFailed);
            return;
        }

        _statusLabel.Text = "";
        _descriptionInput.Text = "";
        var blueprint = result.ContainsKey("blueprint")
            ? (Godot.Collections.Dictionary)result["blueprint"]
            : result;
        var name = blueprint.GetStringOrDefault("name", "?");
        Logger.Instance.Info($"CreationPanel: Created '{name}'");
        ShowReveal(blueprint);
    }

    private void ShowReveal(Godot.Collections.Dictionary blueprint)
    {
        var name = blueprint.GetStringOrDefault("name", "?");
        Logger.Instance.Debug($"CreationPanel: Showing reveal card for '{name}'");
        _isShowingReveal = true;
        _creationForm.Visible = false;
        _revealCard.Modulate = new Color(_revealCard.Modulate, 1.0f);
        _revealCard.Visible = true;

        _revealName.Text = blueprint.GetStringOrDefault("name", "Unknown");

        // Tags
        foreach (var child in _revealTags.GetChildren())
        {
            child.QueueFree();
        }
        var tagsVariant = blueprint.GetValueOrDefault("tags", new Godot.Collections.Array());
        var tags = tagsVariant.AsGodotArray();
        foreach (var tag in tags)
        {
            _revealTags.AddChild(InfoWidgets.CreateTagBadge(tag.ToString() ?? ""));
        }

        // Behaviors
        foreach (var child in _behaviorList.GetChildren())
        {
            child.QueueFree();
        }
        var behaviorsVariant = blueprint.GetValueOrDefault("behaviors", new Godot.Collections.Array());
        var behaviors = behaviorsVariant.AsGodotArray();
        _behaviorSection.Visible = behaviors.Count > 0;
        foreach (var entry in behaviors)
        {
            if (entry.VariantType == Variant.Type.Dictionary)
            {
                var typed = BehaviorEntryMarshal.FromGodotDictionary(entry.AsGodotDictionary());
                _behaviorList.AddChild(InfoWidgets.CreateBehaviorLabel(typed));
            }
        }

        // Stats
        var vdVariant = blueprint.GetValueOrDefault("visual_descriptor", new Godot.Collections.Dictionary());
        var vd = vdVariant.AsGodotDictionary();
        var sizeCategory = vd.GetStringOrDefault("size_category", "medium");
        _revealSize.Text = sizeCategory.ToUpperInvariant();

        _revealCost.Text = $"{tags.Count} tags";

        // Fade-in and start auto-fade timer
        _revealCard.Modulate = new Color(_revealCard.Modulate, 0.0f);
        _fadeTimer = RevealTimeout;
        var tween = CreateTween();
        tween.TweenProperty(_revealCard, "modulate:a", 1.0f, 0.25f);
    }

    private void DismissReveal()
    {
        Logger.Instance.Debug("CreationPanel: Reveal card dismissed");
        _isShowingReveal = false;
        _fadeTimer = -1.0f;
        _revealCard.Modulate = new Color(_revealCard.Modulate, 1.0f);
        _revealCard.Visible = false;
        _creationForm.Visible = true;
        Visible = false;
    }

    private void AutoFadeOut()
    {
        var tween = CreateTween();
        tween.TweenProperty(_revealCard, "modulate:a", 0.0f, FadeDuration);
        tween.TweenCallback(Callable.From(() =>
        {
            if (!_isHovered)
            {
                DismissReveal();
            }
        }));
    }

    private void OnMouseEntered()
    {
        _isHovered = true;
        if (_isShowingReveal && _revealCard.Modulate.A < 1.0f)
        {
            var tween = CreateTween();
            tween.TweenProperty(_revealCard, "modulate:a", 1.0f, 0.1f);
            _fadeTimer = RevealTimeout;
        }
    }

    private void OnMouseExited()
    {
        _isHovered = false;
        if (_isShowingReveal)
        {
            _fadeTimer = RevealTimeout;
        }
    }
}
