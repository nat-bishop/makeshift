using Makeshift.Data;

namespace Makeshift.Models;

/// <summary>
/// Client-side view of a backend <c>GameObjectBlueprint</c>. Field names and
/// defaults match the backend wire format so the record round-trips cleanly
/// through <see cref="MakeshiftJsonContext"/>.
/// </summary>
public sealed record Blueprint
{
    public required string Id { get; init; }
    public required string Name { get; init; }

    public string Description { get; init; } = "";
    public string VisualDescription { get; init; } = "";

    public Durability Durability { get; init; } = Durability.Normal;
    public Affordance Affordance { get; init; } = Affordance.None;
    public bool Active { get; init; }
    public SpeedTier Speed { get; init; } = SpeedTier.Normal;
    public string DestructionResultName { get; init; } = "";

    public StateId[] InitialStates { get; init; } = [];
    public StateId[] SusceptibleStates { get; init; } = [];

    public PhysicsData Physics { get; init; } = new();

    public string[] Tags { get; init; } = [];
    public BehaviorEntry[] Behaviors { get; init; } = [];
    public VisualDescriptor VisualDescriptor { get; init; } = new();

    public bool HasField { get; init; }
    public int FieldRangeCm { get; init; }
}
