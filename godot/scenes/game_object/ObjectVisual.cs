using System.Collections.Generic;
using Godot;
using Makeshift.Autoloads;
using Logger = Makeshift.Autoloads.Logger;
using Makeshift.Data;
using Makeshift.Models;
using Makeshift.Systems;

namespace Makeshift.Scenes.GameObjects;

/// <summary>
/// State-keyed visuals + physics-derived animations for a
/// <see cref="GameObject"/>. Reads its typed blueprint for particle, flash,
/// shader, and light configuration.
/// </summary>
[GlobalClass]
public partial class ObjectVisual : Node
{
    private Sprite2D? _sprite;
    private string _objectId = "";
    private bool _spriteApplied;

    // Programmatic animation state
    private float _time;
    private float _baseSpriteY;
    private Vector2 _baseSpriteScale = Vector2.One;
    private bool _programmaticInitialized;
    private float _hitFlashTimer;

    // Physics-derived flags
    private bool _hasBobbing;
    private bool _hasBounceSquash;
    private Tween? _bounceTween;

    private static GradientTexture2D? _cachedLightTexture;

    // State-driven visual state
    private Color _activeColorShift = Colors.White;
    private readonly List<FlashRuntime> _activeFlashConfigs = new();
    private readonly Dictionary<StateId, CpuParticles2D> _particleNodes = new();
    private readonly Dictionary<StateId, PointLight2D> _lightNodes = new();

    private sealed class FlashRuntime
    {
        public float Interval;
        public Color Color;
        public float NextTime;
        public float FlashTimer;
    }

    public override void _Ready()
    {
        _sprite = GetParent().GetNode<Sprite2D>("Sprite2D");
        EventBus.Instance.SpriteReady += OnSpriteReady;
        SetProcess(false);
    }

    public override void _Process(double delta)
    {
        if (_programmaticInitialized)
        {
            _time += (float)delta;
            ApplyAnims((float)delta);
        }
    }

    public void SetObjectId(string id)
    {
        _objectId = id;
        // Check parent for a preloaded sprite (img2img destruction debris).
        if (GetParent() is GameObject parent && parent.PreloadedSprite is not null)
        {
            SetSprite(parent.PreloadedSprite);
            return;
        }
        var cached = Backend.Instance.GetCachedSprite(id);
        if (cached is not null)
        {
            SetSprite(cached);
        }
    }

    public void SetSprite(Texture2D texture)
    {
        if (_spriteApplied || _sprite is null)
        {
            return;
        }
        _spriteApplied = true;

        var parent = GetParent<GameObject>();
        var heightCm = parent.TypedBlueprint?.Physics.HeightCm ?? 30;
        var worldSize = PhysicsComposer.WorldSpriteSize(heightCm);
        float texSize = texture.GetWidth();
        _sprite.Scale = Vector2.One * (worldSize / texSize);
        _sprite.Texture = texture;
        _baseSpriteScale = _sprite.Scale;

        var pa = parent.GetNodeOrNull<PhysicsApplicator>("PhysicsApplicator");
        pa?.CallDeferred(PhysicsApplicator.MethodName.UpdateShapeFromSprite, texture, worldSize);
    }

    private void OnSpriteReady(string id, Texture2D texture)
    {
        if (id == _objectId)
        {
            SetSprite(texture);
        }
    }

    // --- Init and refresh --------------------------------------------------

    public void InitVisuals(Blueprint bp)
    {
        if (_sprite is null)
        {
            return;
        }
        _baseSpriteY = _sprite.Position.Y;
        _baseSpriteScale = _sprite.Scale;

        var phys = bp.Physics;
        _hasBobbing = phys.Gravity < StateVisuals.BOBBING_GRAVITY_THRESHOLD;
        _hasBounceSquash = phys.Bounce > StateVisuals.SQUASH_BOUNCE_THRESHOLD;

        if (_hasBounceSquash && GetParent() is RigidBody2D rb)
        {
            rb.BodyEntered += OnBounceCollision;
        }

        if (_hasBobbing)
        {
            _programmaticInitialized = true;
            SetProcess(true);
        }
    }

