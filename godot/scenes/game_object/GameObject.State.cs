using Godot;
using Makeshift.Data;
using Makeshift.Systems;

namespace Makeshift.Scenes.GameObjects;

/// <summary>
/// IStateful implementation + state-driven mechanics (DOTs, freeze, friction
/// reset). Delegates storage to the child <see cref="StateManager"/>.
/// </summary>
public partial class GameObject
{
    // --- IStateful ---------------------------------------------------------

    public void AddState(StateId state, float duration) =>
        _stateManager?.AddState(state, duration);

    public void RemoveState(StateId state) =>
        _stateManager?.RemoveState(state);

    public bool HasState(StateId state) =>
        _stateManager is not null && _stateManager.HasState(state);

    /// <summary>
    /// Typed snapshot of every currently active state. Empty when the state
    /// manager hasn't been attached yet. Exposed for the debug overlay.
    /// </summary>
    public System.Collections.Generic.IReadOnlyCollection<StateId> States =>
        _stateManager?.States
        ?? (System.Collections.Generic.IReadOnlyCollection<StateId>)System.Array.Empty<StateId>();

    // --- State change handlers --------------------------------------------

    private void OnStateAdded(string state)
    {
        // Visual feedback
        var stateId = StateContradictions.NameToId(state);
        if (StateVisuals.StateColors.TryGetValue(stateId, out var color))
        {
            _objectVisual?.SpawnParticles(color);
        }
        // State-specific mechanics
        StateEffects.ApplyStandardDot(this, stateId);
        switch (stateId)
        {
            case StateId.Frozen:
                Freeze = true;
                break;
            case StateId.Wet:
                if (PhysicsMaterialOverride is { } mat)
                {
                    mat.Friction = PhysicsComposer.SurfaceFriction(Surface.Slippery);
                }
                break;
        }
    }

    private void OnStatesChanged(Godot.Collections.Array updatedStates)
    {
        // Refresh visuals
        if (_stateManager is null)
        {
            return;
        }
        _objectVisual?.RefreshStateVisuals(_stateManager.States);

        // Unfreeze if no longer frozen
        if (!_stateManager.HasState(StateId.Frozen))
        {
            Freeze = false;
        }
        // Stop DOT if state removed
        if (!_stateManager.HasState(StateId.Burning))
        {
            StateEffects.StopStandardDot(this, StateId.Burning);
        }
        if (!_stateManager.HasState(StateId.Electrified))
        {
            StateEffects.StopStandardDot(this, StateId.Electrified);
        }
        // Restore friction if no longer wet
        if (!_stateManager.HasState(StateId.Wet) && PhysicsMaterialOverride is { } mat)
        {
            mat.Friction = PhysicsComposer.SurfaceFriction(_baseSurface);
        }

        // Essential-state destruction: if object lost ALL its initial states,
        // destroy it (e.g., fire loses burning → destroyed, ice loses frozen
        // → melted).
        var initials = InitialStates;
        if (initials.Length > 0 && !_dying)
        {
            bool hasAnyInitial = false;
            foreach (var sid in initials)
            {
                if (sid != StateId.None && _stateManager.HasState(sid))
                {
                    hasAnyInitial = true;
                    break;
                }
            }
            if (!hasAnyInitial)
            {
                _dying = true;
                TakeDamage(EssentialStateKillDamage, Colors.White);
                return;
            }
        }

        // Debounced backend notification for creature re-evaluation
        _stateChangeDebounce = StateChangeDebounceTime;
        SetProcess(true);
    }

}
