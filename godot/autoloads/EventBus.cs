using Godot;

namespace Makeshift.Autoloads;

/// <summary>
/// Global signal hub. Uses Godot <c>[Signal]</c> delegates so listeners can
/// subscribe via either the <c>+=</c> syntax or a Callable.
/// </summary>
public sealed partial class EventBus : Node
{
    public static EventBus Instance { get; private set; } = null!;

    public override void _EnterTree()
    {
        Instance = this;
    }

    // --- Interaction / combat ------------------------------------------------

    [Signal]
    public delegate void InteractionTriggeredEventHandler(
        string sourceName,
        Godot.Collections.Array sourceTags,
        string targetName,
        Godot.Collections.Array targetTags,
        string effectMessage,
        Vector2 worldPos);

    // --- Object lifecycle ----------------------------------------------------

    [Signal]
    public delegate void ObjectCreatedEventHandler(Godot.Collections.Dictionary blueprint);

    [Signal]
    public delegate void SpriteReadyEventHandler(string objectId, Texture2D texture);

    [Signal]
    public delegate void SpriteFailedEventHandler(string objectId);

    /// <summary>Fired when the combined player+object carry sprite is ready.</summary>
    [Signal]
    public delegate void CombinedSpriteReadyEventHandler(string objectId, Texture2D texture);

    // --- Creation flow -------------------------------------------------------

    [Signal]
    public delegate void CreationRequestedEventHandler();

    [Signal]
    public delegate void CreationFailedEventHandler();

    [Signal]
    public delegate void PlacementStartedEventHandler();

    [Signal]
    public delegate void PlacementEndedEventHandler();

    // --- Level progression ---------------------------------------------------

    [Signal]
    public delegate void LevelCompletedEventHandler(int levelId);

    // --- Debug ---------------------------------------------------------------

    [Signal]
    public delegate void DebugToggledEventHandler(bool enabled);

    // --- Player events -------------------------------------------------------

    [Signal]
    public delegate void PlayerDiedEventHandler();

    [Signal]
    public delegate void PlayerDamagedEventHandler(float amount, int current, int maximum);

    [Signal]
    public delegate void PlayerHealedEventHandler(float amount, int current, int maximum);

    // --- Effects feedback ----------------------------------------------------

    [Signal]
    public delegate void EffectAppliedEventHandler(
        string effectType,
        float amount,
        Color elementColor,
        Vector2 worldPos);

    // --- Backend push --------------------------------------------------------

    [Signal]
    public delegate void BehaviorUpdatedEventHandler(string subjectName);

    /// <summary>Fired when a ProjectileBlueprint + sprite become available.</summary>
    [Signal]
    public delegate void ProjectileReadyEventHandler(string projectileName);
}
