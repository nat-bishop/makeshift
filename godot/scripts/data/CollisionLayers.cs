namespace Makeshift.Data;

/// <summary>
/// Physics-layer bitmask constants. Values are powers-of-two, matching the
/// Godot project layer assignments (Layer 1 = bit 1, Layer 2 = bit 2, etc).
/// </summary>
public static class CollisionLayers
{
    public const int Terrain = 1;   // Layer 1 bitmask
    public const int Player = 2;    // Layer 2 bitmask
    public const int Objects = 4;   // Layer 3 bitmask
    public const int Hazards = 8;   // Layer 4 bitmask
    public const int Triggers = 16; // Layer 5 bitmask
}
