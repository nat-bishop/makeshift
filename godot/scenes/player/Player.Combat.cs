using Godot;
using Makeshift.Autoloads;
using Logger = Makeshift.Autoloads.Logger;
using Makeshift.Scenes.GameObjects;
using Makeshift.Systems;

namespace Makeshift.Scenes.Player;

/// <summary>
/// Kick combat — shape-cast in front of the player, apply impulse and damage
/// to every rigid body hit (<see cref="GameObject.IsHeavy"/> objects keep
/// their position but still take damage).
/// </summary>
public partial class Player
{
    private void ProcessKick(float delta)
    {
        if (_kickCooldownTimer > 0.0f)
        {
            _kickCooldownTimer -= delta;
        }

        if (Input.IsActionJustPressed(KickAction) && _kickCooldownTimer <= 0.0f)
        {
            if (HeldObject is not null && _affordance is not null)
            {
                _affordance.ThrowHeld();
            }
            else
            {
                PerformKick();
            }
            _kickCooldownTimer = KICK_COOLDOWN;
        }
    }

    private void PerformKick()
    {
        _state = State.Kick;
        _animSprite.Play("kick");

        var spaceState = GetWorld2D().DirectSpaceState;
        _kickQuery.Transform = new Transform2D(
            0.0f,
            GlobalPosition + new Vector2(_facing * KICK_RANGE * 0.5f, 0.0f));

        var results = spaceState.IntersectShape(_kickQuery, 8);
        if (results.Count == 0)
        {
            Logger.Instance?.Debug("Player: Kick whiffed — nothing in range");
            return;
        }

        var kickDir = new Vector2(_facing, -0.3f).Normalized();
        foreach (var result in results)
        {
            var colliderVariant = result["collider"];
            var collider = colliderVariant.As<GodotObject>();
            if (collider is not RigidBody2D rb)
            {
                continue;
            }

            // Heavy objects resist the impulse but still take damage.
            bool isHeavy = rb is GameObject heavyGo && heavyGo.IsHeavy();
            if (!isHeavy)
            {
                rb.ApplyCentralImpulse(kickDir * KICK_FORCE);
            }
            WorldMutations.ApplyDamage(rb, KICK_DAMAGE);
            var kickedName = rb is Makeshift.Interfaces.IObjectNamed named
                ? named.GetObjectName()
                : rb.Name.ToString();
            Logger.Instance?.Info($"Player: Kicked '{kickedName}'");
        }
    }
}
