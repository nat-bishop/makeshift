using Godot;

namespace Makeshift.Interfaces;

/// <summary>Takes damage with an optional element color tint.</summary>
public interface IDamageable
{
    void TakeDamage(float amount, Color elementColor);
}
