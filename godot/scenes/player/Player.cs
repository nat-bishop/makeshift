using System;
using Godot;
using Makeshift.Autoloads;
using Logger = Makeshift.Autoloads.Logger;
using Makeshift.Data;
using Makeshift.Interfaces;
using Makeshift.Scenes.GameObjects;
using Makeshift.Systems;

namespace Makeshift.Scenes.Player;

/// <summary>
/// Player character. Implements <see cref="IObjectNamed"/>,
/// <see cref="IDamageable"/>, <see cref="IHealable"/>, <see cref="IStateful"/>,
/// and <see cref="IImpulsable"/>. Split into <c>Player.cs</c> (core + movement
/// + lifecycle) and <c>Player.Combat.cs</c> (kick logic) — combined via
/// <c>partial</c>.
/// </summary>
[GlobalClass]
public partial class Player : CharacterBody2D, IObjectNamed, IDamageable, IHealable, IStateful, IImpulsable
{
    // --- Movement tuning -----------------------------------------------------
    public const float SPEED = 300.0f;
    public const float JUMP_VELOCITY = -400.0f;
    public const float GRAVITY = 980.0f;
    public const float PUSH_FORCE = 500.0f;            // continuous force (N)
    public const float KICK_FORCE = 400.0f;
    public const float KICK_DAMAGE = 10.0f;
    public const float KICK_RANGE = 48.0f;
    public const float KICK_HEIGHT = 32.0f;
    public const float KICK_COOLDOWN = 0.5f;
    public const float VOID_THRESHOLD = 1200.0f;
    public const int MAX_HEALTH = 100;
    public const float DAMAGE_FLASH_DURATION = 0.15f;
    public const float MOVE_ACCEL = 3000.0f;           // px/s²
    public const float EFFECTIVE_MASS = 0.4f;          // external-force resistance
    public const float KNOCKBACK_DECAY = 800.0f;
    public const float KNOCKBACK_FULL_SUPPRESSION = 1000.0f;
    public const float KNOCKBACK_MIN_CONTROL = 0.15f;
    public const float BOUNCE_ENERGY = 1.2f;
    public const float BOUNCE_MIN_SPEED = 50.0f;

    // --- Cached StringNames (avoid per-frame string→StringName conversion) ---
    private static readonly StringName MoveLeftAction = "move_left";
    private static readonly StringName MoveRightAction = "move_right";
    private static readonly StringName JumpAction = "jump";
    private static readonly StringName InteractAction = "interact";
    private static readonly StringName KickAction = "kick";

    /// <summary>Movement animation state machine.</summary>
    public enum State
    {
        Idle,
        Walk,
        Jump,
        Fall,
        Kick,
    }

    private State _state = State.Idle;
    private float _inputDirection;
    private int _facing = 1; // 1 = right, -1 = left
    private float _kickCooldownTimer;
    private PhysicsShapeQueryParameters2D _kickQuery = null!;
    private float _damageFlashTimer;
    private bool _dead;
    private Vector2 _knockback = Vector2.Zero;
    private float _speedModifier = 1.0f;
    private int _slowCount;
    private Vector2 _preSlideVelocity = Vector2.Zero;
    private System.Collections.Generic.HashSet<ulong> _prevContacts = new();
    private System.Collections.Generic.HashSet<ulong> _currentContacts = new();
    private StateManager _gameStateManager = null!;
    private bool _frozenInput;
    private Sprite2D? _combinedSprite;
    private AnimatedSprite2D _animSprite = null!;
    private AffordanceSystem? _affordance;

    /// <summary>Current hit points. Public because HUD + debug panels read it.</summary>
    public int CurrentHealth { get; private set; } = MAX_HEALTH;

    /// <summary>The game object currently being carried or ridden, if any.</summary>
    public Node? HeldObject { get; private set; }

