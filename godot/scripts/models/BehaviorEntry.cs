using System.Text.Json.Serialization;
using Makeshift.Data;

namespace Makeshift.Models;

/// <summary>
/// Per subject x target behavioral data loaded into InteractionCache. Enum
/// fields serialize as their underlying ints to match the backend wire format.
/// </summary>
public sealed record BehaviorEntry
{
    /// <summary>
    /// Canonical target name. Serialized as <c>target_name</c> to match the
    /// backend wire format. <see cref="BehaviorEntryMarshal"/> also accepts an
    /// alternate <c>target</c> key on the Godot.Dictionary path.
    /// </summary>
    [JsonPropertyName("target_name")]
    public string Target { get; init; } = "";

    public Movement Movement { get; init; } = Movement.Ignore;
    public int Priority { get; init; }
    public ActionKind Action { get; init; } = ActionKind.None;
    public int Amount { get; init; }
    public StateAction StateAction { get; init; } = StateAction.None;
    public StateId StateId { get; init; } = StateId.None;
    public int Force { get; init; }
}
