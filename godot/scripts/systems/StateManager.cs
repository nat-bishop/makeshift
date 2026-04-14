using System.Collections.Generic;
using Godot;
using Makeshift.Autoloads;
using Makeshift.Data;
using Makeshift.Interfaces;

namespace Makeshift.Systems;

/// <summary>
/// Manages interaction states (burning, frozen, wet, electrified). Objects
/// are born stateless; states are applied by interactions and decayed by a
/// child <see cref="StateDecay"/> node.
/// </summary>
public partial class StateManager : Node, IStateful
{
    [Signal]
    public delegate void StateAddedEventHandler(string state);

    [Signal]
    public delegate void StateRemovedEventHandler(string state);

    [Signal]
    public delegate void StatesChangedEventHandler(Godot.Collections.Array states);

    private readonly HashSet<StateId> _states = new();
    private StateDecay? _decay;
    private string _ownerName = "?";

    public void InitStates(string ownerName)
    {
        _ownerName = ownerName;
        _decay = new StateDecay { Name = "StateDecay" };
        _decay.DecayExpired += OnDecayExpired;
        AddChild(_decay);
    }

    /// <summary>Snapshot of currently active state names as a Godot array.</summary>
    public Godot.Collections.Array GetStates()
    {
        var arr = new Godot.Collections.Array();
        foreach (var s in _states)
        {
            arr.Add(StateContradictions.GetName(s));
        }
        return arr;
    }

    /// <summary>
    /// Typed snapshot of currently active state names as a C# <c>string[]</c>.
    /// Used by <c>GameObject.GetTags()</c> / <c>EnvironmentBody.GetTags()</c>
    /// to avoid duplicating the iteration.
    /// </summary>
    public string[] GetStateNamesArray()
    {
        var arr = new string[_states.Count];
        int i = 0;
        foreach (var s in _states)
        {
            arr[i++] = StateContradictions.GetName(s);
        }
        return arr;
    }

    // --- Typed IStateful API -------------------------------------------------

    public void AddState(StateId state, float duration)
    {
        if (state == StateId.None)
        {
            return;
        }

        // Remove contradictions (directed)
        foreach (var contra in StateContradictions.GetRemovals(state))
        {
            if (_states.Contains(contra))
            {
                RemoveState(contra);
            }
        }

        bool isNew = _states.Add(state);
        if (isNew)
        {
            var stateName = StateContradictions.GetName(state);
            if (Logger.Instance?.IsDebugEnabled ?? false)
            {
                Logger.Instance.Debug($"StateManager: +{stateName} on '{_ownerName}' (duration={duration:F1}s)");
            }
            EmitSignal(SignalName.StateAdded, stateName);
            EmitSignal(SignalName.StatesChanged, GetStates());
        }

        if (duration > 0.0f)
        {
            _decay?.SetDecay(state, duration);
        }
    }

    public void RemoveState(StateId state)
    {
        _decay?.CancelDecay(state);
        if (!_states.Remove(state))
        {
            return;
        }

        var stateName = StateContradictions.GetName(state);
        if (Logger.Instance?.IsDebugEnabled ?? false)
        {
            Logger.Instance.Debug($"StateManager: -{stateName} on '{_ownerName}'");
        }
        EmitSignal(SignalName.StateRemoved, stateName);
        EmitSignal(SignalName.StatesChanged, GetStates());
    }

    public bool HasState(StateId state)
    {
        return _states.Contains(state);
    }

    public IReadOnlyCollection<StateId> States => _states;

    private void OnDecayExpired(int state)
    {
        RemoveState((StateId)state);
    }
}
