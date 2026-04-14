namespace Makeshift.Data;

// Wire-format integer values are load-bearing: backend sends these as ints in
// Blueprint / BehaviorEntry payloads. Do NOT reorder without backend changes.

/// <summary>Object-level movement intent from a behavior pair.</summary>
public enum Movement
{
    Approach = 0,
    Flee = 1,
    Ignore = 2,
}

/// <summary>Primary action kind executed on contact.</summary>
public enum ActionKind
{
    None = 0,
    Damage = 1,
    Heal = 2,
    Consume = 3,
    Push = 4,
}

/// <summary>State modifier action attached to a behavior pair.</summary>
public enum StateAction
{
    None = 0,
    Add = 1,
    Remove = 2,
}

/// <summary>
/// Canonical state ids — index matches <see cref="StateContradictions.STATE_NAMES"/>:
/// ["", "burning", "frozen", "wet", "electrified"].
/// </summary>
public enum StateId
{
    None = 0,
    Burning = 1,
    Frozen = 2,
    Wet = 3,
    Electrified = 4,
}

/// <summary>Carry / mount / climb affordance.</summary>
public enum Affordance
{
    Carry = 0,
    Mount = 1,
    Climb = 2,
    None = 3,
}

/// <summary>Durability tier. Integer mapping must match the backend wire format.</summary>
public enum Durability
{
    Fragile = 0,
    Weak = 1,
    Normal = 2,
    Sturdy = 3,
    Tough = 4,
    Reinforced = 5,
    Indestructible = 6,
}

/// <summary>Autonomous movement speed tier.</summary>
public enum SpeedTier
{
    Sluggish = 0,
    Slow = 1,
    Normal = 2,
    Fast = 3,
    Rapid = 4,
}

/// <summary>Surface friction tier used by PhysicsData.</summary>
public enum Surface
{
    Slippery = 0,
    Normal = 1,
    Sticky = 2,
}
