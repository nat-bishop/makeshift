using Godot;
using Makeshift.Data;

namespace Makeshift.Systems;

/// <summary>
/// Shared state-driven effect helpers. Both <c>GameObject.State</c> and
/// <c>Player</c> apply identical DOT tick/duration constants on the
/// <see cref="StateId.Burning"/> / <see cref="StateId.Electrified"/> states;
/// this class centralises that dispatch so the timing tables live in exactly
/// one place.
/// </summary>
public static class StateEffects
{
    /// <summary>
    /// Start the standard damage-over-time effect for <paramref name="state"/>
    /// on <paramref name="target"/>, using <see cref="StateVisuals"/> timing
    /// constants and the per-state color. No-op for states without a DOT.
    /// </summary>
    public static void ApplyStandardDot(Node target, StateId state)
    {
        switch (state)
        {
            case StateId.Burning:
                WorldMutations.ApplyDot(
                    target,
                    StateVisuals.BURNING_DOT,
                    StateVisuals.BURNING_TICK,
                    StateVisuals.BURNING_DURATION,
                    StateVisuals.GetStateColorOrWhite(StateId.Burning),
                    "_dot_burning");
                break;
            case StateId.Electrified:
                WorldMutations.ApplyDot(
                    target,
                    StateVisuals.ELECTRIFIED_DOT,
                    StateVisuals.ELECTRIFIED_TICK,
                    StateVisuals.ELECTRIFIED_DURATION,
                    StateVisuals.GetStateColorOrWhite(StateId.Electrified),
                    "_dot_electrified");
                break;
        }
    }

    /// <summary>
    /// Stop the DOT previously started by <see cref="ApplyStandardDot"/> for
    /// <paramref name="state"/>. No-op for states without a DOT.
    /// </summary>
    public static void StopStandardDot(Node target, StateId state)
    {
        switch (state)
        {
            case StateId.Burning:
                WorldMutations.StopDot(target, "_dot_burning");
                break;
            case StateId.Electrified:
                WorldMutations.StopDot(target, "_dot_electrified");
                break;
        }
    }
}
