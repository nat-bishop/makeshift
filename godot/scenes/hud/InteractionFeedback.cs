using System.Collections.Generic;
using Godot;
using Makeshift.Autoloads;
using Logger = Makeshift.Autoloads.Logger;
using Makeshift.Data;

namespace Makeshift.Scenes.Hud;

/// <summary>
/// Spawns floating damage/heal numbers at world positions. Subscribes to
/// <see cref="EventBus.EffectApplied"/> for element-colored feedback.
/// </summary>
public sealed partial class InteractionFeedback : Node2D
{
    private const int MaxActive = 8;
    private const float FloatDistance = 50.0f;
    private const float FloatDuration = 1.5f;
    private const float SolidDuration = 0.75f;
    private const int FontSize = 18;
    private const int OutlineSize = 4;
    private const float XScatter = 20.0f;

    private static readonly Color OutlineColor = Colors.Black;

    private readonly List<Label> _activeLabels = new();

    public override void _Ready()
    {
        EventBus.Instance.EffectApplied += OnEffectApplied;
    }

    public override void _ExitTree()
    {
        if (EventBus.Instance is not null)
        {
            EventBus.Instance.EffectApplied -= OnEffectApplied;
        }
    }

    private void OnEffectApplied(string effectType, float amount, Color elementColor, Vector2 worldPos)
    {
        string text;
        Color color;
        if (effectType == "HEAL")
        {
            text = $"+{(int)amount}";
            color = StateVisuals.HealColor;
        }
        else
        {
            text = $"-{(int)amount}";
            color = elementColor;
        }
        SpawnLabel(text, color, worldPos);
    }

    private void SpawnLabel(string text, Color color, Vector2 worldPos)
    {
        while (_activeLabels.Count >= MaxActive)
        {
            var oldest = _activeLabels[0];
            _activeLabels.RemoveAt(0);
            if (GodotObject.IsInstanceValid(oldest))
            {
                oldest.QueueFree();
            }
        }

        var label = new Label
        {
            Text = text,
            HorizontalAlignment = HorizontalAlignment.Center,
        };
        label.AddThemeFontSizeOverride("font_size", FontSize);
        label.AddThemeColorOverride("font_color", color);
        label.AddThemeColorOverride("font_outline_color", OutlineColor);
        label.AddThemeConstantOverride("outline_size", OutlineSize);

        // Random x offset to prevent stacking
        var xOffset = (float)GD.RandRange(-XScatter, XScatter);
        label.Position = new Vector2(worldPos.X - 30 + xOffset, worldPos.Y);
        var minSize = label.CustomMinimumSize;
        minSize.X = 60;
        label.CustomMinimumSize = minSize;

        AddChild(label);
        _activeLabels.Add(label);

        // Float up, stay solid, then fade.
        var tween = CreateTween();
        tween.TweenProperty(label, "position:y", worldPos.Y - FloatDistance, FloatDuration);
        tween.TweenInterval(SolidDuration);
        tween.TweenProperty(label, "modulate:a", 0.0f, FloatDuration - SolidDuration);
        tween.TweenCallback(Callable.From(() => RemoveLabel(label)));
    }

    private void RemoveLabel(Label label)
    {
        if (GodotObject.IsInstanceValid(label))
        {
            _activeLabels.Remove(label);
            label.QueueFree();
        }
    }
}
