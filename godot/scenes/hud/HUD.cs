using Godot;
using Makeshift.Autoloads;
using Makeshift.UI;

namespace Makeshift.Scenes.Hud;

/// <summary>
/// Top-level HUD canvas: objective label, action hint, object-creation panel,
/// pause + game-over overlays, health bar and damage flash.
/// </summary>
public sealed partial class HUD : CanvasLayer
{
    private ObjectCreationPanel _objectCreationPanel = null!;
    private Label _objectiveLabel = null!;
    private Label _actionHint = null!;

    private bool _placementActive;
    private Control _pauseMenu = null!;
    private Control _gameOverPanel = null!;
    private Label _gameOverTitle = null!;
    private ProgressBar _healthBar = null!;
    private Label _healthLabel = null!;
    private ColorRect _damageFlash = null!;

    public override void _Ready()
    {
        Layer = 10;
        ProcessMode = ProcessModeEnum.Always;

        _objectCreationPanel = GetNode<ObjectCreationPanel>("%ObjectCreationPanel");
        _objectiveLabel = GetNode<Label>("%ObjectiveLabel");
        _actionHint = GetNode<Label>("%ActionHint");

        _objectCreationPanel.Visible = false;
        UpdateActionHint();

        EventBus.Instance.PlacementStarted += OnPlacementStarted;
        EventBus.Instance.PlacementEnded += OnPlacementEnded;
        EventBus.Instance.DebugToggled += OnDebugToggled;
        EventBus.Instance.PlayerDied += OnPlayerDied;
        EventBus.Instance.PlayerDamaged += OnPlayerDamaged;
        EventBus.Instance.PlayerHealed += OnPlayerHealed;

        _pauseMenu = BuildOverlay("Paused", new Color(0, 0, 0, 0.5f),
        [
            ("Resume", Callable.From(HidePauseMenu)),
            ("Main Menu", Callable.From(OnMainMenuPressed)),
        ], out var pauseTitle);
        _ = pauseTitle;

        _gameOverPanel = BuildOverlay("Game Over", new Color(0.1f, 0, 0, 0.6f),
        [
            ("Retry", Callable.From(OnRetryPressed)),
            ("Main Menu", Callable.From(OnMainMenuPressed)),
        ], out _gameOverTitle);

        BuildHealthBar();
        BuildDamageFlash();
    }

    public override void _Input(InputEvent @event)
    {
        if (@event.IsActionPressed("create_object"))
        {
            if (_gameOverPanel.Visible || _pauseMenu.Visible)
            {
                GetViewport().SetInputAsHandled();
                return;
            }
            if (_placementActive)
            {
                GetViewport().SetInputAsHandled();
                return;
            }
            if (_objectCreationPanel.Visible && _objectCreationPanel.IsBusy())
            {
                GetViewport().SetInputAsHandled();
                return;
            }
            _objectCreationPanel.Visible = !_objectCreationPanel.Visible;
            Logger.Instance.Debug($"HUD: Creation panel {(_objectCreationPanel.Visible ? "opened" : "closed")}");
            if (_objectCreationPanel.Visible)
            {
                GameManager.Instance.PauseGame();
                _objectCreationPanel.FocusInput();
            }
            else
            {
                GameManager.Instance.ResumeGame();
            }
            GetViewport().SetInputAsHandled();
        }
    }

    public override void _UnhandledInput(InputEvent @event)
    {
        if (@event.IsActionPressed("ui_cancel"))
        {
            if (_placementActive)
            {
                return; // Game handles Escape during placement
            }
            if (_gameOverPanel.Visible)
            {
                GetViewport().SetInputAsHandled();
                return;
            }
            if (_objectCreationPanel.Visible)
            {
                _objectCreationPanel.Visible = false;
                GameManager.Instance.ResumeGame();
                GetViewport().SetInputAsHandled();
                return;
            }
            if (_pauseMenu.Visible)
            {
                HidePauseMenu();
                GetViewport().SetInputAsHandled();
                return;
            }
            ShowPauseMenu();
            GetViewport().SetInputAsHandled();
        }
    }

    public void SetObjective(string text)
    {
        _objectiveLabel.Text = text;
    }

    private Control BuildOverlay(
        string titleText,
        Color dimColor,
        (string Text, Callable Callback)[] buttons,
        out Label titleLabel)
    {
        var root = new Control
        {
            Visible = false,
            MouseFilter = Control.MouseFilterEnum.Stop,
        };
        root.SetAnchorsPreset(Control.LayoutPreset.FullRect);

        var dim = new ColorRect { Color = dimColor };
        dim.SetAnchorsPreset(Control.LayoutPreset.FullRect);
        root.AddChild(dim);

        var center = new CenterContainer();
        center.SetAnchorsPreset(Control.LayoutPreset.FullRect);
        root.AddChild(center);

        var vbox = new VBoxContainer();
        vbox.AddThemeConstantOverride("separation", 16);
        center.AddChild(vbox);

        titleLabel = new Label
        {
            Text = titleText,
            HorizontalAlignment = HorizontalAlignment.Center,
        };
        titleLabel.AddThemeFontSizeOverride("font_size", 32);
        vbox.AddChild(titleLabel);

        foreach (var (btnText, callback) in buttons)
        {
            var btn = new Button
            {
                Text = btnText,
                CustomMinimumSize = new Vector2(200, 40),
            };
            btn.Pressed += () => callback.Call();
            vbox.AddChild(btn);
        }

        AddChild(root);
        return root;
    }

