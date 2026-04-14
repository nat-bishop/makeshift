using Godot;

namespace Makeshift.Interfaces;

/// <summary>Accepts an external impulse (knockback / push).</summary>
public interface IImpulsable
{
    void ApplyExternalImpulse(Vector2 impulse);
}
