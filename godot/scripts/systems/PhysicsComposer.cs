using System;
using Godot;
using Makeshift.Data;

namespace Makeshift.Systems;

/// <summary>
/// Continuous logarithmic scaling from <c>height_cm</c>.
/// <see cref="ScaleFromHeight"/> gives smooth progression;
/// <see cref="SizeFromHeight"/> still provides category labels for debug /
/// passive-push checks.
/// </summary>
public static class PhysicsComposer
{
    /// <summary>Reference height: 100cm object = 1.0x scale.</summary>
    public const float REFERENCE_CM = 100.0f;

    /// <summary>Scale floor.</summary>
    public const float MIN_SCALE = 0.2f;

    /// <summary>Scale ceiling — keeps huge objects playable on a 2D screen.</summary>
    public const float MAX_SCALE = 4.0f;

    /// <summary>Height clamp for the log curve — minimum cm.</summary>
    public const float MIN_CM = 1.0f;

    /// <summary>Height clamp for the log curve — maximum cm.</summary>
    public const float MAX_CM = 5000.0f;

    /// <summary>Base sprite size at 1.0x scale (medium reference).</summary>
    public const float BASE_SPRITE = 72.0f;

    /// <summary>Base collision size at 1.0x scale (medium reference).</summary>
    public const float BASE_COLLISION = 56.0f;

    /// <summary>Typed friction lookup keyed by <see cref="Surface"/>.</summary>
    public static float SurfaceFriction(Surface surface) =>
        surface switch
        {
            Surface.Slippery => 0.05f,
            Surface.Normal => 0.5f,
            Surface.Sticky => 1.0f,
            _ => 0.5f,
        };

    /// <summary>
    /// Logarithmic scale: <c>log2(height/100)</c> compressed by 0.55, clamped
    /// to <see cref="MIN_SCALE"/>..<see cref="MAX_SCALE"/>.
    /// </summary>
    public static float ScaleFromHeight(int heightCm)
    {
        var h = Math.Clamp((float)heightCm, MIN_CM, MAX_CM);
        var logRatio = MathF.Log(h / REFERENCE_CM) / MathF.Log(2.0f); // log2
        // Map logRatio to scale: 0 → 1.0x, each ±1 doubles/halves
        var rawScale = MathF.Pow(2.0f, logRatio * 0.55f); // 0.55 compresses extremes
        return Math.Clamp(rawScale, MIN_SCALE, MAX_SCALE);
    }

    /// <summary>Mass multiplier derived from continuous scale.</summary>
    public static float GetSizeMassMultiplier(int heightCm) => ScaleFromHeight(heightCm);

    /// <summary>Continuous world sprite size from <paramref name="heightCm"/>.</summary>
    public static float WorldSpriteSize(int heightCm) => BASE_SPRITE * ScaleFromHeight(heightCm);

    /// <summary>Continuous world collision size from <paramref name="heightCm"/>.</summary>
    public static float WorldCollisionSize(int heightCm) => BASE_COLLISION * ScaleFromHeight(heightCm);

    /// <summary>Category label for debug display, passive push checks, etc.</summary>
    public static string SizeFromHeight(int heightCm) => heightCm switch
    {
        < 10 => "tiny",
        < 50 => "small",
        < 150 => "medium",
        < 400 => "large",
        _ => "huge",
    };

    /// <summary>
    /// Height-derived scale factor for state-propagation *radius*, intentionally
    /// narrower than <see cref="ScaleFromHeight"/>: 25cm → 0.5×, 200cm → 2.0×,
    /// clamped. Keeps very tall objects (e.g. a mountain) from propagating
    /// states across the entire level — visual/physics scale can exceed this,
    /// but propagation radius stays bounded for gameplay fairness.
    /// </summary>
    public static float PropagationRadiusFromHeight(int heightCm)
    {
        var raw = heightCm / 100.0f;
        return Math.Clamp(raw, 0.5f, 2.0f);
    }

    /// <summary>
    /// Piecewise linear map from the LLM's 0..100 gravity answer to Godot
    /// <see cref="Godot.RigidBody2D.GravityScale"/>. 0-50 maps linearly to
    /// -1.0 (helium-like rise) … 1.0 (normal fall); 50-100 continues to 2.0
    /// (extra heavy). Mirrors the backend choice_map in prompts/creation.py.
    /// </summary>
    public static float GravityToScale(int g)
    {
        if (g <= 50)
        {
            return Mathf.Lerp(-1.0f, 1.0f, g / 50.0f);
        }
        return Mathf.Lerp(1.0f, 2.0f, (g - 50) / 50.0f);
    }
}
