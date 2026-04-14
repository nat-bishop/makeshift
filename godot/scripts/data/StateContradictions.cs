using System.Collections.Frozen;
using System.Collections.Generic;

namespace Makeshift.Data;

/// <summary>
/// Directed state contradictions: adding the key removes all values.
/// e.g. adding "burning" removes both "frozen" and "wet",
/// but adding "wet" only removes "burning".
/// "electrified" has no contradictions — can stack with anything.
/// </summary>
public static class StateContradictions
{
    /// <summary>
    /// Canonical state ID → name mapping. Index matches <see cref="StateId"/>.
    /// [0]=None, [1]=burning, [2]=frozen, [3]=wet, [4]=electrified.
    /// </summary>
    public static readonly string[] STATE_NAMES =
    [
        "",
        "burning",
        "frozen",
        "wet",
        "electrified",
    ];

    /// <summary>
    /// Directed removal table keyed by <see cref="StateId"/>.
    /// Adding the key state removes every state in the value array.
    /// </summary>
    public static readonly FrozenDictionary<StateId, StateId[]> Removes =
        new Dictionary<StateId, StateId[]>
        {
            [StateId.Burning] = [StateId.Frozen, StateId.Wet],
            [StateId.Frozen] = [StateId.Burning],
            [StateId.Wet] = [StateId.Burning],
        }.ToFrozenDictionary();

    /// <summary>
    /// Returns the list of states that must be removed when adding
    /// <paramref name="adding"/>. Empty when the state has no contradictions.
    /// </summary>
    public static StateId[] GetRemovals(StateId adding)
    {
        return Removes.TryGetValue(adding, out var removals) ? removals : [];
    }

    /// <summary>
    /// Human-readable name for a <see cref="StateId"/>. Unknown ids return "".
    /// </summary>
    public static string GetName(StateId state)
    {
        var idx = (int)state;
        return idx >= 0 && idx < STATE_NAMES.Length ? STATE_NAMES[idx] : string.Empty;
    }

    /// <summary>
    /// Reverse lookup: state name → <see cref="StateId"/>. Unknown names return
    /// <see cref="StateId.None"/>.
    /// </summary>
    public static StateId NameToId(string name) =>
        name switch
        {
            "burning" => StateId.Burning,
            "frozen" => StateId.Frozen,
            "wet" => StateId.Wet,
            "electrified" => StateId.Electrified,
            _ => StateId.None,
        };
}
