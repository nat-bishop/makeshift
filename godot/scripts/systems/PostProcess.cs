using Godot;
using Makeshift.Autoloads;

namespace Makeshift.Systems;

/// <summary>
/// Post-processing shader manager. Cycles through available shaders with a
/// key toggle bound to the <c>toggle_post_process</c> input action.
/// </summary>
[GlobalClass]
public partial class PostProcess : CanvasLayer
{
    private static readonly string[] Shaders =
    [
        "", // index 0 = no post-processing
        "res://shaders/post/palette_limit.gdshader",
        "res://shaders/post/dither.gdshader",
        "res://shaders/post/sobel_outline.gdshader",
        "res://shaders/post/crosshatch.gdshader",
        "res://shaders/post/pencil.gdshader",
    ];

    private int _currentIndex;
    private ColorRect _colorRect = null!;

    public override void _Ready()
    {
        Layer = 100;
        _colorRect = new ColorRect();
        _colorRect.SetAnchorsPreset(Control.LayoutPreset.FullRect);
        _colorRect.MouseFilter = Control.MouseFilterEnum.Ignore;
        _colorRect.Visible = false;
        AddChild(_colorRect);
    }

    public override void _UnhandledInput(InputEvent @event)
    {
        if (@event.IsActionPressed("toggle_post_process"))
        {
            CycleShader();
        }
    }

    public void CycleShader()
    {
        _currentIndex = (_currentIndex + 1) % Shaders.Length;
        if (_currentIndex == 0)
        {
            _colorRect.Visible = false;
            _colorRect.Material = null;
            Logger.Instance?.Info("PostProcess: disabled");
        }
        else
        {
            var shader = ResourceLoader.Load<Shader>(Shaders[_currentIndex]);
            var mat = new ShaderMaterial { Shader = shader };
            _colorRect.Material = mat;
            _colorRect.Visible = true;
            var shaderName = Shaders[_currentIndex].GetFile().GetBaseName();
            Logger.Instance?.Info($"PostProcess: {shaderName}");
        }
    }
}
