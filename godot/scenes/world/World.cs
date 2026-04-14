using Godot;
using Makeshift.Autoloads;
using Makeshift.Interfaces;
using Makeshift.Models;
using Makeshift.Scenes.GameObjects;

namespace Makeshift.Scenes.World;

/// <summary>
/// Owns the object container and tilemap for the active game scene. Spawns
/// <see cref="GameObject"/> instances from blueprints (either typed records
/// coming from Backend via <see cref="IWorld.SpawnObject"/>, or raw Godot
/// dictionaries from the in-game creation flow).
/// </summary>
[GlobalClass]
public partial class World : Node2D, IWorld
{
    private static readonly PackedScene _gameObjectScene =
        GD.Load<PackedScene>("res://scenes/game_object/game_object.tscn");

    private Node2D _objectsContainer = null!;
    private TileMapLayer? _tileMap;
    private Node2D? _currentLevel;

    public override void _Ready()
    {
        AddToGroup("world");
        _objectsContainer = GetNode<Node2D>("ObjectsContainer");
        _tileMap = GetNodeOrNull<TileMapLayer>("TileMapLayer");
    }

    /// <summary>
    /// Typed spawn entry point used by <see cref="Backend"/> when the
    /// destruction-debris pipeline has a properly deserialized
    /// <see cref="Blueprint"/>. Calls
    /// <see cref="GameObject.InitFromBlueprint(Blueprint)"/> directly so the
    /// typed spawn path bypasses the Blueprint -> Dict -> Blueprint round trip.
    /// </summary>
    public void SpawnObject(Blueprint blueprint, Vector2 position)
    {
        Logger.Instance?.Debug($"World: Spawning '{blueprint.Name}' at {position} (typed)");

        var obj = (GameObject)_gameObjectScene.Instantiate();
        _objectsContainer.AddChild(obj);
        obj.GlobalPosition = position;
        obj.InitFromBlueprint(blueprint);

        Logger.Instance?.Debug(
            $"World: Object count after spawn: {_objectsContainer.GetChildCount()}");
    }

    /// <summary>
    /// Dictionary spawn entry point used by <c>Game.cs</c> (which receives
    /// the blueprint via the <see cref="EventBus.ObjectCreated"/> signal as
    /// a <see cref="Godot.Collections.Dictionary"/>).
    /// </summary>
    public Node SpawnObject(Godot.Collections.Dictionary blueprint, Vector2 position)
    {
        var name = blueprint.TryGetValue("name", out var n) ? n.AsString() : "?";
        Logger.Instance?.Debug($"World: Spawning '{name}' at {position}");

        var obj = (GameObject)_gameObjectScene.Instantiate();
        _objectsContainer.AddChild(obj);
        obj.GlobalPosition = position;
        obj.InitFromBlueprint(blueprint);

        Logger.Instance?.Debug(
            $"World: Object count after spawn: {_objectsContainer.GetChildCount()}");
        return obj;
    }

    public void ClearObjects()
    {
        Logger.Instance?.Info(
            $"World: Clearing all objects ({_objectsContainer.GetChildCount()})");
        foreach (var child in _objectsContainer.GetChildren())
        {
            child.QueueFree();
        }
        Logger.Instance?.Debug("World: Object count after clear: 0");
    }

    /// <summary>
    /// Snapshot of every spawned object's blueprint + position, used by
    /// <see cref="Backend"/> for periodic session sync. Returns a Godot Array
    /// of dicts so the dict-oriented sync payload stays unchanged on the wire.
    /// </summary>
    public Godot.Collections.Array GetObjectsData()
    {
        var data = new Godot.Collections.Array();
        foreach (var child in _objectsContainer.GetChildren())
        {
            if (child is GameObject go)
            {
                data.Add(new Godot.Collections.Dictionary
                {
                    ["blueprint"] = go.GetBlueprintDictionary(),
                    ["position"] = new Godot.Collections.Dictionary
                    {
                        ["x"] = go.GlobalPosition.X,
                        ["y"] = go.GlobalPosition.Y,
                    },
                });
            }
        }
        return data;
    }

    public void LoadLevel(PackedScene levelScene)
    {
        if (_currentLevel is not null)
        {
            _currentLevel.QueueFree();
            _currentLevel = null;
        }

        _currentLevel = (Node2D)levelScene.Instantiate();
        AddChild(_currentLevel);
        MoveChild(_currentLevel, 0); // Behind objects
    }

}