    private void BuildHealthBar()
    {
        var container = new HBoxContainer
        {
            GrowHorizontal = Control.GrowDirection.Begin,
            Position = new Vector2(-170, 16),
        };
        container.SetAnchorsPreset(Control.LayoutPreset.TopRight);
        container.AddThemeConstantOverride("separation", 6);

        _healthBar = new ProgressBar
        {
            CustomMinimumSize = new Vector2(150, 24),
            MaxValue = 100,
            Value = 100,
            ShowPercentage = false,
        };

        var style = InfoWidgets.MakeStylebox(new Color(0.2f, 0.2f, 0.2f, 0.8f), 4, 0, 0);
        _healthBar.AddThemeStyleboxOverride("background", style);

        var fill = InfoWidgets.MakeStylebox(new Color(0.3f, 0.9f, 0.3f), 4, 0, 0);
        _healthBar.AddThemeStyleboxOverride("fill", fill);
        container.AddChild(_healthBar);

        _healthLabel = new Label { Text = "100/100" };
        _healthLabel.AddThemeFontSizeOverride("font_size", 14);
        container.AddChild(_healthLabel);

        AddChild(container);
    }

    private void BuildDamageFlash()
    {
        _damageFlash = new ColorRect
        {
            Color = new Color(1.0f, 0.0f, 0.0f, 0.0f),
            MouseFilter = Control.MouseFilterEnum.Ignore,
        };
        _damageFlash.SetAnchorsPreset(Control.LayoutPreset.FullRect);
        AddChild(_damageFlash);
    }

    private void UpdateHealthBar(int current, int maximum)
    {
        Logger.Instance.Debug($"HUD: Health bar updated {current}/{maximum}");
        _healthBar.MaxValue = maximum;
        _healthBar.Value = current;
        _healthLabel.Text = $"{current}/{maximum}";

        var ratio = maximum > 0 ? (float)current / maximum : 0.0f;
        if (_healthBar.GetThemeStylebox("fill") is StyleBoxFlat fill)
        {
            if (ratio > 0.5f)
            {
                fill.BgColor = new Color(0.3f, 0.9f, 0.3f);
            }
            else if (ratio > 0.25f)
            {
                fill.BgColor = new Color(0.9f, 0.9f, 0.2f);
            }
            else
            {
                fill.BgColor = new Color(0.9f, 0.2f, 0.2f);
            }
        }
    }

    private void FlashDamageOverlay()
    {
        _damageFlash.Color = new Color(1.0f, 0.0f, 0.0f, 0.25f);
        var tween = CreateTween();
        tween.TweenProperty(_damageFlash, "color:a", 0.0f, 0.4f);
    }

    private void OnPlayerDamaged(float amount, int current, int maximum)
    {
        UpdateHealthBar(current, maximum);
        FlashDamageOverlay();
    }

    private void OnPlayerHealed(float amount, int current, int maximum)
    {
        UpdateHealthBar(current, maximum);
    }

    private void ShowPauseMenu()
    {
        Logger.Instance.Debug("HUD: Pause menu shown");
        _pauseMenu.Visible = true;
        GameManager.Instance.PauseGame();
    }

    private void HidePauseMenu()
    {
        Logger.Instance.Debug("HUD: Pause menu hidden");
        _pauseMenu.Visible = false;
        GameManager.Instance.ResumeGame();
    }

    private void OnMainMenuPressed()
    {
        Logger.Instance.Info("HUD: Returning to main menu");
        _pauseMenu.Visible = false;
        _gameOverPanel.Visible = false;
        GameManager.Instance.ReturnToMenu();
    }

    private void OnRetryPressed()
    {
        Logger.Instance.Info("HUD: Retry pressed");
        _gameOverPanel.Visible = false;
        GameManager.Instance.RestartLevel();
    }

    private void OnPlacementStarted()
    {
        _placementActive = true;
        _objectCreationPanel.Visible = false;
        UpdateActionHint();
    }

    private void OnPlacementEnded()
    {
        _placementActive = false;
        UpdateActionHint();
    }

    private void OnDebugToggled(bool enabled)
    {
        _ = enabled;
    }

    private void OnPlayerDied()
    {
        if (_healthBar.Value > 0)
        {
            _gameOverTitle.Text = "You fell!";
            Logger.Instance.Info("HUD: Game over — player fell");
        }
        else
        {
            _gameOverTitle.Text = "You died!";
            Logger.Instance.Info("HUD: Game over — player died (health depleted)");
        }
        _gameOverPanel.Visible = true;
        GameManager.Instance.PauseGame();
    }

    private void UpdateActionHint()
    {
        _actionHint.Text = _placementActive
            ? "Click: Place  |  Esc: Cancel"
            : "Tab: Create  |  E: Kick  |  Esc: Menu  |  F3: Debug";
    }

    public override void _ExitTree()
    {
        if (EventBus.Instance is null)
        {
            return;
        }
        EventBus.Instance.PlacementStarted -= OnPlacementStarted;
        EventBus.Instance.PlacementEnded -= OnPlacementEnded;
        EventBus.Instance.DebugToggled -= OnDebugToggled;
        EventBus.Instance.PlayerDied -= OnPlayerDied;
        EventBus.Instance.PlayerDamaged -= OnPlayerDamaged;
        EventBus.Instance.PlayerHealed -= OnPlayerHealed;
    }
}
