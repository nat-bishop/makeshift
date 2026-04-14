using System;
using System.Linq;
using Godot;
using Makeshift.Autoloads;
using Makeshift.Data;
using Makeshift.Interfaces;
using Makeshift.Models;
using Makeshift.Systems;

namespace Makeshift.Scenes.GameObjects;

/// <summary>
/// GameObject: LLM-generated physics, states (not tags), affordance (not
/// categories), no behavior verbs. Implements <see cref="IObjectNamed"/>,
/// <see cref="IDamageable"/>, <see cref="IHealable"/>, <see cref="IStateful"/>,
/// and <see cref="IImpulsable"/>. Split into partial files: construction +
/// state propagation live here, damage/heal in GameObject.Damage.cs, and
/// state delegation in GameObject.State.cs.
/// </summary>
[GlobalClass]
public partial class GameObject : RigidBody2D, IObjectNamed, IDamageable, IHealable, IStateful, IImpulsable
{
    private const float StateChangeDebounceTime = 0.5f;
    private const float EssentialStateKillDamage = 99999.0f;

    /// <summary>Durability tier → HP lookup. Mirrors backend DURABILITY_HP.</summary>
    private static readonly int[] DurabilityHp = { 5, 15, 40, 80, 150, 300 };

    public string ObjectId { get; set; } = "";
    public string ObjectName { get; set; } = "";
    public int CurrentHp { get; set; } = 50;
    public int MaxHp { get; set; } = 50;
    public bool Autonomous { get; set; }
    public string DestructionResultName { get; set; } = "";

    /// <summary>Typed Blueprint record. Preferred for C# callers.</summary>
    public Blueprint? TypedBlueprint { get; private set; }

    public Durability Durability => TypedBlueprint?.Durability ?? Durability.Normal;
    public Affordance Affordance => TypedBlueprint?.Affordance ?? Affordance.None;
    public SpeedTier Speed => TypedBlueprint?.Speed ?? SpeedTier.Normal;
    public bool HasField => TypedBlueprint?.HasField ?? false;
    public int FieldRangeCm => TypedBlueprint?.FieldRangeCm ?? 0;

    /// <summary>Initial states as typed ids; empty when no blueprint is loaded.</summary>
    public StateId[] InitialStates =>
        TypedBlueprint?.InitialStates ?? Array.Empty<StateId>();

    /// <summary>Susceptible states as typed ids; empty when no blueprint is loaded.</summary>
    public StateId[] SusceptibleStates =>
        TypedBlueprint?.SusceptibleStates ?? Array.Empty<StateId>();

    /// <summary>
    /// Optional preloaded sprite from img2img destruction debris pipeline.
    /// Set when the spawn-time blueprint dictionary contains
    /// <c>_preloaded_sprite</c> (Backend wires this up).
    /// </summary>
    public Texture2D? PreloadedSprite { get; private set; }

    /// <summary>
    /// Combined player+object sprite for carry/ride affordances. Populated by
    /// <see cref="EventBus.CombinedSpriteReady"/> matched on object id.
    /// </summary>
    public Texture2D? CombinedTexture { get; set; }

    private bool _dying;
    private StateManager? _stateManager;
    private Node? _statePropagator;
    private Node? _objectBehavior;
    private float _stateChangeDebounce;

    /// <summary>Stored at init for WET state restore.</summary>
    private Surface _baseSurface = Surface.Normal;

    private PhysicsApplicator? _physicsApplicator;
    private ObjectVisual? _objectVisual;

    public override void _Ready()
    {
        CollisionLayer = (uint)CollisionLayers.Objects;
        CollisionMask = (uint)(CollisionLayers.Terrain | CollisionLayers.Player | CollisionLayers.Objects);
        SetProcess(false);

        _physicsApplicator = GetNode<PhysicsApplicator>("PhysicsApplicator");
        _objectVisual = GetNode<ObjectVisual>("ObjectVisual");

        EventBus.Instance.CombinedSpriteReady += OnCombinedSpriteReady;
    }

    private void OnCombinedSpriteReady(string id, Texture2D texture)
    {
        if (id == ObjectId)
        {
            CombinedTexture = texture;
        }
    }

    /// <summary>
    /// Initialize from a Godot Dictionary blueprint (still passed by the
    /// in-game creation / level-fixture spawn path as a dict). Round-trips
    /// through <see cref="BlueprintMarshal"/> to build a typed
    /// <see cref="Blueprint"/>; every subsequent read goes through the typed
    /// record — no raw dict field is stored on the GameObject itself.
    /// </summary>
    public void InitFromBlueprint(Godot.Collections.Dictionary bp)
    {
        // Extract the runtime-only preloaded sprite reference BEFORE
        // marshalling — the typed Blueprint record doesn't have a slot for
        // it, and Texture2D doesn't survive Json.Stringify.
        if (bp.TryGetValue("_preloaded_sprite", out var preloaded) &&
            preloaded.VariantType == Variant.Type.Object)
        {
            PreloadedSprite = preloaded.As<Texture2D>();
            bp.Remove("_preloaded_sprite");
        }

        var typed = BlueprintMarshal.FromGodotDictionary(bp, "GameObject");
        if (typed is null)
        {
            Logger.Instance?.Warn("GameObject: Blueprint deserialize returned null; aborting init");
            return;
        }
        InitFromBlueprint(typed);
    }

