using System.Collections.Generic;
using Godot;
using Makeshift.Data;
using Makeshift.Models;

namespace Makeshift.Autoloads;

/// <summary>
/// Client-side cache for object behaviors, keyed by a normalized
/// <c>(subject, target)</c> tuple.
/// </summary>
public sealed partial class InteractionCache : Node
{
    public static InteractionCache Instance { get; private set; } = null!;

    private readonly Dictionary<(string Subject, string Target), BehaviorEntry> _behavior = new();

    public override void _EnterTree()
    {
        Instance = this;
    }

    // --- Key normalization ---------------------------------------------------

    private static string Normalize(string name)
    {
        var parts = name.Trim().ToLowerInvariant().Split(' ', System.StringSplitOptions.RemoveEmptyEntries);
        return string.Join(" ", parts);
    }

    private static (string Subject, string Target) Key(string subject, string target)
        => (Normalize(subject), Normalize(target));

    // --- Typed C# API --------------------------------------------------------

    public void StoreBehavior(string subject, string target, BehaviorEntry entry)
    {
        _behavior[Key(subject, target)] = entry;
    }

    public BehaviorEntry? LookupBehavior(string subjectName, string targetName)
    {
        return _behavior.TryGetValue(Key(subjectName, targetName), out var entry) ? entry : null;
    }

    /// <summary>
    /// Drop every cached behavior pair. Intended for level/session resets so
    /// the cache doesn't grow unbounded across runs. The cache outlives a
    /// single session because <see cref="InteractionCache"/> is an autoload.
    /// TODO (Wave 4): wire this into <c>Game.cs</c> on level reset — no
    /// session-start signal exists on <see cref="EventBus"/> yet.
    /// </summary>
    public void ClearAll()
    {
        _behavior.Clear();
    }

}
