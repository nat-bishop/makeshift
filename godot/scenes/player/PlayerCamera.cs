using Godot;

namespace Makeshift.Scenes.Player;

/// <summary>
/// Camera that leads the player slightly toward the mouse cursor. Mouse
/// displacement is scaled by <see cref="LookAheadFactor"/>, clamped to
/// <see cref="LookAheadMax"/>, then smoothed toward the target offset.
/// </summary>
[GlobalClass]
public partial class PlayerCamera : Camera2D
{
    [Export]
    public float LookAheadFactor { get; set; } = 0.2f;

    [Export]
    public float LookAheadMax { get; set; } = 100.0f;

    [Export]
    public float SmoothSpeed { get; set; } = 5.0f;

    private Vector2 _baseOffset;
    private Viewport _viewport = null!;

    public override void _Ready()
    {
        _baseOffset = Offset;
        _viewport = GetViewport();
    }

    public override void _Process(double delta)
    {
        var viewportSize = _viewport.GetVisibleRect().Size;
        var mouseScreen = _viewport.GetMousePosition();
        var screenCenter = viewportSize * 0.5f;
        var displacement = (mouseScreen - screenCenter) / Zoom;

        var targetOffset = (displacement * LookAheadFactor).LimitLength(LookAheadMax);

        var t = 1.0f - Mathf.Exp(-SmoothSpeed * (float)delta);
        Offset = Offset.Lerp(_baseOffset + targetOffset, t);
    }
}