    public override void _Ready()
    {
        AddToGroup("player");
        AddToGroup("living");

        _animSprite = GetNode<AnimatedSprite2D>("AnimatedSprite2D");

        _gameStateManager = new StateManager { Name = "GameStateManager" };
        AddChild(_gameStateManager);
        _gameStateManager.InitStates("player");
        _gameStateManager.StateAdded += OnGameStateAdded;
        _gameStateManager.StateRemoved += OnGameStateRemoved;

        var kickShape = new RectangleShape2D { Size = new Vector2(KICK_RANGE, KICK_HEIGHT) };
        _kickQuery = new PhysicsShapeQueryParameters2D
        {
            Shape = kickShape,
            CollisionMask = CollisionLayers.Objects,
            CollideWithBodies = true,
        };

        _animSprite.AnimationFinished += OnAnimationFinished;

        // Affordance system (carry/ride via sprite swap)
        _affordance = new AffordanceSystem { Name = "AffordanceSystem" };
        AddChild(_affordance);
        _affordance.Init(this);

        Logger.Instance?.Info($"Player: Spawned with {MAX_HEALTH} HP");
    }

    public override void _PhysicsProcess(double delta)
    {
        var dt = (float)delta;
        ProcessNormalMovement(GRAVITY, SPEED, dt);
        _preSlideVelocity = Velocity;
        MoveAndSlide();
        DecayKnockback(dt);

        if (GlobalPosition.Y > VOID_THRESHOLD && !_dead)
        {
            _dead = true;
            CurrentHealth = 0;
            Logger.Instance?.Info($"Player: Fell into void at y={GlobalPosition.Y:F0}");
            EventBus.Instance.EmitSignal(EventBus.SignalName.PlayerDamaged, (float)MAX_HEALTH, CurrentHealth, MAX_HEALTH);
            EventBus.Instance.EmitSignal(EventBus.SignalName.PlayerDied);
            SetPhysicsProcess(false);
            _prevContacts.Clear();
            return;
        }

        PushRigidBodies();
        ProcessInteract();
        ProcessKick(dt);
        ProcessDamageFlash(dt);
        UpdateAnimation();
    }

    private void ProcessNormalMovement(float gravity, float speed, float delta)
    {
        var vel = Velocity;
        if (!IsOnFloor())
        {
            vel.Y += gravity * delta;
        }

        // Frozen state disables all movement input
        if (_frozenInput)
        {
            _inputDirection = 0.0f;
            Velocity = vel;
            return;
        }

        if (Input.IsActionJustPressed(JumpAction) && IsOnFloor())
        {
            vel.Y = JUMP_VELOCITY;
        }

        _inputDirection = Input.GetAxis(MoveLeftAction, MoveRightAction);
        var targetVx = _inputDirection * speed * _speedModifier;
        var control = Mathf.Clamp(
            1.0f - _knockback.Length() / KNOCKBACK_FULL_SUPPRESSION,
            KNOCKBACK_MIN_CONTROL,
            1.0f);
        vel.X = Mathf.MoveToward(vel.X, targetVx, MOVE_ACCEL * control * delta);
        Velocity = vel;

        if (_inputDirection > 0.0f)
        {
            _facing = 1;
        }
        else if (_inputDirection < 0.0f)
        {
            _facing = -1;
        }
    }

    private void PushRigidBodies()
    {
        _currentContacts.Clear();
        var count = GetSlideCollisionCount();
        for (int i = 0; i < count; i++)
        {
            var collision = GetSlideCollision(i);
            var collider = collision.GetCollider();
            if (collider is not RigidBody2D rb)
            {
                continue;
            }

            var cid = rb.GetInstanceId();
            if (!_currentContacts.Add(cid))
            {
                continue;
            }

            // Push — continuous, every frame. Typed via GameObject.
            if (rb is GameObject pushGo && pushGo.IsPassivelyPushable())
            {
                var pushDir = -collision.GetNormal();
                rb.ApplyCentralForce(pushDir * PUSH_FORCE);
            }

            // Entry-only effects (first frame of new contact): bounce the
            // player off high-bounce GameObjects. Threshold mirrors
            // ObjectVisual._hasBounceSquash so the visual squash and the
            // player rebound trigger from the same physics property.
            if (!_prevContacts.Contains(cid)
                && rb is GameObject bounceGo
                && bounceGo.TypedBlueprint is not null
                && bounceGo.TypedBlueprint.Physics.Bounce > StateVisuals.SQUASH_BOUNCE_THRESHOLD)
            {
                ApplyBounce(collision);
            }
        }

        // Swap sets without allocating — next frame's "previous" is this
        // frame's "current"; the now-empty set becomes the fresh scratch.
        (_prevContacts, _currentContacts) = (_currentContacts, _prevContacts);
        _currentContacts.Clear();
    }

