using System.Text.Json.Serialization;

namespace Makeshift.Models;

/// <summary>
/// Base type for incoming WebSocket messages from the backend.
/// Discriminated by the <c>type</c> field.
/// </summary>
[JsonPolymorphic(TypeDiscriminatorPropertyName = "type")]
[JsonDerivedType(typeof(SpriteReadyMessage), "sprite_ready")]
[JsonDerivedType(typeof(SpriteFailedMessage), "sprite_failed")]
[JsonDerivedType(typeof(CombinedSpriteReadyMessage), "combined_sprite_ready")]
[JsonDerivedType(typeof(DestructionSpriteReadyMessage), "destruction_sprite_ready")]
[JsonDerivedType(typeof(BehaviorsReadyMessage), "behaviors_ready")]
[JsonDerivedType(typeof(BehaviorUpdatedMessage), "behavior_updated")]
[JsonDerivedType(typeof(ProjectileReadyMessage), "projectile_ready")]
[JsonDerivedType(typeof(WsErrorMessage), "error")]
public abstract record WsMessage;

/// <summary>Main object sprite is ready at <see cref="SpriteUrl"/>.</summary>
public sealed record SpriteReadyMessage : WsMessage
{
    public string ObjectId { get; init; } = "";
    public string SpriteUrl { get; init; } = "";
}

/// <summary>Sprite generation failed; <see cref="Reason"/> is free-form.</summary>
public sealed record SpriteFailedMessage : WsMessage
{
    public string ObjectId { get; init; } = "";
    public string Reason { get; init; } = "";
}

/// <summary>Combined player+object carry/ride sprite is ready.</summary>
public sealed record CombinedSpriteReadyMessage : WsMessage
{
    public string ObjectId { get; init; } = "";
    public string SpriteUrl { get; init; } = "";
}

/// <summary>Destruction-debris sprite ready, keyed by debris name.</summary>
public sealed record DestructionSpriteReadyMessage : WsMessage
{
    public string DestructionResultName { get; init; } = "";
    public string SpriteUrl { get; init; } = "";
}

/// <summary>Initial behavior batch for a subject.</summary>
public sealed record BehaviorsReadyMessage : WsMessage
{
    public string SubjectName { get; init; } = "";
    public BehaviorEntry[] Behaviors { get; init; } = [];
}

/// <summary>Behavior hot-swap after re-evaluation.</summary>
public sealed record BehaviorUpdatedMessage : WsMessage
{
    public string SubjectName { get; init; } = "";
    public BehaviorEntry[] Behaviors { get; init; } = [];
}

/// <summary>Projectile blueprint ready — cache by name for later spawn requests.</summary>
public sealed record ProjectileReadyMessage : WsMessage
{
    public ProjectileBlueprint Projectile { get; init; } = new();
}

/// <summary>Generic WS error channel.</summary>
public sealed record WsErrorMessage : WsMessage
{
    public string Message { get; init; } = "";
}
