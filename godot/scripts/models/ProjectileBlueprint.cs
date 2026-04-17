namespace Makeshift.Models;

/// <summary>
/// Client view of the backend <c>ProjectileBlueprint</c>. Delivered via a
/// <see cref="ProjectileReadyMessage"/> when the firer's behaviors are
/// resolved with <c>delivery=projectile</c>. Cached in <c>Backend</c> by
/// normalized name and looked up at spawn time by <c>ObjectBehavior</c>.
/// </summary>
public sealed record ProjectileBlueprint
{
    public string Name { get; init; } = "";
    public string VisualDescription { get; init; } = "";
    public PhysicsData Physics { get; init; } = new();
    public string SpriteUrl { get; init; } = "";
}