    /// <summary>
    /// Typed initialization entry point. Called directly from
    /// <see cref="World.SpawnObject(Blueprint, Vector2)"/> to avoid the
    /// Blueprint -> Dict -> Blueprint round trip, and indirectly from the
    /// dict overload above.
    /// </summary>
    public void InitFromBlueprint(Blueprint bp)
    {
        TypedBlueprint = bp;

        ObjectId = TypedBlueprint?.Id ?? "";
        ObjectName = TypedBlueprint?.Name ?? "";
        Autonomous = TypedBlueprint?.Autonomous ?? false;
        DestructionResultName = TypedBlueprint?.DestructionResultName ?? "";

        var durIdx = (int)Durability;
        if (durIdx >= (int)Data.Durability.Indestructible)
        {
            CurrentHp = 999999;
            MaxHp = 999999;
        }
        else
        {
            int hpVal = durIdx >= 0 && durIdx < DurabilityHp.Length
                ? DurabilityHp[durIdx]
                : 40;
            CurrentHp = hpVal;
            MaxHp = hpVal;
        }

        // Surface for WET restore
        _baseSurface = TypedBlueprint?.Physics.Surface ?? Surface.Normal;

        // State manager (objects are born stateless)
        _stateManager = new StateManager { Name = "StateManager" };
        AddChild(_stateManager);
        _stateManager.InitStates(ObjectName);
        _stateManager.StateAdded += OnStateAdded;
        _stateManager.StatesChanged += OnStatesChanged;

        // Physics from LLM-generated values
        _physicsApplicator?.Apply(TypedBlueprint?.Physics ?? new PhysicsData(), ObjectName);

        // Visual
        _objectVisual?.SetObjectId(ObjectId);
        if (TypedBlueprint is not null)
        {
            _objectVisual?.InitVisuals(TypedBlueprint);
        }

        // Groups
        AddToGroup("game_objects");
        if (Autonomous)
        {
            AddToGroup("living");
        }

        // State propagation system
        var heightCm = TypedBlueprint?.Physics.HeightCm ?? 30;
        CreateStatePropagator(heightCm);

        // Apply initial states (fire spawns burning, ice spawns frozen, etc.)
        foreach (var sid in InitialStates)
        {
            if (sid != StateId.None)
            {
                _stateManager.AddState(sid, 0.0f);
            }
        }

        // Object behavior (active creatures + reactive objects like bombs/fans)
        if (Autonomous)
        {
            CreateObjectBehavior();
        }

        var debugLabel = new Makeshift.UI.DebugLabel();
        AddChild(debugLabel);
        debugLabel.Init(this);

        Logger.Instance?.Info(
            $"GameObject: Initialized '{ObjectName}' (id={ObjectId}) hp={CurrentHp} " +
            $"durability={Durability} affordance={Affordance}");
    }

    private void CreateObjectBehavior()
    {
        var ob = new ObjectBehavior { Name = "ObjectBehavior" };
        AddChild(ob);
        ob.InitObject(this, ObjectName, Speed, Autonomous);
        _objectBehavior = ob;
    }

    /// <summary>
    /// Expose the child <see cref="Systems.ObjectBehavior"/> (if any) for the
    /// typed debug overlay. Returns <c>null</c> for non-autonomous objects.
    /// </summary>
    public ObjectBehavior? GetObjectBehavior() => _objectBehavior as ObjectBehavior;

    private void CreateStatePropagator(int heightCm)
    {
        var sp = new StatePropagator { Name = "StatePropagator" };
        AddChild(sp);
        sp.InitPropagator(this, heightCm);
        _statePropagator = sp;
    }

    // --- IObjectNamed ------------------------------------------------------

    public string GetObjectName() => ObjectName;

    public string[] GetTags() =>
        _stateManager?.GetStateNamesArray() ?? Array.Empty<string>();

    // --- IImpulsable -------------------------------------------------------

    public void ApplyExternalImpulse(Vector2 impulse)
    {
        ApplyCentralImpulse(impulse);
    }

    // --- Pushable / heavy helpers ------------------------------------------

    public bool IsPassivelyPushable()
    {
        var mass = TypedBlueprint?.Physics.MassKg ?? 1.0f;
        return mass < 0.5f;
    }

    public bool IsHeavy()
    {
        var mass = TypedBlueprint?.Physics.MassKg ?? 1.0f;
        return mass > 50.0f;
    }

    /// <summary>
    /// Reconstruct a Godot Dictionary form of the typed blueprint for
    /// session-sync serialization. Round-trips through
    /// <see cref="BlueprintMarshal"/> so wire format stays identical to
    /// the backend payload that originally seeded the record.
    /// </summary>
    public Godot.Collections.Dictionary GetBlueprintDictionary()
    {
        return TypedBlueprint is null
            ? new Godot.Collections.Dictionary()
            : BlueprintMarshal.ToGodotDictionary(TypedBlueprint);
    }

    // --- State-change event handlers (logic split into GameObject.State.cs) ---

    public override void _Process(double delta)
    {
        if (_stateChangeDebounce > 0.0f)
        {
            _stateChangeDebounce -= (float)delta;
            if (_stateChangeDebounce <= 0.0f)
            {
                _stateChangeDebounce = 0.0f;
                SetProcess(false);
                Backend.Instance.SendStateChanged(ObjectName, _stateManager?.GetStates() ?? new Godot.Collections.Array());
            }
        }
    }

    public override void _ExitTree()
    {
        if (EventBus.Instance is not null)
        {
            EventBus.Instance.CombinedSpriteReady -= OnCombinedSpriteReady;
        }
    }
}
