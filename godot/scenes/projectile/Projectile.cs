using Godot;
using Makeshift.Autoloads;
using Logger = Makeshift.Autoloads.Logger;
using Makeshift.Data;
using Makeshift.Interfaces;
using Makeshift.Models;
using Makeshift.Systems;
using Timer = Godot.Timer;

namespace Makeshift.Scenes.Projectiles;

/// <summary>
/// Fired by an active object's <see cref="ObjectBehavior"/> when a behavior
/// resolves with delivery=projectile. Carries damage + optional state effect
/// as a flying RigidBody2D; on impact it applies them to the first body it
/// hits (other than the firer) and despawns. Knockback comes from the
/// engine's collision response (mass × velocity transfers at impact).
/// </summary>
public partial class Projectile : RigidBody2D
{
    public const float MaxLifetime = 5.0f;
    public const float LaunchImpulse = 1000.0f;
    public const float SpawnOffset = 32.0f;

    public string ProjectileName { get; private set; } = "";
    public RigidBody2D? Firer { get; private set; }
    public float Damage { get; private set; }
    public StateAction StateAction { get; private set; }
    public StateId StateId { get; private set; }

    public void InitProjectile(
        ProjectileBlueprint bp,
        Texture2D? texture,
        RigidBody2D firer,
        Vector2 fromPos,
        Vector2 towardPos,
        float damage,
        StateAction stateAction,
        StateId stateId)
    {
        ProjectileName = bp.Name;
        Firer = firer;
        Damage = damage;
        StateAction = stateAction;
        StateId = stateId;

        // Physics: mass + gravity from the blueprint, no damping (clean flight).
        var scale = PhysicsComposer.ScaleFromHeight(bp.Physics.HeightCm);
        Mass = Mathf.Max(bp.Physics.MassKg * scale, 0.1f);
        GravityScale = PhysicsComposer.GravityToScale(bp.Physics.Gravity);
        LinearDamp = 0.0f;
        AngularDamp = 0.0f;
        PhysicsMaterialOverride = new PhysicsMaterial { Friction = 0.5f, Bounce = 0.0f };

        ContactMonitor = true;
        MaxContactsReported = 4;
        CollisionLayer = (uint)CollisionLayers.Hazards;
        CollisionMask = (uint)(CollisionLayers.Terrain | CollisionLayers.Player | CollisionLayers.Objects);

        // Sprite — sized down vs the firer's projectile-blueprint height so a
        // missile sprite doesn't end up the size of the helicopter that fired it.
        var visualSize = PhysicsComposer.WorldSpriteSize(bp.Physics.HeightCm);
        var sprite = new Sprite2D { Name = "Sprite2D", Texture = texture };
        if (texture is not null)
        {
            var texW = texture.GetWidth();
            if (texW > 0)
            {
                sprite.Scale = Vector2.One * (visualSize / texW);
            }
        }
        AddChild(sprite);

        var shape = new CollisionShape2D
        {
            Name = "CollisionShape2D",
            Shape = new RectangleShape2D { Size = new Vector2(visualSize * 0.6f, visualSize * 0.6f) },
        };
        AddChild(shape);

        // Aim and offset spawn position so the projectile doesn't immediately
        // overlap the firer's collision shape (which would emit BodyEntered
        // synchronously with the firer as the target).
        var dir = (towardPos - fromPos).Normalized();
        if (dir.LengthSquared() < 0.0001f)
        {
            dir = Vector2.Right;
        }
        GlobalPosition = fromPos + dir * SpawnOffset;
        sprite.Rotation = dir.Angle();

        // Launch! Velocity = LaunchImpulse / Mass — heavy projectiles fly slow,
        // light ones fly fast, and impact knockback (mass × velocity) is the
        // same for both. Physical and consistent without per-projectile tuning.
        ApplyCentralImpulse(dir * LaunchImpulse);

        BodyEntered += OnBodyEntered;

        var lifetime = new Timer
        {
            Name = "Lifetime",
            WaitTime = MaxLifetime,
            OneShot = true,
        };
        AddChild(lifetime);
        lifetime.Timeout += () =>
        {
            if (IsInstanceValid(this))
            {
                QueueFree();
            }
        };
        lifetime.Start();
    }

    private void OnBodyEntered(Node body)
    {
        if (Firer is not null && IsInstanceValid(Firer) && body == Firer)
        {
            return;
        }

        if (body is IDamageable d)
        {
            var lethal = Damage >= ObjectBehavior.LethalThreshold
                ? ObjectBehavior.InstantKillDamage
                : (Damage > 0 ? Damage : 15.0f);
            d.TakeDamage(lethal, Colors.White);
        }

        if (StateAction != StateAction.None && StateId != StateId.None && body is IStateful s)
        {
            if (StateAction == StateAction.Add)
            {
                s.AddState(StateId, 10.0f);
            }
            else
            {
                s.RemoveState(StateId);
            }
        }

        Logger.Instance?.Info(
            $"Projectile: '{ProjectileName}' impacted '{(body is IObjectNamed nm ? nm.GetObjectName() : body.Name.ToString())}' (dmg={Damage})");
        QueueFree();
    }
}