    private void ApplyBounce(KinematicCollision2D collision)
    {
        var normal = collision.GetNormal();
        var impactSpeed = Mathf.Max(-_preSlideVelocity.Dot(normal), 0.0f);
        if (impactSpeed > BOUNCE_MIN_SPEED)
        {
            Velocity = normal * impactSpeed * BOUNCE_ENERGY;
        }
    }

    private void ProcessInteract()
    {
        if (Input.IsActionJustPressed(InteractAction) && _affordance is not null)
        {
            _affordance.Interact();
        }
    }

    private void OnAnimationFinished()
    {
        if (_state == State.Kick)
        {
            _state = State.Idle; // re-evaluated on next UpdateAnimation
        }
    }

    private void UpdateAnimation()
    {
        if (_inputDirection > 0.0f)
        {
            _animSprite.FlipH = false;
        }
        else if (_inputDirection < 0.0f)
        {
            _animSprite.FlipH = true;
        }

        // Let kick animation play through before resuming normal state
        if (_state == State.Kick)
        {
            return;
        }

        var newState = _state;
        if (!IsOnFloor())
        {
            newState = Velocity.Y < 0.0f ? State.Jump : State.Fall;
        }
        else if (Mathf.Abs(Velocity.X) > 1.0f)
        {
            newState = State.Walk;
        }
        else
        {
            newState = State.Idle;
        }

        if (newState != _state)
        {
            _state = newState;
            var animName = _state switch
            {
                State.Idle => "idle",
                State.Walk => "walk",
                State.Jump => "jump",
                State.Fall => "fall",
                _ => "idle",
            };
            _animSprite.Play(animName);
        }
    }

    // --- IDamageable ---------------------------------------------------------

    public void TakeDamage(float amount, Color elementColor)
    {
        if (_dead)
        {
            return;
        }
        CurrentHealth = Mathf.Max(0, CurrentHealth - (int)amount);
        _damageFlashTimer = DAMAGE_FLASH_DURATION;
        Logger.Instance?.Debug($"Player: Took {amount:F0} damage, {CurrentHealth}/{MAX_HEALTH} HP remaining");
        EventBus.Instance.EmitSignal(EventBus.SignalName.PlayerDamaged, amount, CurrentHealth, MAX_HEALTH);
        if (CurrentHealth <= 0)
        {
            _dead = true;
            Logger.Instance?.Info("Player: Died from damage");
            EventBus.Instance.EmitSignal(EventBus.SignalName.PlayerDied);
            SetPhysicsProcess(false);
            _prevContacts.Clear();
        }
    }

    // --- IHealable -----------------------------------------------------------

    public void Heal(float amount)
    {
        CurrentHealth = Mathf.Min(CurrentHealth + (int)amount, MAX_HEALTH);
        Logger.Instance?.Debug($"Player: Healed {amount:F0}, {CurrentHealth}/{MAX_HEALTH} HP");
        EventBus.Instance.EmitSignal(EventBus.SignalName.PlayerHealed, amount, CurrentHealth, MAX_HEALTH);
    }

    // --- Damage flash --------------------------------------------------------

    private void ProcessDamageFlash(float delta)
    {
        if (_damageFlashTimer <= 0.0f)
        {
            return;
        }
        _damageFlashTimer -= delta;
        var t = _damageFlashTimer / DAMAGE_FLASH_DURATION;
        _animSprite.Modulate = new Color(1.0f, 1.0f - 0.6f * t, 1.0f - 0.6f * t);
        if (_damageFlashTimer <= 0.0f)
        {
            _animSprite.Modulate = Colors.White;
        }
    }

    // --- IImpulsable ---------------------------------------------------------

