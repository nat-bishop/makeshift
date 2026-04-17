using Godot;
using Makeshift.Autoloads;
using Logger = Makeshift.Autoloads.Logger;
using Makeshift.Data;
using Makeshift.Models;
using Makeshift.Systems;

namespace Makeshift.Scenes.GameObjects;

/// <summary>
/// Reads LLM-generated <see cref="PhysicsData"/> and applies it to the parent
/// <see cref="RigidBody2D"/>. <see cref="ObjectVisual"/> calls
/// <see cref="UpdateShapeFromSprite"/> (deferred) once a sprite arrives so the
/// collision shape hugs the actual pixels.
/// </summary>
[GlobalClass]
public partial class PhysicsApplicator : Node
{
    private RigidBody2D? _body;
    private CollisionShape2D? _collisionShape;
    private bool _hasSpriteShape;

    public override void _Ready()
    {
        _body = GetParent<RigidBody2D>();
        _collisionShape = _body.GetNode<CollisionShape2D>("CollisionShape2D");
    }

    /// <summary>
    /// Apply the typed physics record. <see cref="GameObject.InitFromBlueprint"/>
    /// drives this immediately after construction.
    /// </summary>
    public void Apply(PhysicsData physics, string objectName = "?")
    {
        if (_body is null)
        {
            // _Ready() hasn't fired yet — pull parent directly to stay safe.
            _body = GetParent<RigidBody2D>();
            _collisionShape = _body.GetNode<CollisionShape2D>("CollisionShape2D");
        }

        var massKg = physics.MassKg;
        var heightCm = physics.HeightCm;
        var surface = physics.Surface;
        var bounce100 = physics.Bounce;
        var gravity100 = physics.Gravity;

        var scale = PhysicsComposer.ScaleFromHeight(heightCm);
        var sizeCat = PhysicsComposer.SizeFromHeight(heightCm);

        // Mass (real-world kg * continuous scale), clamped so an LLM-assigned
        // near-zero mass can't cause infinite knockback velocity on impact.
        _body.Mass = Mathf.Max(massKg * scale, 0.5f);

        // Gravity: piecewise linear mapping
        //   0-50 -> -1.0 to 1.0 (floating up to normal)
        //   50-100 -> 1.0 to 2.0 (normal to extra heavy)
        _body.GravityScale = GravityToScale(gravity100);

        // Damping derived from height and mass
        _body.LinearDamp = Mathf.Clamp(heightCm / (massKg * 100.0f + 10.0f), 0.0f, 10.0f);

        // Physics material
        var mat = new PhysicsMaterial();
        mat.Friction = PhysicsComposer.SurfaceFriction(surface);
        mat.Bounce = bounce100 / 100.0f;
        _body.PhysicsMaterialOverride = mat;

        // Fallback collision shape from continuous scale
        if (!_hasSpriteShape)
        {
            ConfigureShape(heightCm);
        }

        Logger.Instance?.Debug(
            $"PhysicsApplicator: '{objectName}' mass={_body.Mass:F3} gravity={_body.GravityScale:F2} " +
            $"friction={mat.Friction:F2} bounce={mat.Bounce:F2} damp={_body.LinearDamp:F2} " +
            $"size={sizeCat} scale={scale:F2}");
    }

    private static float GravityToScale(int g)
    {
        if (g <= 50)
        {
            return Mathf.Lerp(-1.0f, 1.0f, g / 50.0f);
        }
        return Mathf.Lerp(1.0f, 2.0f, (g - 50) / 50.0f);
    }

    /// <summary>
    /// Replace the fallback collision shape with one derived from the actual
    /// sprite's used pixels (so collision matches transparent edges instead
    /// of the bounding box).
    /// </summary>
    public void UpdateShapeFromSprite(Texture2D texture, float worldSize)
    {
        if (_collisionShape is null)
        {
            return;
        }

        var image = texture.GetImage();
        var usedRect = image.GetUsedRect();
        if (usedRect.Size.X == 0 || usedRect.Size.Y == 0)
        {
            return;
        }

        var texSize = (float)image.GetWidth();
        var worldScale = worldSize / texSize;

        var spriteCenter = new Vector2(texSize / 2.0f, image.GetHeight() / 2.0f);
        var rectCenter = new Vector2(
            usedRect.Position.X + usedRect.Size.X / 2.0f,
            usedRect.Position.Y + usedRect.Size.Y / 2.0f);

        var rect = new RectangleShape2D
        {
            Size = new Vector2(usedRect.Size.X, usedRect.Size.Y) * worldScale,
        };
        _collisionShape.Shape = rect;
        _collisionShape.Position = (rectCenter - spriteCenter) * worldScale;
        _hasSpriteShape = true;
    }

    private void ConfigureShape(int heightCm)
    {
        if (_collisionShape is null)
        {
            return;
        }
        var collisionSize = PhysicsComposer.WorldCollisionSize(heightCm);
        _collisionShape.Shape = new RectangleShape2D
        {
            Size = new Vector2(collisionSize, collisionSize),
        };
    }

}
