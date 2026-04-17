using Godot;
using Makeshift.Data;

namespace Makeshift.Models;

/// <summary>
/// Bidirectional helper for <see cref="BehaviorEntry"/> &lt;-&gt;
/// <see cref="Godot.Collections.Dictionary"/> conversion, mirroring the backend
/// wire field names (<c>target_name</c>/<c>movement</c>/<c>priority</c>/
/// <c>action</c>/<c>amount</c>/<c>state_action</c>/<c>state_id</c>/
/// <c>delivery</c>/<c>projectile_name</c>).
/// </summary>
public static class BehaviorEntryMarshal
{
    /// <summary>
    /// Build a typed <see cref="BehaviorEntry"/> from a Godot dictionary using
    /// the backend snake_case wire names. Accepts either <c>target_name</c>
    /// (canonical) or <c>target</c> as a fallback. Missing keys fall back to
    /// the record's default values.
    /// </summary>
    public static BehaviorEntry FromGodotDictionary(Godot.Collections.Dictionary dict)
    {
        var target = GetString(dict, "target_name");
        if (string.IsNullOrEmpty(target))
        {
            target = GetString(dict, "target");
        }
        return new BehaviorEntry
        {
            Target = target,
            Movement = (Movement)GetInt(dict, "movement", (int)Movement.Ignore),
            Priority = GetInt(dict, "priority"),
            Action = (ActionKind)GetInt(dict, "action"),
            Amount = GetInt(dict, "amount"),
            StateAction = (StateAction)GetInt(dict, "state_action"),
            StateId = (StateId)GetInt(dict, "state_id"),
            Delivery = (Delivery)GetInt(dict, "delivery"),
            ProjectileName = GetString(dict, "projectile_name"),
        };
    }

    /// <summary>
    /// Serialize a typed <see cref="BehaviorEntry"/> back to its dictionary
    /// wire form so downstream Godot consumers (UI reveal card, debug overlay)
    /// see the same shape the backend originally delivered.
    /// </summary>
    public static Godot.Collections.Dictionary ToGodotDictionary(BehaviorEntry entry)
    {
        return new Godot.Collections.Dictionary
        {
            ["target_name"] = entry.Target,
            ["movement"] = (int)entry.Movement,
            ["priority"] = entry.Priority,
            ["action"] = (int)entry.Action,
            ["amount"] = entry.Amount,
            ["state_action"] = (int)entry.StateAction,
            ["state_id"] = (int)entry.StateId,
            ["delivery"] = (int)entry.Delivery,
            ["projectile_name"] = entry.ProjectileName,
        };
    }

    private static string GetString(Godot.Collections.Dictionary dict, string key)
    {
        return dict.TryGetValue(key, out var v) ? v.AsString() : "";
    }

    private static int GetInt(Godot.Collections.Dictionary dict, string key, int fallback = 0)
    {
        return dict.TryGetValue(key, out var v) ? (int)v.AsInt64() : fallback;
    }
}
