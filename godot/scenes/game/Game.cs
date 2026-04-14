using Godot;
using Makeshift.Autoloads;
using Makeshift.Scenes.Effects;
using Makeshift.Scenes.Hud;
using Makeshift.Scenes.Levels;
using Makeshift.Scenes.Player;
using Makeshift.Systems;

namespace Makeshift.Scenes.Game;

/// <summary>
/// Root in-game scene: loads the active level into the <see cref="World"/>,
/// positions the player at the spawn marker, drives the object-creation
/// materialize effect and the mouse-follow placement ghost. Subscribes to
/// <see cref="EventBus"/> for creation / sprite / level-completion flow.
/// </summary>
[GlobalClass]
public partial class Game : Node2D
{
    private static readonly Vector2 SpawnOffset = new(80, -32);

    private World.World _world = null!;
    private HUD _hud = null!;
    private Player.Player _player = null!;

    private Node2D? _currentLevelScene;
    private MaterializeEffect? _materializeEffect;
    private Godot.Collections.Dictionary _pendingBlueprint = new();
    private bool _placementActive;
    private Node2D? _placementGhost;

    public override void _Ready()
    {
        SetProcess(false);
        _world = GetNode<World.World>("World");
        _hud = GetNode<HUD>("HUD");
        _player = GetNode<Player.Player>("Player");

        EventBus.Instance.LevelCompleted += OnLevelCompleted;
        EventBus.Instance.ObjectCreated += OnObjectCreated;
        EventBus.Instance.CreationRequested += OnCreationRequested;
        EventBus.Instance.CreationFailed += OnCreationFailed;
        EventBus.Instance.SpriteReady += OnSpriteReady;
        EventBus.Instance.SpriteFailed += OnSpriteFailed;

        LoadCurrentLevel();
    }

    public override void _Process(double delta)
    {
        var mousePos = GetGlobalMousePosition();
        if (_materializeEffect is not null && IsInstanceValid(_materializeEffect))
        {
            _materializeEffect.GlobalPosition = mousePos;
        }
        if (_placementActive && _placementGhost is not null && IsInstanceValid(_placementGhost))
        {
            _placementGhost.GlobalPosition = mousePos;
        }
    }

    public override void _UnhandledInput(InputEvent @event)
    {
        if (!_placementActive)
        {
            return;
        }

        if (@event is InputEventMouseButton mb &&
            mb.ButtonIndex == MouseButton.Left && mb.Pressed)
        {
            ConfirmPlacement();
            GetViewport().SetInputAsHandled();
        }
        else if (@event.IsActionPressed("ui_cancel"))
        {
            CancelPlacement();
            GetViewport().SetInputAsHandled();
        }
    }

    public override void _ExitTree()
    {
        if (EventBus.Instance is not null)
        {
            EventBus.Instance.LevelCompleted -= OnLevelCompleted;
            EventBus.Instance.ObjectCreated -= OnObjectCreated;
            EventBus.Instance.CreationRequested -= OnCreationRequested;
            EventBus.Instance.CreationFailed -= OnCreationFailed;
            EventBus.Instance.SpriteReady -= OnSpriteReady;
            EventBus.Instance.SpriteFailed -= OnSpriteFailed;
        }
    }

    // --- Level loading ------------------------------------------------------

    private void LoadCurrentLevel()
    {
        int levelIndex = GameManager.Instance.CurrentLevel;
        if (levelIndex >= GameManager.Levels.Length)
        {
            return;
        }

        var levelPath = GameManager.Levels[levelIndex].Scene;
        var levelScene = GD.Load<PackedScene>(levelPath);
        if (levelScene is null)
        {
            Logger.Instance?.Error($"Game: Failed to load level: {levelPath}");
            return;
        }

        _currentLevelScene = (Node2D)levelScene.Instantiate();
        _world.AddChild(_currentLevelScene);
        _world.MoveChild(_currentLevelScene, 0); // Behind objects
        Logger.Instance?.Info($"Game: Loaded level {levelIndex} ({levelPath})");

        // Position player at spawn point
        var spawnPoint = _currentLevelScene.FindChild("SpawnPoint", recursive: true, owned: false) as Marker2D;
        if (spawnPoint is not null)
        {
            _player.GlobalPosition = spawnPoint.GlobalPosition;
        }
        else
        {
            _player.GlobalPosition = new Vector2(128, 0);
        }

        // Set objective text in HUD
        if (_currentLevelScene is BaseLevel baseLevel)
        {
            _hud.SetObjective(baseLevel.objective_text);
        }
    }

    private string GetPendingId()
    {
        return _pendingBlueprint.TryGetValue("id", out var v) ? v.AsString() : "";
    }

    // --- Signal handlers ----------------------------------------------------

    private void OnLevelCompleted(int levelId)
    {
        // GameManager handles level progression via its own listener.
        _ = levelId;
    }

    private void OnCreationRequested()
    {
        ClearPending();
        var spawnPos = GetGlobalMousePosition();
        var effect = new MaterializeEffect
        {
            GlobalPosition = spawnPos,
        };
        _world.AddChild(effect);
        _materializeEffect = effect;
        SetProcess(true);
        Logger.Instance?.Debug($"Game: Materialization effect started at {spawnPos}");
    }

    private void OnObjectCreated(Godot.Collections.Dictionary blueprint)
    {
        _pendingBlueprint = blueprint;
        var pendingId = GetPendingId();

        // Sprite may already be cached (arrived via WebSocket before HTTP response).
        if (!string.IsNullOrEmpty(pendingId) &&
            Backend.Instance.GetCachedSprite(pendingId) is not null)
        {
            BeginPlacement();
        }
        else
        {
            var name = blueprint.TryGetValue("name", out var nV) ? nV.AsString() : "?";
            Logger.Instance?.Debug($"Game: Waiting for sprite for '{name}'");
        }
    }

