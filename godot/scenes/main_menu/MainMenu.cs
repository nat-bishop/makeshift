using Godot;
using Makeshift.Autoloads;
using Logger = Makeshift.Autoloads.Logger;

namespace Makeshift.Scenes.MainMenu;

/// <summary>
/// Main menu controller. Drives new-game / continue / quit flow and delegates
/// to <see cref="Backend.Instance"/> for session lifecycle.
/// </summary>
public sealed partial class MainMenu : Control
{
    private Button _newGameButton = null!;
    private Button _continueButton = null!;
    private Button _quitButton = null!;

    private VBoxContainer? _levelSelectContainer;

    public override void _Ready()
    {
        _newGameButton = GetNode<Button>("%NewGameButton");
        _continueButton = GetNode<Button>("%ContinueButton");
        _quitButton = GetNode<Button>("%QuitButton");

        var hasSession = !string.IsNullOrEmpty(Backend.Instance.SessionId);
        Logger.Instance.Info($"MainMenu: Initialized (has_session={hasSession})");

        _newGameButton.Pressed += OnNewGamePressed;
        _continueButton.Pressed += OnContinuePressed;
        _quitButton.Pressed += OnQuitPressed;

        // Disable Continue if no saved session
        _continueButton.Disabled = !hasSession;

        BuildLevelSelect();
    }

    private void BuildLevelSelect()
    {
        _levelSelectContainer = new VBoxContainer
        {
            Visible = false,
        };
        _levelSelectContainer.AddThemeConstantOverride("separation", 8);

        // Insert after NewGameButton in the parent VBox
        var vbox = (VBoxContainer)_newGameButton.GetParent();
        vbox.AddChild(_levelSelectContainer);
        vbox.MoveChild(_levelSelectContainer, _newGameButton.GetIndex() + 1);

        for (int i = 0; i < GameManager.Levels.Length; i++)
        {
            int levelIndex = i;
            var btn = new Button
            {
                Text = GameManager.Levels[i].Name,
                CustomMinimumSize = new Vector2(0, 36),
            };
            btn.Pressed += () => OnLevelSelected(levelIndex);
            _levelSelectContainer.AddChild(btn);
        }
    }

    private void OnNewGamePressed()
    {
        if (_levelSelectContainer is not null)
        {
            _levelSelectContainer.Visible = !_levelSelectContainer.Visible;
        }
    }

    private async void OnLevelSelected(int level)
    {
        Logger.Instance.Info($"MainMenu: Level {level} selected");
        _newGameButton.Disabled = true;
        _continueButton.Disabled = true;

        var result = await Backend.Instance.CreateSessionAsync();
        if (result.ContainsKey("error") && result["error"].AsBool())
        {
            Logger.Instance.Warn("MainMenu: Session creation failed, starting in offline mode");
        }

        GameManager.Instance.StartGame(level);
    }

    private async void OnContinuePressed()
    {
        var sessionId = Backend.Instance.SessionId;
        if (string.IsNullOrEmpty(sessionId))
        {
            return;
        }

        Logger.Instance.Info($"MainMenu: Continue requested for session {sessionId}");
        _newGameButton.Disabled = true;
        _continueButton.Disabled = true;

        var result = await Backend.Instance.RestoreSessionAsync(sessionId);
        if (result.ContainsKey("error") && result["error"].AsBool())
        {
            Logger.Instance.Warn("MainMenu: Failed to restore session");
            _newGameButton.Disabled = false;
            _continueButton.Disabled = false;
            return;
        }

        GameManager.Instance.StartGame(GameManager.Instance.CurrentLevel);
    }

    private void OnQuitPressed()
    {
        Logger.Instance.Info("MainMenu: Quit pressed");
        GetTree().Quit();
    }
}