    public void RefreshStateVisuals(IReadOnlyCollection<StateId> states)
    {
        UpdateStateParticles(states);
        UpdateStateColor(states);
        UpdateStateLights(states);
        UpdateStateFlash(states);

        bool needsProcess = _hasBobbing || _activeFlashConfigs.Count > 0;
        if (needsProcess)
        {
            _programmaticInitialized = true;
            SetProcess(true);
        }
        else if (!_hasBobbing)
        {
            if (_sprite is not null)
            {
                _sprite.Modulate = _activeColorShift;
            }
            _programmaticInitialized = false;
            SetProcess(false);
        }
    }

    // --- State-driven visuals ----------------------------------------------

    private void UpdateStateParticles(IReadOnlyCollection<StateId> states)
    {
        var stateSet = new HashSet<StateId>(states);
        var keysToRemove = new List<StateId>();
        foreach (var key in _particleNodes.Keys)
        {
            if (!stateSet.Contains(key))
            {
                _particleNodes[key].QueueFree();
                keysToRemove.Add(key);
            }
        }
        foreach (var k in keysToRemove)
        {
            _particleNodes.Remove(k);
        }
        foreach (var s in stateSet)
        {
            if (StateVisuals.Particles.ContainsKey(s) && !_particleNodes.ContainsKey(s))
            {
                _particleNodes[s] = CreateStateParticles(s);
            }
        }
    }

    private CpuParticles2D CreateStateParticles(StateId state)
    {
        var data = StateVisuals.Particles[state];
        var emitter = new CpuParticles2D
        {
            Emitting = true,
            Amount = data.Amount,
            Lifetime = 1.0,
            Direction = data.Direction,
            Spread = data.Spread,
            InitialVelocityMin = data.Speed * 0.5f,
            InitialVelocityMax = data.Speed,
            ScaleAmountMin = 0.3f,
            ScaleAmountMax = 0.6f,
            Gravity = data.Direction * -50.0f,
            Color = data.Color,
        };
        var ramp = new Gradient();
        ramp.SetColor(0, data.Color);
        ramp.SetColor(1, new Color(data.Color.R, data.Color.G, data.Color.B, 0.0f));
        emitter.ColorRamp = ramp;
        AddChild(emitter);
        return emitter;
    }

    private void UpdateStateColor(IReadOnlyCollection<StateId> states)
    {
        _activeColorShift = Colors.White;
        foreach (var s in states)
        {
            if (StateVisuals.ColorShift.TryGetValue(s, out var shift))
            {
                _activeColorShift = shift;
                break; // First match wins
            }
        }
        if (_hitFlashTimer <= 0.0f && _sprite is not null)
        {
            _sprite.Modulate = _activeColorShift;
        }
    }

    private void UpdateStateLights(IReadOnlyCollection<StateId> states)
    {
        var stateSet = new HashSet<StateId>(states);
        var keysToRemove = new List<StateId>();
        foreach (var key in _lightNodes.Keys)
        {
            if (!stateSet.Contains(key))
            {
                _lightNodes[key].QueueFree();
                keysToRemove.Add(key);
            }
        }
        foreach (var k in keysToRemove)
        {
            _lightNodes.Remove(k);
        }
        foreach (var s in stateSet)
        {
            if (StateVisuals.Lights.ContainsKey(s) && !_lightNodes.ContainsKey(s))
            {
                _lightNodes[s] = CreateStateLight(s);
            }
        }
    }

    private static GradientTexture2D GetLightTexture()
    {
        if (_cachedLightTexture is not null)
        {
            return _cachedLightTexture;
        }
        var gradient = new Gradient();
        gradient.SetColor(0, Colors.White);
        gradient.SetColor(1, new Color(1.0f, 1.0f, 1.0f, 0.0f));
        var tex = new GradientTexture2D
        {
            Gradient = gradient,
            Fill = GradientTexture2D.FillEnum.Radial,
            FillFrom = new Vector2(0.5f, 0.5f),
            FillTo = new Vector2(1.0f, 0.5f),
            Width = 128,
            Height = 128,
        };
        _cachedLightTexture = tex;
        return tex;
    }

    private PointLight2D CreateStateLight(StateId state)
    {
        var data = StateVisuals.Lights[state];
        var light = new PointLight2D
        {
            Color = data.Color,
            Energy = data.Energy,
            Texture = GetLightTexture(),
            TextureScale = data.Range / 128.0f,
        };
        AddChild(light);
        return light;
    }

