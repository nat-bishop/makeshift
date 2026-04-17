using System;
using Godot;
using Makeshift.Data;
using Makeshift.Interfaces;
using Timer = Godot.Timer;

namespace Makeshift.Systems;

/// <summary>
/// World-mutation primitives. All game-state mutations route through here,
/// dispatching on <see cref="IDamageable"/>, <see cref="IHealable"/>,
/// <see cref="IStateful"/>, and <see cref="IImpulsable"/>.
/// </summary>
public static class WorldMutations
{
    private const float Gravity = 980.0f;
    private const float MaxVelocity = 800.0f;

    // ------------------------------------------------------------------ damage

    public static void ApplyDamage(Node target, float amount) =>
        ApplyDamage(target, amount, Colors.White);

    public static void ApplyDamage(Node target, float amount, Color elementColor)
    {
        if (target is IDamageable d)
        {
            d.TakeDamage(amount, elementColor);
        }
    }

    // ------------------------------------------------------------------- heal

    public static void ApplyHeal(Node target, float amount)
    {
        if (target is IHealable h)
        {
            h.Heal(amount);
        }
    }

    // ----------------------------------------------------------------- state

    public static void ApplyAddState(Node target, StateId state, float duration = 0.0f)
    {
        if (target is IStateful s)
        {
            // Directed contradictions are enforced inside StateManager.AddState().
            s.AddState(state, duration);
        }
    }

    public static void ApplyRemoveState(Node target, StateId state)
    {
        if (target is IStateful s)
        {
            s.RemoveState(state);
        }
    }

    // --------------------------------------------------------------- impulse

    public static void ApplyImpulse(Node target, Vector2 direction, float magnitude)
    {
        var impulse = direction * magnitude;
        if (target is RigidBody2D body)
        {
            body.ApplyCentralImpulse(impulse);
            ClampVelocity(body);
        }
        else if (target is IImpulsable i)
        {
            i.ApplyExternalImpulse(impulse);
        }
    }

    // ----------------------------------------------------------------- force

    public static void ApplyMovementForce(
        RigidBody2D body,
        Vector2 direction,
        float maxSpeed,
        float forceMagnitude)
    {
        var currentSpeed = body.LinearVelocity.Dot(direction);
        if (currentSpeed >= maxSpeed)
        {
            return;
        }
        var speedRatio = Math.Clamp(currentSpeed / maxSpeed, 0.0f, 1.0f);
        var scaledForce = forceMagnitude * (1.0f - speedRatio);
        var compensated = FrictionCompensated(body, scaledForce);
        body.ApplyCentralForce(direction * compensated);
    }

    public static void ApplyContinuousForce(Node target, Vector2 direction, float magnitude)
    {
        if (target is RigidBody2D body)
        {
            var compensated = FrictionCompensated(body, magnitude);
            body.ApplyCentralForce(direction * compensated);
        }
        else if (target is IImpulsable i)
        {
            var dt = 1.0f / Engine.PhysicsTicksPerSecond;
            i.ApplyExternalImpulse(direction * magnitude * dt);
        }
    }

    public static float FrictionCompensated(RigidBody2D body, float desiredMagnitude)
    {
        var gravScale = MathF.Abs((float)body.GravityScale);
        if (gravScale < 0.1f)
        {
            return desiredMagnitude * (float)body.Mass;
        }
        var friction = 1.0f;
        if (body.PhysicsMaterialOverride is { } mat)
        {
            friction = MathF.Max((float)mat.Friction, friction);
        }
        var weight = (float)body.Mass * Gravity * gravScale;
        var frictionForce = friction * weight;
        var signF = MathF.Sign(desiredMagnitude);
        return signF * (frictionForce + MathF.Abs(desiredMagnitude) * (float)body.Mass);
    }

    private static void ClampVelocity(RigidBody2D body)
    {
        var vel = body.LinearVelocity;
        if (vel.LengthSquared() > MaxVelocity * MaxVelocity)
        {
            body.LinearVelocity = vel.Normalized() * MaxVelocity;
        }
    }

    // ------------------------------------------------------------- projectile

    /// <summary>
    /// Fire a projectile from <paramref name="firer"/> toward
    /// <paramref name="towardPos"/>. Looks up the named projectile blueprint
    /// (delivered earlier via <c>projectile_ready</c>); returns false if it
    /// isn't cached yet so the caller can leave its action timer at zero and
    /// try again next physics tick.
    /// </summary>
    public static bool SpawnProjectile(
        RigidBody2D firer,
        string projectileName,
        Vector2 towardPos,
        float damage,
        StateAction stateAction,
        StateId stateId)
    {
        var tree = firer.GetTree();
        var worldNode = tree?.GetFirstNodeInGroup("world");
        if (worldNode is not IWorld world)
        {
            return false;
        }
        return world.SpawnProjectile(
            firer,
            projectileName,
            firer.GlobalPosition,
            towardPos,
            damage,
            stateAction,
            stateId);
    }

    // -------------------------------------------------------------------- dot

    /// <summary>
    /// Apply a damage-over-time effect: deals <paramref name="damagePerTick"/>
    /// every <paramref name="tickInterval"/> seconds for <paramref name="duration"/>
    /// seconds. A child <see cref="Timer"/> named <paramref name="timerName"/>
    /// is parented under <paramref name="target"/>. Restarting the same timer
    /// name cancels any in-flight DOT first.
    /// </summary>
    public static void ApplyDot(
        Node target,
        float damagePerTick,
        float tickInterval,
        float duration,
        Color? elementColor = null,
        string timerName = "_dot_timer")
    {
        if (target is not IDamageable)
        {
            return;
        }
        if (tickInterval <= 0.0f || duration <= 0.0f)
        {
            return;
        }

        var color = elementColor ?? Colors.White;
        StopDot(target, timerName);

        var timer = new Timer
        {
            Name = timerName,
            WaitTime = tickInterval,
            OneShot = false,
        };
        target.AddChild(timer);

        var ticksLeft = (int)(duration / tickInterval);
        timer.Timeout += () =>
        {
            // Both captures must be checked every tick — either can be freed
            // mid-DOT (target dies, timer is queue_free'd by a parallel call).
            if (!GodotObject.IsInstanceValid(timer) || !GodotObject.IsInstanceValid(target))
            {
                return;
            }
            if (--ticksLeft <= 0)
            {
                timer.Stop();
                timer.QueueFree();
                return;
            }
            ApplyDamage(target, damagePerTick, color);
        };
        timer.Start();
    }

    public static void StopDot(Node target, string timerName = "_dot_timer")
    {
        var existing = target.GetNodeOrNull(timerName);
        if (existing is Timer t)
        {
            t.Stop();
            t.QueueFree();
        }
        else if (existing is not null)
        {
            existing.QueueFree();
        }
    }

}
