using Godot;

namespace Makeshift.Autoloads;

/// <summary>
/// Global game state manager. Owns the current <see cref="GameState"/>, the
/// current level index, and the debug mode flag. Drives scene transitions via
/// <see cref="SceneTree.ChangeSceneToFile"/>.
/// </summary>
public sealed partial class GameManager : Node
{
    public static GameManager Instance { get; private set; } = null!;

    public enum GameState
    {
        Menu = 0,
        Playing = 1,
        Paused = 2,
    }

    /// <summary>Level scene + display name. Keep order, keep strings.</summary>
    public sealed record LevelInfo(string Scene, string Name);

    public static readonly LevelInfo[] Levels =
    [
        new("res://scenes/levels/level_01.tscn", "Level 1: The Acid Moat"),
        new("res://scenes/levels/level_02.tscn", "Level 2: The Sentry"),
        new("res://scenes/levels/level_03.tscn", "Level 3: Reach the Top"),
        new("res://scenes/levels/level_sandbox.tscn", "Sandbox"),
    ];

    public const string GameScene = "res://scenes/game/game.tscn";

    public GameState CurrentState { get; private set; } = GameState.Menu;
    public int CurrentLevel { get; private set; }
    public bool DebugMode { get; private set; }

    public override void _EnterTree()
    {
        Instance = this;
    }

    public override void _Ready()
    {
        EventBus.Instance.LevelCompleted += OnLevelCompleted;
    }

    public override void _UnhandledInput(InputEvent @event)
    {
        if (@event.IsActionPressed("toggle_debug"))
        {
            DebugMode = !DebugMode;
            EventBus.Instance.EmitSignal(EventBus.SignalName.DebugToggled, DebugMode);
            Logger.Instance?.Debug($"GameManager: Debug mode {(DebugMode ? "ON" : "OFF")}");
        }
    }

    public void ChangeSceneToFile(string path)
    {
        Logger.Instance?.Info($"GameManager: Changing scene to {path}");
        GetTree().ChangeSceneToFile(path);
    }

    public void StartGame(int level = 0)
    {
        Logger.Instance?.Info($"GameManager: Starting game at level {level}");
        CurrentLevel = level;
        CurrentState = GameState.Playing;
        if (CurrentLevel < Levels.Length)
        {
            ChangeSceneToFile(GameScene);
        }
        else
        {
            Logger.Instance?.Warn($"GameManager: Level {level} out of range, returning to menu");
            ReturnToMenu();
        }
    }

    public void PauseGame()
    {
        Logger.Instance?.Info("GameManager: Game paused");
        CurrentState = GameState.Paused;
        GetTree().Paused = true;
    }

    public void ResumeGame()
    {
        Logger.Instance?.Info("GameManager: Game resumed");
        CurrentState = GameState.Playing;
        GetTree().Paused = false;
    }

    public void ReturnToMenu()
    {
        Logger.Instance?.Info($"GameManager: Returning to menu (from level {CurrentLevel})");
        GetTree().Paused = false;
        CurrentState = GameState.Menu;
        CurrentLevel = 0;
        ChangeSceneToFile("res://scenes/main_menu/main_menu.tscn");
    }

    public void RestartLevel()
    {
        Logger.Instance?.Info($"GameManager: Restarting level {CurrentLevel}");
        GetTree().Paused = false;
        CurrentState = GameState.Playing;
        ChangeSceneToFile(GameScene);
    }

    private void OnLevelCompleted(int levelId)
    {
        Logger.Instance?.Info($"GameManager: Level {levelId} completed, advancing to {levelId + 1}");
        CurrentLevel = levelId + 1;
        if (CurrentLevel < Levels.Length)
        {
            // Reload the game scene, which will load the next level.
            ChangeSceneToFile(GameScene);
        }
        else
        {
            Logger.Instance?.Info("GameManager: All levels completed!");
            ReturnToMenu();
        }
    }

}