    private void UpdateStateFlash(IReadOnlyCollection<StateId> states)
    {
        _activeFlashConfigs.Clear();
        foreach (var s in states)
        {
            if (StateVisuals.Flash.TryGetValue(s, out var cfg))
            {
                _activeFlashConfigs.Add(new FlashRuntime
                {
                    Interval = cfg.Interval,
                    Color = cfg.Color,
                    NextTime = cfg.Interval,
                    FlashTimer = 0.0f,
                });
            }
        }
    }

    // --- Per-frame animation -----------------------------------------------

    private void ApplyAnims(float delta)
    {
        if (_sprite is null)
        {
            return;
        }

        // Bobbing
        if (_hasBobbing)
        {
            var pos = _sprite.Position;
            pos.Y = _baseSpriteY + 3.0f * Mathf.Sin(_time * Mathf.Pi);
            _sprite.Position = pos;
        }

        // Flash
        if (_hitFlashTimer > 0.0f)
        {
            _hitFlashTimer -= delta;
        }
        else if (_activeFlashConfigs.Count > 0)
        {
            var color = _activeColorShift;
            foreach (var cfg in _activeFlashConfigs)
            {
                if (cfg.FlashTimer > 0.0f)
                {
                    cfg.FlashTimer -= delta;
                    if (cfg.FlashTimer > 0.0f)
                    {
                        color = cfg.Color;
                    }
                }
                else
                {
                    cfg.NextTime -= delta;
                    if (cfg.NextTime <= 0.0f)
                    {
                        color = cfg.Color;
                        cfg.FlashTimer = 0.1f;
                        cfg.NextTime = cfg.Interval;
                    }
                }
            }
            _sprite.Modulate = color;
        }
    }

    // --- Event-triggered effects -------------------------------------------

    public void FlashHit(Color color)
    {
        if (_sprite is null)
        {
            return;
        }
        _hitFlashTimer = 0.15f;
        var original = _sprite.Modulate;
        var tween = _sprite.CreateTween();
        tween.TweenProperty(_sprite, "modulate", color, 0.07);
        tween.TweenProperty(_sprite, "modulate", original, 0.08);
    }

    public void SpawnParticles(Color color, int count = 5)
    {
        if (_sprite is null)
        {
            return;
        }
        var center = _sprite.Position;
        for (int i = 0; i < count; i++)
        {
            var particle = new ColorRect
            {
                Size = new Vector2(4, 4),
                Color = color,
                Position = center - new Vector2(2, 2),
            };
            AddChild(particle);
            var angle = GD.Randf() * Mathf.Tau;
            var dir = new Vector2(Mathf.Cos(angle), Mathf.Sin(angle) - 0.5f).Normalized();
            var endPos = particle.Position + dir * 30.0f;
            var tween = particle.CreateTween();
            tween.SetParallel(true);
            tween.TweenProperty(particle, "position", endPos, 0.5);
            tween.TweenProperty(particle, "modulate:a", 0.0f, 0.5);
            tween.SetParallel(false);
            tween.TweenCallback(Callable.From(particle.QueueFree));
        }
    }

    private void OnBounceCollision(Node body)
    {
        if (_sprite is null)
        {
            return;
        }
        if (_bounceTween is not null && _bounceTween.IsValid())
        {
            _bounceTween.Kill();
        }
        var basis = _baseSpriteScale;
        _bounceTween = _sprite.CreateTween();
        _bounceTween.TweenProperty(_sprite, "scale", basis * new Vector2(1.2f, 0.8f), 0.05);
        _bounceTween.TweenProperty(_sprite, "scale", basis * new Vector2(0.9f, 1.1f), 0.08);
        _bounceTween.TweenProperty(_sprite, "scale", basis, 0.1);
    }

    public override void _ExitTree()
    {
        if (EventBus.Instance is not null)
        {
            EventBus.Instance.SpriteReady -= OnSpriteReady;
        }
        if (_hasBounceSquash && GetParent() is RigidBody2D rb)
        {
            rb.BodyEntered -= OnBounceCollision;
        }
    }

}
