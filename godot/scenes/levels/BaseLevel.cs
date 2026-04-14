using Godot;
using Makeshift.Autoloads;
using Makeshift.Data;
using Makeshift.Scenes.GameObjects;
using Makeshift.Systems;

namespace Makeshift.Scenes.Levels;

/// <summary>
/// Base class for all levels. Provides spawn point, goal area, objective, and
/// shared terrain-building helpers. Subclasses (<see cref="Level01"/>,
/// <see cref="Level02"/>, <see cref="Level03"/>) populate terrain and
/// game-object placements in their own <see cref="_Ready"/> override.
/// </summary>
[GlobalClass]
public partial class BaseLevel : Node2D
{
    private static readonly PackedScene _gameObjectScene =
        GD.Load<PackedScene>("res://scenes/game_object/game_object.tscn");

    private static readonly Texture2D _platformTex =
        GD.Load<Texture2D>("res://assets/tilesets/cardboard_platform.png");

    // Export names match the identifiers baked into the level .tscn files.
    [Export] public int level_id { get; set; }
    [Export] public string objective_text { get; set; } = "";
    [Export] public string next_level_path { get; set; } = "";

    protected Marker2D SpawnPoint { get; private set; } = null!;
    protected Area2D GoalArea { get; private set; } = null!;

    public override void _Ready()
    {
        SpawnPoint = GetNode<Marker2D>("SpawnPoint");
        GoalArea = GetNode<Area2D>("Goal");

        Logger.Instance?.Info(
            $"Level: Ready — id={level_id} path={SceneFilePath}");
        GoalArea.BodyEntered += OnGoalBodyEntered;
    }

    private void OnGoalBodyEntered(Node2D body)
    {
        if (IsPlayer(body))
        {
            Logger.Instance?.Info(
                $"BaseLevel: Player reached goal! Completing level {level_id}");
            EventBus.Instance.EmitSignal(EventBus.SignalName.LevelCompleted, level_id);
        }
    }

    // --- Shared helpers -----------------------------------------------------

    protected static bool IsPlayer(Node body)
        => body is CharacterBody2D && body.IsInGroup("player");

    protected void RespawnPlayer(Node2D body)
    {
        Logger.Instance?.Info(
            $"BaseLevel: Respawning player to {SpawnPoint.GlobalPosition}");
        body.GlobalPosition = SpawnPoint.GlobalPosition;
        if (body is CharacterBody2D cb)
        {
            cb.Velocity = Vector2.Zero;
        }
    }

    protected void CreatePlatform(Vector2 pos, Vector2 size) =>
        CreatePlatform(pos, size, _platformTex);

    protected void CreatePlatform(Vector2 pos, Vector2 size, Texture2D texture)
    {
        var body = new StaticBody2D
        {
            Position = pos + size / 2f,
            CollisionLayer = (uint)CollisionLayers.Terrain,
            CollisionMask = 0u,
        };

        var shape = new CollisionShape2D();
        var rect = new RectangleShape2D { Size = size };
        shape.Shape = rect;
        body.AddChild(shape);

        var visual = new TextureRect
        {
            Texture = texture,
            ExpandMode = TextureRect.ExpandModeEnum.IgnoreSize,
            Size = size,
            Position = -size / 2f,
            StretchMode = TextureRect.StretchModeEnum.Tile,
        };
        body.AddChild(visual);

        AddChild(body);
    }

    protected Node SpawnGameObject(Godot.Collections.Dictionary blueprint, Vector2 pos)
    {
        var obj = (GameObject)_gameObjectScene.Instantiate();
        AddChild(obj);
        obj.GlobalPosition = pos;
        obj.InitFromBlueprint((Godot.Collections.Dictionary)blueprint.Duplicate(deep: true));
        return obj;
    }

    protected void CreateKillZone(Vector2 pos, Vector2 size)
    {
        var area = new Area2D
        {
            Position = pos + size / 2f,
            CollisionLayer = (uint)CollisionLayers.Hazards,
            CollisionMask = (uint)(CollisionLayers.Player | CollisionLayers.Objects),
        };
        var shape = new CollisionShape2D();
        var rect = new RectangleShape2D { Size = size };
        shape.Shape = rect;
        area.AddChild(shape);
        area.BodyEntered += OnKillZoneEntered;
        AddChild(area);
    }

    private void OnKillZoneEntered(Node2D body)
    {
        if (IsPlayer(body))
        {
            RespawnPlayer(body);
        }
        else
        {
            WorldMutations.ApplyDamage(body, 999.0f);
        }
    }

    /// <summary>Instantiate an <see cref="EnvironmentBody"/> and initialize it.</summary>
    protected EnvironmentBody.EnvironmentBody CreateEnvBody(
        Vector2 pos,
        Vector2 size,
        string envName,
        Godot.Collections.Dictionary bp,
        Color color,
        bool solid = true)
    {
        var body = new EnvironmentBody.EnvironmentBody
        {
            Position = pos + size / 2f,
        };
        AddChild(body);
        body.InitEnv(envName, bp, size, color, solid);
        return body;
    }
}
