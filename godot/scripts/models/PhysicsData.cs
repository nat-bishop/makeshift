using Makeshift.Data;

namespace Makeshift.Models;

/// <summary>LLM-generated physics for a <see cref="Blueprint"/>.</summary>
public sealed record PhysicsData
{
    public float MassKg { get; init; } = 1.0f;
    public int HeightCm { get; init; } = 30;
    public Surface Surface { get; init; } = Surface.Normal;
    public int Bounce { get; init; } = 10;
    public int Gravity { get; init; } = 50;
}