    private void OnSpriteReady(string id, Texture2D texture)
    {
        if (id != GetPendingId() || string.IsNullOrEmpty(GetPendingId()))
        {
            return;
        }

        if (_placementActive && _placementGhost is not null && IsInstanceValid(_placementGhost))
        {
            var sprite = _placementGhost.GetNode<Sprite2D>("Sprite2D");
            sprite.Texture = texture;
            int heightCm = ExtractHeightCm(_pendingBlueprint);
            float worldSize = PhysicsComposer.WorldSpriteSize(heightCm);
            sprite.Scale = Vector2.One * (worldSize / texture.GetWidth());
        }
        else
        {
            BeginPlacement();
        }
    }

    private void OnSpriteFailed(string id)
    {
        if (id != GetPendingId())
        {
            return;
        }
        var name = _pendingBlueprint.TryGetValue("name", out var nV) ? nV.AsString() : "?";
        Logger.Instance?.Warn($"Game: Sprite failed for '{name}', placing with placeholder");
        BeginPlacement();
    }

    private void OnCreationFailed()
    {
        if (_materializeEffect is not null && IsInstanceValid(_materializeEffect))
        {
            _materializeEffect.Resolve(scatter: true);
            _materializeEffect = null;
            Logger.Instance?.Debug("Game: Materialization effect cancelled (creation failed)");
        }
        _pendingBlueprint = new();
        SetProcess(false);
    }

    // --- Placement flow ------------------------------------------------------

    private void BeginPlacement()
    {
        GameManager.Instance.ResumeGame();
        var ghostStartPos = _player.GlobalPosition + SpawnOffset;
        if (_materializeEffect is not null && IsInstanceValid(_materializeEffect))
        {
            ghostStartPos = _materializeEffect.GlobalPosition;
            _materializeEffect.Resolve();
            _materializeEffect = null;
        }

        _placementGhost = CreatePlacementGhost();
        _placementGhost.GlobalPosition = ghostStartPos;
        _world.AddChild(_placementGhost);
        _placementActive = true;
        SetProcess(true);
        EventBus.Instance.EmitSignal(EventBus.SignalName.PlacementStarted);

        var name = _pendingBlueprint.TryGetValue("name", out var nV) ? nV.AsString() : "?";
        Logger.Instance?.Debug($"Game: Placement mode started for '{name}'");
    }

    private Node2D CreatePlacementGhost()
    {
        var ghost = new Node2D();
        var sprite = new Sprite2D { Name = "Sprite2D" };
        ghost.AddChild(sprite);

        var pendingId = GetPendingId();
        Texture2D? cached = !string.IsNullOrEmpty(pendingId)
            ? Backend.Instance.GetCachedSprite(pendingId)
            : null;

        if (cached is not null)
        {
            sprite.Texture = cached;
            int heightCm = ExtractHeightCm(_pendingBlueprint);
            float worldSize = PhysicsComposer.WorldSpriteSize(heightCm);
            sprite.Scale = Vector2.One * (worldSize / cached.GetWidth());
        }
        else
        {
            int heightCm = ExtractHeightCm(_pendingBlueprint);
            int spriteSize = (int)PhysicsComposer.WorldSpriteSize(heightCm);
            var color = new Color(0.6f, 0.7f, 0.8f, 0.8f); // Neutral placeholder
            var image = Image.CreateEmpty(spriteSize, spriteSize, false, Image.Format.Rgba8);
            image.Fill(color);
            sprite.Texture = ImageTexture.CreateFromImage(image);
        }

        ghost.Modulate = new Color(0.7f, 0.9f, 1.0f, 0.5f);
        return ghost;
    }

    private void ConfirmPlacement()
    {
        if (_placementGhost is null)
        {
            return;
        }
        var finalPos = _placementGhost.GlobalPosition;
        var blueprint = _pendingBlueprint;

        EndPlacement();

        var name = blueprint.TryGetValue("name", out var nV) ? nV.AsString() : "?";
        Logger.Instance?.Info(
            $"Game: Placed '{name}' at ({finalPos.X:F0}, {finalPos.Y:F0})");
        _world.SpawnObject(blueprint, finalPos);
    }

    private void CancelPlacement()
    {
        EndPlacement();
        Logger.Instance?.Debug("Game: Placement cancelled");
    }

    private void EndPlacement()
    {
        if (_placementGhost is not null && IsInstanceValid(_placementGhost))
        {
            _placementGhost.QueueFree();
            _placementGhost = null;
        }
        _placementActive = false;
        SetProcess(false);
        _pendingBlueprint = new();
        EventBus.Instance.EmitSignal(EventBus.SignalName.PlacementEnded);
    }

    private void ClearPending()
    {
        if (_placementActive)
        {
            EndPlacement();
        }
        if (_materializeEffect is not null && IsInstanceValid(_materializeEffect))
        {
            _materializeEffect.QueueFree();
            _materializeEffect = null;
        }
        _pendingBlueprint = new();
        if (!_placementActive)
        {
            SetProcess(false);
        }
    }

    private static int ExtractHeightCm(Godot.Collections.Dictionary blueprint)
    {
        if (blueprint.TryGetValue("physics", out var physV) &&
            physV.VariantType == Variant.Type.Dictionary)
        {
            var phys = physV.AsGodotDictionary();
            if (phys.TryGetValue("height_cm", out var hV))
            {
                return hV.AsInt32();
            }
        }
        return 30;
    }
}