    public void ApplyExternalImpulse(Vector2 impulse)
    {
        if (_dead)
        {
            return;
        }
        var velChange = impulse / EFFECTIVE_MASS;
        Velocity += velChange;
        _knockback += velChange;
    }

    private void DecayKnockback(float delta)
    {
        _knockback = _knockback.MoveToward(Vector2.Zero, KNOCKBACK_DECAY * delta);
        if (IsOnFloor() && _knockback.Y > 0.0f)
        {
            _knockback.Y = 0.0f;
        }
    }

    // --- Speed modifier (stackable) ------------------------------------------

    public void ApplySpeedModifier(float factor)
    {
        _slowCount += 1;
        _speedModifier = Mathf.Min(_speedModifier, factor);
    }

    public void ClearSpeedModifier()
    {
        _slowCount = Mathf.Max(0, _slowCount - 1);
        if (_slowCount == 0)
        {
            _speedModifier = 1.0f;
        }
    }

    // --- IObjectNamed --------------------------------------------------------

    public string GetObjectName() => "player";

    public string[] GetTags() => Array.Empty<string>();

    public int GetFacing() => _facing;

    // --- IStateful (delegates to StateManager) -------------------------------

    public void AddState(StateId state, float duration) =>
        _gameStateManager?.AddState(state, duration);

    public void RemoveState(StateId state) => _gameStateManager?.RemoveState(state);

    public bool HasState(StateId state) => _gameStateManager is not null && _gameStateManager.HasState(state);

    // --- StateManager signal handlers ----------------------------------------

    private void OnGameStateAdded(string stateName)
    {
        var stateId = StateContradictions.NameToId(stateName);
        StateEffects.ApplyStandardDot(this, stateId);
        switch (stateId)
        {
            case StateId.Frozen:
                _frozenInput = true;
                break;
            case StateId.Wet:
                ApplySpeedModifier(StateVisuals.WET_SPEED_MULT);
                break;
        }
    }

    private void OnGameStateRemoved(string stateName)
    {
        var stateId = StateContradictions.NameToId(stateName);
        StateEffects.StopStandardDot(this, stateId);
        switch (stateId)
        {
            case StateId.Frozen:
                _frozenInput = false;
                break;
            case StateId.Wet:
                ClearSpeedModifier();
                break;
        }
    }

    // --- Carry/Ride sprite swap ---------------------------------------------

    public void SwapToCombinedSprite(Texture2D texture, Node obj)
    {
        HeldObject = obj;
        _animSprite.Visible = false;
        if (_combinedSprite is null)
        {
            _combinedSprite = new Sprite2D();
            AddChild(_combinedSprite);
        }
        _combinedSprite.Texture = texture;

        // Scale so that the carried/ridden object's sprite-space height
        // matches its blueprint physics. Floor at the player's normal display
        // size so small carried items don't shrink the player.
        var heightCm = 100;
        if (obj is GameObject gameObj && gameObj.TypedBlueprint is not null)
        {
            heightCm = gameObj.TypedBlueprint.Physics.HeightCm;
        }
        var objWorldSize = PhysicsComposer.WorldSpriteSize(heightCm);
        var frameTex = _animSprite.SpriteFrames.GetFrameTexture(_animSprite.Animation, 0);
        var playerWorldSize = frameTex.GetWidth() * _animSprite.Scale.X;
        var targetWorldSize = Mathf.Max(objWorldSize, playerWorldSize);
        var texSize = (float)texture.GetWidth();
        _combinedSprite.Scale = Vector2.One * (targetWorldSize / texSize);

        _combinedSprite.Visible = true;

        var objName = obj is IObjectNamed named ? named.GetObjectName() : obj.Name.ToString();
        Logger.Instance?.Info($"Player: Swapped to combined sprite (holding '{objName}')");
    }

    public Node? RestoreOriginalSprite()
    {
        if (_combinedSprite is not null)
        {
            _combinedSprite.Visible = false;
        }
        _animSprite.Visible = true;
        var obj = HeldObject;
        HeldObject = null;
        return obj;
    }

    public bool IsHolding() => HeldObject is not null;
}
