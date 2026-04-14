using Godot;

namespace Makeshift.Scenes.Levels;

/// <summary>
/// Sandbox: flat ground with platforms and raised sections. No prebuilt
/// objects — used for prompt iteration and free-form creation testing.
/// </summary>
[GlobalClass]
public partial class LevelSandbox : BaseLevel
{
    public override void _Ready()
    {
        level_id = 3;
        objective_text = "";
        next_level_path = "";
        base._Ready();
        BuildTerrain();
    }

    private void BuildTerrain()
    {
        CreatePlatform(new Vector2(0, 600), new Vector2(1600, 64));

        CreatePlatform(new Vector2(256, 536), new Vector2(256, 128));
        CreatePlatform(new Vector2(1088, 472), new Vector2(384, 192));

        CreatePlatform(new Vector2(640, 488), new Vector2(160, 24));
        CreatePlatform(new Vector2(832, 392), new Vector2(160, 24));
        CreatePlatform(new Vector2(192, 336), new Vector2(160, 24));

        CreateKillZone(new Vector2(0, 760), new Vector2(1600, 64));
    }
}
