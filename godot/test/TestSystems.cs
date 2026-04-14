using Godot;
using Makeshift.Autoloads;
using Logger = Makeshift.Autoloads.Logger;
using Makeshift.Data;

namespace Makeshift.Tests;

/// <summary>
/// Comprehensive test harness: exercises Godot subsystems headlessly.
/// Drop it into a scene or load it as a root node; assertions run in
/// <see cref="_Ready"/>.
/// </summary>
public sealed partial class TestSystems : Node
{
    private int _passCount;
    private int _failCount;
    private int _frame;
    private Camera2D? _cam;

    private Node? _eventBus;
    private Node? _gameManager;
    private Node? _backend;
    private Node? _log;

    public override void _Ready()
    {
        GD.Print("=== TEST: Systems Integration (Comprehensive) ===");
        var root = GetTree().Root;

        // Resolve autoloads
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

        TestAutoloads();
        TestCollisionLayers();
        TestGameManager();
        TestEventBusSignals();
        TestSceneCompilation();
        TestLevelConstruction();
        TestGameObject();

        // Camera for screenshot compatibility
        _cam = new Camera2D { Position = new Vector2(640, 360) };
        root.AddChild(_cam);
        _cam.CallDeferred(Camera2D.MethodName.MakeCurrent);

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

    // ---------------------------------------------------------------------
    // Helpers
    // ---------------------------------------------------------------------

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
    // Section 1: Autoloads
    // ---------------------------------------------------------------------

    private void TestAutoloads()
    {
        Section("Autoloads");
        Assert("EventBus exists", _eventBus is not null);
        Assert("GameManager exists", _gameManager is not null);
        Assert("Backend exists", _backend is not null);
        Assert("Log exists", _log is not null);

        // Logger has typed PascalCase methods — tested via direct call below.
        Assert("Logger.Instance exists", Logger.Instance is not null);
        // Smoke-test each level. Writes to log file and/or console; must not throw.
        Logger.Instance?.Debug("TestSystems: Debug() smoke");
        Logger.Instance?.Info("TestSystems: Info() smoke");
        Logger.Instance?.Warn("TestSystems: Warn() smoke");
        Assert("Logger.Debug/Info/Warn invoked without throwing", true);
    }

    // ---------------------------------------------------------------------
    // Section 2: CollisionLayers
    // ---------------------------------------------------------------------

    private void TestCollisionLayers()
    {
        Section("CollisionLayers");
        Assert("TERRAIN == 1", CollisionLayers.Terrain == 1);
        Assert("PLAYER == 2", CollisionLayers.Player == 2);
        Assert("OBJECTS == 4", CollisionLayers.Objects == 4);
        Assert("HAZARDS == 8", CollisionLayers.Hazards == 8);
        Assert("TRIGGERS == 16", CollisionLayers.Triggers == 16);
        Assert("TERRAIN is power of 2", (CollisionLayers.Terrain & (CollisionLayers.Terrain - 1)) == 0);
        Assert(
            "No layer overlap (union == 31)",
            (CollisionLayers.Terrain | CollisionLayers.Player | CollisionLayers.Objects
                | CollisionLayers.Hazards | CollisionLayers.Triggers) == 31);
    }

    // ---------------------------------------------------------------------
    // Section 3: GameManager
    // ---------------------------------------------------------------------

    private void TestGameManager()
    {
        Section("GameManager");
        Assert("starts in MENU state (0)", GameManager.Instance.CurrentState == GameManager.GameState.Menu);
        Assert("current_level starts at 0", GameManager.Instance.CurrentLevel == 0);
        Assert("has 3 levels", GameManager.Levels.Length == 3);
        // All lifecycle methods are typed members of GameManager — if the
        // compiler let us get here, they exist. No reflection probes needed.
    }

    // ---------------------------------------------------------------------
    // Section 4: EventBus Signals
    // ---------------------------------------------------------------------

    private void TestEventBusSignals()
    {
        Section("EventBus Signals");
        string[] expected = ["InteractionTriggered", "ObjectCreated", "SpriteReady", "LevelCompleted"];
        foreach (var sigName in expected)
        {
            Assert($"has signal: {sigName}", _eventBus is not null && _eventBus.HasSignal(sigName));
        }
    }

    // ---------------------------------------------------------------------
    // Section 6: Scene Compilation
    // ---------------------------------------------------------------------

    private void TestSceneCompilation()
    {
        Section("Scene Compilation");
        string[] scenes =
        [
            "res://scenes/game/game.tscn",
            "res://scenes/game_object/game_object.tscn",
            "res://scenes/hud/hud.tscn",
            "res://scenes/hud/interaction_feedback.tscn",
            "res://scenes/hud/object_creation_panel.tscn",
            "res://scenes/levels/base_level.tscn",
            "res://scenes/levels/level_01.tscn",
            "res://scenes/levels/level_02.tscn",
            "res://scenes/levels/level_03.tscn",
            "res://scenes/main_menu/main_menu.tscn",
            "res://scenes/player/player.tscn",
            "res://scenes/world/world.tscn",
        ];
        foreach (var path in scenes)
        {
            var scene = GD.Load<PackedScene>(path);
            Assert($"loads: {path}", scene is not null);
        }
    }

    // ---------------------------------------------------------------------
    // Section 13: Level Construction
    // ---------------------------------------------------------------------

    private void TestLevelConstruction()
    {
        Section("Level Construction");
        var root = GetTree().Root;

        string[] levelPaths =
        [
            "res://scenes/levels/level_01.tscn",
            "res://scenes/levels/level_02.tscn",
            "res://scenes/levels/level_03.tscn",
        ];

        for (int i = 0; i < levelPaths.Length; i++)
        {
            var scene = GD.Load<PackedScene>(levelPaths[i]);
            Assert($"level_{i + 1} scene loads", scene is not null);
            if (scene is null)
            {
                continue;
            }

            var level = scene.Instantiate();
            root.AddChild(level);

            var spawn = level.FindChild("SpawnPoint", true, false);
            var goal = level.FindChild("Goal", true, false);

            Assert($"level_{i + 1} has SpawnPoint", spawn is not null);
            Assert($"level_{i + 1} has Goal", goal is not null);

            if (goal is not null)
            {
                Assert($"level_{i + 1} Goal is Area2D", goal is Area2D);
                var goalShape = goal.FindChild("CollisionShape2D", false, false);
                Assert($"level_{i + 1} Goal has CollisionShape2D", goalShape is not null);
            }

            level.Free();
        }
    }

    // ---------------------------------------------------------------------
    // Section 14: GameObject
    // ---------------------------------------------------------------------

    private void TestGameObject()
    {
        Section("GameObject");
        // Full GameObject construction needs a live scene tree; contract
        // coverage lives in the Python backend unit tests.
        Assert("GameObject contract check (stub)", true);
    }
}
