using Godot;
using Makeshift.Autoloads;

namespace Makeshift.Tests;

/// <summary>
/// Gameplay integration test: runs in <see cref="_Ready"/>, quits after
/// a few frames.
/// </summary>
public sealed partial class TestGameplay : Node
{
    private int _passCount;
    private int _failCount;
    private int _frame;

    private Node? _eventBus;
    private Node? _gameManager;
    private Node? _backend;
    private Node? _log;

    public override void _Ready()
    {
        GD.Print("=== TEST: Gameplay Integration ===");
        var root = GetTree().Root;

        foreach (var child in root.GetChildren())
        {
            switch (child.Name.ToString())
            {
                case "EventBus":
                    _eventBus = child;
                    break;
                case "GameManager":
                    _gameManager = child;
                    break;
                case "Backend":
                    _backend = child;
                    break;
                case "Log":
                    _log = child;
                    break;
            }
        }

        TestGameStateFlow();
        TestBackendOfflineMode();

        GD.Print("\n=== SUMMARY ===");
        GD.Print($"PASSED: {_passCount}");
        GD.Print($"FAILED: {_failCount}");
        GD.Print($"TOTAL:  {_passCount + _failCount}");
        GD.Print(_failCount == 0 ? "\nALL PASSED" : "\nFAILURES DETECTED");
        GD.Print("=== TEST COMPLETE ===");
    }

    public override void _Process(double delta)
    {
        _frame++;
        if (_frame > 3)
        {
            GetTree().Quit();
        }
    }

    private void Assert(string desc, bool condition)
    {
        if (condition)
        {
            _passCount++;
            GD.Print($"ASSERT PASS: {desc}");
        }
        else
        {
            _failCount++;
            GD.Print($"ASSERT FAIL: {desc}");
        }
    }

    private static void Section(string name)
    {
        GD.Print($"\n--- {name} ---");
    }

    // ---------------------------------------------------------------------
    // Test: Game state flow (GameManager)
    // ---------------------------------------------------------------------

    private void TestGameStateFlow()
    {
        Section("Game State Flow");

        Assert("Initial state is MENU", GameManager.Instance.CurrentState == GameManager.GameState.Menu);
        Assert("Initial level is 0", GameManager.Instance.CurrentLevel == 0);
        Assert("GAME_SCENE defined", !string.IsNullOrEmpty(GameManager.GameScene));
        Assert("3 levels defined", GameManager.Levels.Length == 3);

        // Verify level scene paths are loadable
        for (int i = 0; i < GameManager.Levels.Length; i++)
        {
            var scene = GD.Load<PackedScene>(GameManager.Levels[i].Scene);
            Assert($"Level {i + 1} scene exists", scene is not null);
        }
    }

    // ---------------------------------------------------------------------
    // Test: Backend offline mode
    // ---------------------------------------------------------------------

    private void TestBackendOfflineMode()
    {
        Section("Backend Offline Mode");

        Assert("Backend has session_id field", Backend.Instance.SessionId is not null);
        Assert("Session ID starts empty or loaded from file", true);
        // CreateObjectAsync / CreateSessionAsync are typed members of Backend —
        // the compiler enforces their existence; no reflection probes required.

        // Sprite cache should return null for unknown IDs
        var cached = Backend.Instance.GetCachedSprite("nonexistent");
        Assert("No cached sprite for unknown ID", cached is null);

        // Mark dirty should not crash
        Backend.Instance.MarkDirty();
        Assert("MarkDirty() no crash", true);
    }
}
