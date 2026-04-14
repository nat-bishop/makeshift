using Godot;
using Makeshift.Autoloads;
using Logger = Makeshift.Autoloads.Logger;
using Makeshift.Data;
using Makeshift.Interfaces;
using Makeshift.Scenes.GameObjects;
using Makeshift.Scenes.Player;

namespace Makeshift.Systems;

/// <summary>
/// Affordance system — carry and ride via a combined-sprite swap. When the
/// player picks up a game object, its visual + physics collapse into a single
/// pre-rendered combined sprite on the player. Attacking while holding throws
/// the object; pressing interact again drops it.
/// </summary>
public partial class AffordanceSystem : Node
{
    public const float INTERACT_RANGE = 64.0f;
    public const float THROW_FORCE = 600.0f;
    public const float MASS_CARRY_LIMIT = 50.0f; // kg

    // Cached StringName for hot-path group lookup inside FindNearestInteractable.
    // ObjectBehavior interns the same name separately; StringName is string-
    // interned at the engine level, so a per-class static is free.
    private static readonly StringName GameObjectsGroup = "game_objects";

    private Player _player = null!;
    private int _heldCollisionLayer;
    private int _heldCollisionMask;
    private readonly Callable _onHeldObjectFreedCallable;

    public AffordanceSystem()
    {
        _onHeldObjectFreedCallable = Callable.From(OnHeldObjectFreed);
    }

    /// <summary>Wire this system to its owning player. Called from Player._Ready.</summary>
    public void Init(Player player)
    {
        _player = player;
    }

    /// <summary>Primary interact trigger — pick up or drop.</summary>
    public void Interact()
    {
        if (_player.HeldObject is not null)
        {
            Drop();
            return;
        }

        var nearest = FindNearestInteractable();
        if (nearest is null)
        {
            return;
        }

        var aff = GetAffordance(nearest);
        if (aff == Affordance.Carry || aff == Affordance.Mount)
        {
            Acquire(nearest);
        }
    }

    private void Acquire(Node obj)
    {
        var aff = GetAffordance(obj);

        // Mass limit (carry only — mounts can be heavy)
        if (aff == Affordance.Carry && obj is RigidBody2D tooHeavy && tooHeavy.Mass > MASS_CARRY_LIMIT)
        {
            var dir = new Vector2(_player.GetFacing(), 0);
            WorldMutations.ApplyImpulse(tooHeavy, dir, 200.0f);
            return;
        }

        var tex = GetCombinedTexture(obj);
        var objName = GetObjectName(obj);
        if (tex is null)
        {
            Logger.Instance?.Warn($"AffordanceSystem: No combined sprite for '{objName}'");
            return;
        }

        // Hide and disable physics so creatures/propagation don't target it
        if (obj is Node2D node2d)
        {
            node2d.Visible = false;
        }
        if (obj is RigidBody2D rb)
        {
            _heldCollisionLayer = (int)rb.CollisionLayer;
            _heldCollisionMask = (int)rb.CollisionMask;
            rb.Freeze = true;
            rb.CollisionLayer = 0;
            rb.CollisionMask = 0;
        }

        // Auto-restore if held object is destroyed while carried
        obj.Connect(
            Node.SignalName.TreeExiting,
            _onHeldObjectFreedCallable,
            (uint)GodotObject.ConnectFlags.OneShot);

        _player.SwapToCombinedSprite(tex, obj);
        var action = aff == Affordance.Mount ? "Mounted" : "Picked up";
        Logger.Instance?.Info($"AffordanceSystem: {action} '{objName}'");
    }

    /// <summary>Hurl the currently-held object forward.</summary>
    public void ThrowHeld()
    {
        var obj = Release();
        if (obj is null)
        {
            return;
        }
        var facing = _player.GetFacing();
        if (obj is Node2D node2d)
        {
            node2d.GlobalPosition = _player.GlobalPosition + new Vector2(facing * 40, -10);
        }
        if (obj is RigidBody2D rb)
        {
            var throwDir = new Vector2(facing, -0.3f).Normalized();
            rb.ApplyCentralImpulse(throwDir * THROW_FORCE);
        }
        Logger.Instance?.Info($"AffordanceSystem: Threw '{GetObjectName(obj)}'");
    }

    private void Drop()
    {
        var obj = Release();
        if (obj is null)
        {
            return;
        }
        var facing = _player.GetFacing();
        if (obj is Node2D node2d)
        {
            node2d.GlobalPosition = _player.GlobalPosition + new Vector2(facing * 40, 0);
        }
        Logger.Instance?.Info($"AffordanceSystem: Dropped '{GetObjectName(obj)}'");
    }

    private Node? Release()
    {
        var obj = _player.RestoreOriginalSprite();
        if (obj is null || !GodotObject.IsInstanceValid(obj))
        {
            return null;
        }

        // Disconnect destruction watcher
        if (obj.IsConnected(Node.SignalName.TreeExiting, _onHeldObjectFreedCallable))
        {
            obj.Disconnect(Node.SignalName.TreeExiting, _onHeldObjectFreedCallable);
        }

        // Restore visibility and physics
        if (obj is Node2D node2d)
        {
            node2d.Visible = true;
        }
        if (obj is RigidBody2D rb)
        {
            rb.Freeze = false;
            rb.CollisionLayer = (uint)_heldCollisionLayer;
            rb.CollisionMask = (uint)_heldCollisionMask;
        }
        return obj;
    }

    private void OnHeldObjectFreed()
    {
        _player.RestoreOriginalSprite();
        Logger.Instance?.Info("AffordanceSystem: Held object destroyed, restored player sprite");
    }

    // --- Helpers -------------------------------------------------------------

    /// <summary>
    /// Returns the target's carry/mount/climb affordance. Only
    /// <see cref="GameObject"/> has an affordance; anything else is inert.
    /// </summary>
    private static Affordance GetAffordance(Node obj) =>
        obj is GameObject go ? go.Affordance : Affordance.None;

    private static Texture2D? GetCombinedTexture(Node obj)
    {
        if (obj is not GameObject go)
        {
            return null;
        }

        if (go.CombinedTexture is { } tex)
        {
            return tex;
        }

        // Fall back to buffered cache (texture arrived before object was placed)
        var objectId = go.ObjectId;
        if (string.IsNullOrEmpty(objectId))
        {
            return null;
        }

        var cached = Backend.Instance?.GetCombinedSprite(objectId);
        if (cached is not null)
        {
            go.CombinedTexture = cached;
        }
        return cached;
    }

    private static string GetObjectName(Node obj)
    {
        if (obj is IObjectNamed named)
        {
            return named.GetObjectName();
        }
        return obj.Name.ToString();
    }

    private Node? FindNearestInteractable()
    {
        Node? best = null;
        var bestDist = INTERACT_RANGE;
        foreach (var node in _player.GetTree().GetNodesInGroup(GameObjectsGroup))
        {
            if (!GodotObject.IsInstanceValid(node) || node is not Node2D node2d)
            {
                continue;
            }
            var dist = _player.GlobalPosition.DistanceTo(node2d.GlobalPosition);
            if (dist >= bestDist)
            {
                continue;
            }
            var aff = GetAffordance(node);
            if (aff == Affordance.Carry || aff == Affordance.Mount)
            {
                best = node;
                bestDist = dist;
            }
        }
        return best;
    }
}
