using Godot;
using Makeshift.Autoloads;
using Makeshift.Data;
using Makeshift.Interfaces;
using Makeshift.Models;
using Makeshift.Systems;

namespace Makeshift.Scenes.EnvironmentBody;

/// <summary>
/// Named, indestructible environment body. Participates in the pairwise
/// behavior cache as a target via <see cref="IObjectNamed"/> and
/// <see cref="IStateful"/>. Env bodies do NOT implement
/// <see cref="IDamageable"/> / <see cref="IHealable"/>.
/// </summary>
[GlobalClass]
public partial class EnvironmentBody : StaticBody2D, IObjectNamed, IStateful
{
    private const float FieldMargin = 32.0f;

    [Export] public string EnvName { get; set; } = "";

    /// <summary>Typed Blueprint record. Preferred for C# callers.</summary>
    public Blueprint? TypedBlueprint { get; private set; }

    private StateManager? _stateManager;
    private bool _solid = true;
    private bool _initiallySolid = true;
    private ColorRect? _visual;
    private Color _initialColor;
    private Area2D? _fieldArea;

    public void InitEnv(string envName, Godot.Collections.Dictionary bp, Vector2 size, Color color, bool solid = true)
    {
        EnvName = envName;
        TypedBlueprint = BlueprintMarshal.FromGodotDictionary(bp, "EnvironmentBody");

        _stateManager = new StateManager { Name = "StateManager" };
        AddChild(_stateManager);
        _stateManager.InitStates(envName);
        _stateManager.StatesChanged += OnStatesChanged;

        _solid = solid;
        _initiallySolid = solid;
        _initialColor = color;

        CollisionLayer = solid ? (uint)CollisionLayers.Objects : 0u;
        CollisionMask = 0u;

        // Physics shape
        var bodyShape = new CollisionShape2D();
        var rect = new RectangleShape2D { Size = size };
        bodyShape.Shape = rect;
        AddChild(bodyShape);

        // Visual
        _visual = new ColorRect
        {
            Size = size,
            Position = -size / 2f,
            Color = color,
        };
        AddChild(_visual);

        // Detection Area2D — no current consumer, kept for potential reuse
        // by future systems.
        _fieldArea = new Area2D
        {
            Name = "FieldArea",
            CollisionLayer = 0,
            CollisionMask = (uint)(CollisionLayers.Objects | CollisionLayers.Player),
            Monitoring = true,
            Monitorable = false,
        };
        var areaShape = new CollisionShape2D();
        var fieldRect = new RectangleShape2D
        {
            Size = size + new Vector2(FieldMargin * 2, FieldMargin * 2),
        };
        areaShape.Shape = fieldRect;
        _fieldArea.AddChild(areaShape);
        AddChild(_fieldArea);

        AddToGroup("game_objects");

        Logger.Instance?.Info($"EnvironmentBody: Initialized '{EnvName}', solid={solid}");
    }

    // --- IObjectNamed ------------------------------------------------------

    public string GetObjectName() => EnvName;

    public string[] GetTags() =>
        _stateManager?.GetStateNamesArray() ?? System.Array.Empty<string>();

    // --- IStateful ---------------------------------------------------------

    public void AddState(StateId state, float duration) => _stateManager?.AddState(state, duration);

    public void RemoveState(StateId state) => _stateManager?.RemoveState(state);

    public bool HasState(StateId state) => _stateManager is not null && _stateManager.HasState(state);

    // --- State change handling ---------------------------------------------

    private void OnStatesChanged(Godot.Collections.Array updatedStates)
    {
        UpdateSolidity();
        UpdateVisuals();
    }

    private void UpdateSolidity()
    {
        bool shouldBeSolid;
        if (_stateManager is not null && _stateManager.HasState(StateId.Frozen))
        {
            shouldBeSolid = true; // Frozen surface is walkable
        }
        else
        {
            shouldBeSolid = _initiallySolid;
        }
        if (shouldBeSolid != _solid)
        {
            _solid = shouldBeSolid;
            CollisionLayer = _solid ? (uint)CollisionLayers.Objects : 0u;
        }
    }

    private void UpdateVisuals()
    {
        if (_visual is null)
        {
            return;
        }
        if (_stateManager is not null && _stateManager.HasState(StateId.Frozen))
        {
            _visual.Color = new Color(0.7f, 0.85f, 1.0f, 0.85f);
        }
        else
        {
            _visual.Color = _initialColor;
        }
    }

}
