using System.Collections.Generic;
using Godot;

namespace Makeshift.Scenes.Effects;

/// <summary>
/// Object materialization effect: a swarm of paper scraps coalesce into a
/// central glow while an LLM call resolves a new blueprint, then either
/// scatter (failure / cancel) or land at the final spawn point.
/// </summary>
[GlobalClass]
public partial class MaterializeEffect : Node2D
{
    private const int ScrapCount = 10;
    private const float SpawnRadius = 120.0f;
    private const float CoalesceDuration = 1.2f;
    private const float IdleBobAmplitude = 8.0f;
    private const float IdleBobPeriod = 1.5f;
    private const float ResolveDuration = 0.3f;
    private const float BurstRadius = 60.0f;

    private static readonly Color[] CraftColors =
    [
        new(0.82f, 0.73f, 0.55f),
        new(0.93f, 0.89f, 0.80f),
        new(0.60f, 0.47f, 0.33f),
        new(0.88f, 0.86f, 0.82f),
        new(0.72f, 0.68f, 0.62f),
        new(0.78f, 0.65f, 0.45f),
        new(0.85f, 0.80f, 0.70f),
    ];

    private readonly List<Sprite2D> _scraps = new();
    private Tween? _coalesceTween;
    private readonly List<Tween> _idleTweens = new();
    private bool _isResolving;

    public override void _Ready()
    {
        CreateScraps();
        StartCoalesce();
    }

    public void Resolve(bool scatter = true)
    {
        if (_isResolving)
        {
            return;
        }
        _isResolving = true;
        KillAllTweens();

        var tween = CreateTween().SetParallel(true);
        foreach (var scrap in _scraps)
        {
            if (!IsInstanceValid(scrap))
            {
                continue;
            }
            if (scatter)
            {
                var burstDir = Vector2.FromAngle(GD.Randf() * Mathf.Tau);
                var burstTarget = scrap.Position + burstDir * BurstRadius;
                tween.TweenProperty(scrap, "position", burstTarget, ResolveDuration);
            }
            tween.TweenProperty(scrap, "modulate:a", 0.0f, ResolveDuration);
        }

        tween.SetParallel(false);
        tween.TweenCallback(Callable.From(QueueFree));
    }

    private void CreateScraps()
    {
        for (int i = 0; i < ScrapCount; i++)
        {
            var scrap = new Sprite2D();
            int scrapSize = (int)GD.RandRange(4, 8);
            var image = Image.CreateEmpty(scrapSize, scrapSize, false, Image.Format.Rgba8);
            image.Fill(CraftColors[(int)(GD.Randi() % CraftColors.Length)]);
            scrap.Texture = ImageTexture.CreateFromImage(image);

            var angle = GD.Randf() * Mathf.Tau;
            var dist = (float)GD.RandRange(SpawnRadius * 0.4, SpawnRadius);
            scrap.Position = Vector2.FromAngle(angle) * dist;
            scrap.Rotation = GD.Randf() * Mathf.Tau;
            var modAlpha = scrap.Modulate;
            modAlpha.A = 0.0f;
            scrap.Modulate = modAlpha;
            AddChild(scrap);
            _scraps.Add(scrap);
        }
    }

    private void StartCoalesce()
    {
        _coalesceTween = CreateTween().SetParallel(true);
        for (int i = 0; i < _scraps.Count; i++)
        {
            var scrap = _scraps[i];
            var delay = (float)GD.RandRange(0.0, 0.3);
            var duration = CoalesceDuration - delay;

            // Fade in
            _coalesceTween.TweenProperty(scrap, "modulate:a", 1.0f, duration * 0.4f).SetDelay(delay);
            // Move to center
            _coalesceTween
                .TweenProperty(scrap, "position", Vector2.Zero, duration)
                .SetDelay(delay)
                .SetEase(Tween.EaseType.In)
                .SetTrans(Tween.TransitionType.Quad);
            // Spin
            var direction = GD.Randf() > 0.5f ? 1.0f : -1.0f;
            var spin = scrap.Rotation + (float)GD.RandRange(Mathf.Pi, Mathf.Tau * 2.0) * direction;
            _coalesceTween.TweenProperty(scrap, "rotation", spin, duration).SetDelay(delay);
        }

        _coalesceTween.SetParallel(false);
        _coalesceTween.TweenCallback(Callable.From(StartIdle));
    }

    private void StartIdle()
    {
        if (_isResolving)
        {
            return;
        }
        foreach (var scrap in _scraps)
        {
            if (!IsInstanceValid(scrap))
            {
                continue;
            }
            var tween = CreateTween().SetLoops();
            var offset = new Vector2(
                (float)GD.RandRange(-IdleBobAmplitude, IdleBobAmplitude),
                (float)GD.RandRange(-IdleBobAmplitude, IdleBobAmplitude));
            var period = (float)GD.RandRange(IdleBobPeriod * 0.8, IdleBobPeriod * 1.2);
            tween
                .TweenProperty(scrap, "position", offset, period)
                .SetEase(Tween.EaseType.InOut)
                .SetTrans(Tween.TransitionType.Sine);
            tween
                .TweenProperty(scrap, "position", -offset * 0.5f, period)
                .SetEase(Tween.EaseType.InOut)
                .SetTrans(Tween.TransitionType.Sine);
            _idleTweens.Add(tween);
        }
    }

    public override void _ExitTree()
    {
        KillAllTweens();
    }

    private void KillAllTweens()
    {
        if (_coalesceTween is not null && _coalesceTween.IsValid())
        {
            _coalesceTween.Kill();
            _coalesceTween = null;
        }
        foreach (var tween in _idleTweens)
        {
            if (tween is not null && tween.IsValid())
            {
                tween.Kill();
            }
        }
        _idleTweens.Clear();
    }

}
