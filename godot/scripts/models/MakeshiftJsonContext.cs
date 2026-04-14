using System.Text.Json;
using System.Text.Json.Serialization;

namespace Makeshift.Models;

/// <summary>
/// Source-generated JsonSerializerContext for backend payloads.
/// Global snake_case policy converts C# PascalCase members to backend
/// snake_case wire names automatically — no per-field [JsonPropertyName].
///
/// Wire-format integer enums stay as integers (default behavior for
/// [JsonSerializable]). DO NOT add [JsonStringEnumConverter] here — backend
/// sends state_action / state_id / movement / action as ints.
/// </summary>
[JsonSourceGenerationOptions(
    PropertyNamingPolicy = JsonKnownNamingPolicy.SnakeCaseLower,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull)]
[JsonSerializable(typeof(Blueprint))]
[JsonSerializable(typeof(BehaviorEntry))]
[JsonSerializable(typeof(BehaviorEntry[]))]
[JsonSerializable(typeof(PhysicsData))]
[JsonSerializable(typeof(VisualDescriptor))]
[JsonSerializable(typeof(WsMessage))]
[JsonSerializable(typeof(SpriteReadyMessage))]
[JsonSerializable(typeof(SpriteFailedMessage))]
[JsonSerializable(typeof(CombinedSpriteReadyMessage))]
[JsonSerializable(typeof(DestructionSpriteReadyMessage))]
[JsonSerializable(typeof(BehaviorsReadyMessage))]
[JsonSerializable(typeof(BehaviorUpdatedMessage))]
[JsonSerializable(typeof(WsErrorMessage))]
internal partial class MakeshiftJsonContext : JsonSerializerContext { }
