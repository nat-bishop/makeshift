using System.Collections.Frozen;
using System.Collections.Generic;
using Godot;

namespace Makeshift.Data;

/// <summary>Per-state particle config (color, direction, amount, speed, spread).</summary>
public readonly record struct ParticleConfig(
    Color Color,
    Vector2 Direction,
    int Amount,
    float Speed,
    float Spread);

/// <summary>Per-state flash config (interval + color).</summary>
public readonly record struct FlashConfig(float Interval, Color Color);

/// <summary>Per-state <c>PointLight2D</c> config (color, energy, range).</summary>
public readonly record struct LightConfig(Color Color, float Energy, float Range);

/// <summary>
/// V3 state-keyed visual configs. 4 states: burning, frozen, wet, electrified.
/// Each state maps to particle, shader, color shift, flash, and light configs.
/// Also hosts the shared DOT / speed / damage constants used by both
/// GameObject and Player when applying state effects.
/// </summary>
public static class StateVisuals
{
    // --- Typed (C#) lookups keyed by StateId --------------------------------

    public static readonly FrozenDictionary<StateId, ParticleConfig> Particles =
        new Dictionary<StateId, ParticleConfig>
        {
            [StateId.Burning] = new(
                Color: new Color(1.0f, 0.5f, 0.0f, 0.8f),
                Direction: new Vector2(0, -1),
                Amount: 8,
                Speed: 40.0f,
                Spread: 30.0f),
            [StateId.Wet] = new(
                Color: new Color(0.3f, 0.5f, 1.0f, 0.6f),
                Direction: new Vector2(0, 1),
                Amount: 4,
                Speed: 20.0f,
                Spread: 15.0f),
            [StateId.Electrified] = new(
                Color: new Color(1.0f, 1.0f, 0.2f, 0.9f),
                Direction: new Vector2(0, 0),
                Amount: 6,
                Speed: 60.0f,
                Spread: 180.0f),
        }.ToFrozenDictionary();

    public static readonly FrozenDictionary<StateId, Color> ColorShift =
        new Dictionary<StateId, Color>
        {
            [StateId.Frozen] = new Color(0.6f, 0.8f, 1.0f, 1.0f),
        }.ToFrozenDictionary();

    public static readonly FrozenDictionary<StateId, FlashConfig> Flash =
        new Dictionary<StateId, FlashConfig>
        {
            [StateId.Burning] = new(0.3f, new Color(1.0f, 0.6f, 0.0f)),
            [StateId.Electrified] = new(0.5f, new Color(1.0f, 1.0f, 0.3f)),
        }.ToFrozenDictionary();

    public static readonly FrozenDictionary<StateId, LightConfig> Lights =
        new Dictionary<StateId, LightConfig>
        {
            [StateId.Burning] = new(new Color(1.0f, 0.5f, 0.0f), 0.8f, 64.0f),
        }.ToFrozenDictionary();

    public static readonly FrozenDictionary<StateId, string> ShaderStates =
        new Dictionary<StateId, string>
        {
            [StateId.Frozen] = "ice",
        }.ToFrozenDictionary();

    public static readonly FrozenDictionary<StateId, Color> StateColors =
        new Dictionary<StateId, Color>
        {
            [StateId.Burning] = new Color(1.0f, 0.5f, 0.0f),
            [StateId.Frozen] = new Color(0.4f, 0.7f, 1.0f),
            [StateId.Wet] = new Color(0.3f, 0.5f, 1.0f),
            [StateId.Electrified] = new Color(1.0f, 1.0f, 0.2f),
        }.ToFrozenDictionary();

    public static readonly Color HealColor = new(0.3f, 1.0f, 0.3f);

    /// <summary>
    /// Per-state color with fallback. Returns <see cref="Colors.White"/>
    /// when the state has no entry in <see cref="StateColors"/> (e.g.
    /// <see cref="StateId.None"/>).
    /// </summary>
    public static Color GetStateColorOrWhite(StateId state) =>
        StateColors.TryGetValue(state, out var c) ? c : Colors.White;

    /// <summary>Per-state color with a caller-supplied fallback.</summary>
    public static Color GetStateColorOr(StateId state, Color fallback) =>
        StateColors.TryGetValue(state, out var c) ? c : fallback;

    // --- State mechanics constants (shared by game_object + player) ---------

    public const float BURNING_DOT = 5.0f;
    public const float BURNING_TICK = 1.0f;
    public const float BURNING_DURATION = 10.0f;
    public const float ELECTRIFIED_DOT = 8.0f;
    public const float ELECTRIFIED_TICK = 1.5f;
    public const float ELECTRIFIED_DURATION = 8.0f;
    public const float WET_SPEED_MULT = 0.5f;
    public const float FROZEN_DAMAGE_MULT = 2.0f;

    // --- Physics-derived visual thresholds ----------------------------------
    // These aren't state-based — they're derived from blueprint physics values
    // at creation time.
    public const int BOBBING_GRAVITY_THRESHOLD = 25;   // gravity < 25 -> bobbing
    public const bool BREATHING_AUTONOMOUS = true;     // autonomous == true -> breathing
    public const int SQUASH_BOUNCE_THRESHOLD = 60;     // bounce > 60 -> squash/stretch

}
