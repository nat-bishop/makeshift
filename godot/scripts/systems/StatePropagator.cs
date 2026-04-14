using Godot;
using Makeshift.Data;
using Makeshift.Interfaces;
using Makeshift.Scenes.GameObjects;
using Timer = Godot.Timer;

namespace Makeshift.Systems;

/// <summary>
/// Tick-based state propagation: when an owning object has active states,
/// periodically spread them to susceptible neighbors inside an
/// <see cref="Area2D"/>. Propagation rate is driven by
/// <see cref="TickInterval"/> so effects like fire visibly spread as a wave.
/// </summary>
public partial class StatePropagator : Node
{
    private const float TickInterval = 2.0f;
    private const float BaseRadius = 64.0f;
    private const float DefaultPropagationDuration = 10.0f;

    // Collision mask: propagate to player + objects layers. Symbolic so the
    // bitmask can't drift from CollisionLayers.
    private const uint MaskPlayerObjects = (uint)(CollisionLayers.Player | CollisionLayers.Objects);

    private Node2D? _owner;
    private Area2D? _propagationArea;
    private Timer? _tickTimer;
    private bool _ticking;
    private StateManager? _ownerStateManager;

    public void InitPropagator(Node2D owner, int heightCm)
    {
        _owner = owner;
        CreateArea(heightCm);
        CreateTimer();

        _ownerStateManager = owner.GetNodeOrNull<StateManager>("StateManager");
        if (_ownerStateManager is not null)
        {
            _ownerStateManager.StateAdded += OnStateAdded;
            _ownerStateManager.StatesChanged += OnStatesChanged;
        }
    }

    private void CreateArea(int heightCm)
    {
        _propagationArea = new Area2D
        {
            Name = "PropagationArea",
            CollisionLayer = 0,
            CollisionMask = MaskPlayerObjects,
            Monitoring = true,
            Monitorable = false,
        };

        var shapeNode = new CollisionShape2D();
        var circle = new CircleShape2D();
        float scale = PhysicsComposer.PropagationRadiusFromHeight(heightCm);
        circle.Radius = BaseRadius * scale;
        shapeNode.Shape = circle;
        _propagationArea.AddChild(shapeNode);
        _owner!.AddChild(_propagationArea);
    }

    private void CreateTimer()
    {
        _tickTimer = new Timer
        {
            WaitTime = TickInterval,
            OneShot = false,
        };
        _tickTimer.Timeout += OnTick;
        AddChild(_tickTimer);
    }

    private void OnStateAdded(string stateName)
    {
        _ = stateName;
        if (!_ticking)
        {
            _ticking = true;
            _tickTimer?.Start();
            // Immediate first tick so effects aren't delayed.
            OnTick();
        }
    }

    private void OnStatesChanged(Godot.Collections.Array states)
    {
        if (states.Count == 0 && _ticking)
        {
            _ticking = false;
            _tickTimer?.Stop();
        }
    }

    private void OnTick()
    {
        if (_propagationArea is null || _owner is null || !GodotObject.IsInstanceValid(_owner))
        {
            return;
        }
        if (_ownerStateManager is null)
        {
            return;
        }

        // Snapshot owner's active states as typed StateId values.
        var myStates = _ownerStateManager.States;
        if (myStates.Count == 0)
        {
            _ticking = false;
            _tickTimer?.Stop();
            return;
        }

        foreach (var body in _propagationArea.GetOverlappingBodies())
        {
            if (body == _owner || !GodotObject.IsInstanceValid(body))
            {
                continue;
            }

            // Only GameObject carries a SusceptibleStates list.
            // EnvironmentBody is not susceptible to propagated state spread.
            if (body is not GameObject go || body is not IStateful stateful)
            {
                continue;
            }

            var susceptible = go.SusceptibleStates;
            if (susceptible.Length == 0)
            {
                continue;
            }
            foreach (var state in myStates)
            {
                if (System.Array.IndexOf(susceptible, state) >= 0)
                {
                    stateful.AddState(state, DefaultPropagationDuration);
                }
            }
        }
    }

    public override void _ExitTree()
    {
        if (_ownerStateManager is not null && GodotObject.IsInstanceValid(_ownerStateManager))
        {
            _ownerStateManager.StateAdded -= OnStateAdded;
            _ownerStateManager.StatesChanged -= OnStatesChanged;
        }
        _ownerStateManager = null;
    }
}
