using Godot;
using Makeshift.Autoloads;
using Logger = Makeshift.Autoloads.Logger;
using Makeshift.Data;

namespace Makeshift.Scenes.GameObjects;

/// <summary>
/// IDamageable + IHealable implementation. Split out for file-size hygiene.
/// </summary>
public partial class GameObject
{
    public void TakeDamage(float amount, Color elementColor)
    {
        // Frozen = brittle: 2x incoming damage
        var incoming = amount;
        if (_stateManager is not null && _stateManager.HasState(StateId.Frozen))
        {
            incoming *= StateVisuals.FROZEN_DAMAGE_MULT;
        }
        CurrentHp -= (int)Mathf.Max(incoming, 1.0f); // Minimum 1 damage

        _objectVisual?.FlashHit(elementColor);

        if (CurrentHp <= 0)
        {
            Logger.Instance?.Info($"GameObject: '{ObjectName}' destroyed");
            if (!string.IsNullOrEmpty(DestructionResultName))
            {
                Backend.Instance.RequestDestructionSpawn(DestructionResultName, GlobalPosition);
            }
            QueueFree();
        }
    }

    /// <summary>
    /// IDamageable convenience overload (white element color).
    /// </summary>
    public void TakeDamage(float amount) => TakeDamage(amount, Colors.White);

    public void Heal(float amount)
    {
        CurrentHp = Mathf.Min(CurrentHp + (int)amount, MaxHp);
        _objectVisual?.FlashHit(StateVisuals.HealColor);
    }
}
