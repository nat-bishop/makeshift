using System.Collections.Generic;
using Godot;
using Makeshift.Data;
using Timer = Godot.Timer;

namespace Makeshift.Systems;

/// <summary>
/// Manages timed decay of states. Created by <see cref="StateManager"/> as a
/// child node. Each active decay owns a one-shot <see cref="Timer"/> child.
///
/// C# Dictionary (not <c>Godot.Collections.Dictionary</c>) — no marshaling
/// crosses here, all callers are in-process C#.
/// </summary>
public partial class StateDecay : Node
{
    [Signal]
    public delegate void DecayExpiredEventHandler(int state);

    private readonly Dictionary<StateId, Timer> _timers = new();

    public void SetDecay(StateId state, float duration)
    {
        CancelDecay(state);
        var timer = new Timer
        {
            WaitTime = duration,
            OneShot = true,
        };
        // Capture state for the closure; Timer.Timeout is parameterless.
        var captured = state;
        timer.Timeout += () => OnTimerExpired(captured);
        AddChild(timer);
        timer.Start();
        _timers[state] = timer;
    }

    public void CancelDecay(StateId state)
    {
        if (_timers.TryGetValue(state, out var timer))
        {
            if (GodotObject.IsInstanceValid(timer))
            {
                timer.Stop();
                timer.QueueFree();
            }
            _timers.Remove(state);
        }
    }

    private void OnTimerExpired(StateId state)
    {
        CancelDecay(state);
        EmitSignal(SignalName.DecayExpired, (int)state);
    }
}
