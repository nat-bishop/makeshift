using Godot;

namespace Makeshift.Models;

/// <summary>
/// Typed extension helpers for <see cref="Godot.Collections.Dictionary"/>.
/// Consolidates the <c>(T)dict.GetValueOrDefault(key, fallback)</c> pattern
/// that's duplicated across Backend / Game / ObjectCreationPanel / ObjectVisual /
/// BehaviorEntryMarshal, avoiding per-site casts.
/// </summary>
public static class GodotDictExt
{
    /// <summary>Read a string value, or <paramref name="fallback"/> when missing.</summary>
    public static string GetStringOrDefault(
        this Godot.Collections.Dictionary dict,
        string key,
        string fallback = "")
    {
        return dict.TryGetValue(key, out var v) ? v.AsString() : fallback;
    }

    /// <summary>Read an int value, or <paramref name="fallback"/> when missing.</summary>
    public static int GetIntOrDefault(
        this Godot.Collections.Dictionary dict,
        string key,
        int fallback = 0)
    {
        return dict.TryGetValue(key, out var v) ? v.AsInt32() : fallback;
    }

    /// <summary>Read a float value, or <paramref name="fallback"/> when missing.</summary>
    public static float GetFloatOrDefault(
        this Godot.Collections.Dictionary dict,
        string key,
        float fallback = 0f)
    {
        return dict.TryGetValue(key, out var v) ? (float)v.AsDouble() : fallback;
    }

    /// <summary>Read a bool value, or <paramref name="fallback"/> when missing.</summary>
    public static bool GetBoolOrDefault(
        this Godot.Collections.Dictionary dict,
        string key,
        bool fallback = false)
    {
        return dict.TryGetValue(key, out var v) ? v.AsBool() : fallback;
    }
}
