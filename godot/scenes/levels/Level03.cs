using Godot;
using Makeshift.Autoloads;
using Logger = Makeshift.Autoloads.Logger;
using Makeshift.Data;
using Makeshift.Models;

namespace Makeshift.Scenes.Levels;

/// <summary>
/// Level 3: The Climb. Goal is high up. Player must create objects to reach
/// it. Stacked objects, ladders, or flying objects all work.
/// </summary>
[GlobalClass]
public partial class Level03 : BaseLevel
{
    private static Godot.Collections.Dictionary FirePitBp() => new()
    {
        ["name"] = "fire pit",
        ["physics"] = new Godot.Collections.Dictionary
        {
            ["mass_kg"] = 50.0,
            ["height_cm"] = 10,
            ["surface"] = 1,
            ["bounce"] = 0,
            ["gravity"] = 50,
        },
        ["durability"] = 6,
    };

    public override void _Ready()
    {
        level_id = 2;
        objective_text = "Reach the top!";
        next_level_path = "";
        base._Ready();

        BuildTerrain();
        SpawnPrespawn("wooden_box", new Vector2(200, 536));
        SpawnPrespawn("campfire", new Vector2(600, 536));

        // Pre-populate behavior: campfire damages wooden box and sets it on fire.
        InteractionCache.Instance.StoreBehavior("campfire", "wooden box",
            new BehaviorEntry
            {
                Target = "wooden box",
                Movement = Movement.Ignore,
                Priority = 2,
                Action = ActionKind.Damage,
                Amount = 10,
                StateAction = StateAction.Add,
                StateId = StateId.Burning,
            });
    }

    private void BuildTerrain()
    {
        CreatePlatform(new Vector2(0, 568), new Vector2(1280, 64));
        CreatePlatform(new Vector2(300, 450), new Vector2(200, 24));
        CreatePlatform(new Vector2(600, 330), new Vector2(200, 24));
        CreatePlatform(new Vector2(900, 210), new Vector2(200, 24));
        CreateEnvBody(
            new Vector2(450, 540), new Vector2(100, 28),
            "fire pit", FirePitBp(),
            new Color(1.0f, 0.3f, 0.0f, 0.8f), solid: false);
    }
}
