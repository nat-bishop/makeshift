using Godot;
using Makeshift.Autoloads;
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
    private static Godot.Collections.Dictionary WoodenBoxBlueprint()
    {
        var bp = new Godot.Collections.Dictionary
        {
            ["id"] = "box_level03",
            ["name"] = "wooden box",
            ["description"] = "wooden box",
            ["visual_description"] = "a sturdy wooden storage box, medium sized",
            ["physics"] = new Godot.Collections.Dictionary
            {
                ["mass_kg"] = 8.0,
                ["height_cm"] = 60,
                ["surface"] = 1,
                ["bounce"] = 10,
                ["gravity"] = 55,
            },
            ["durability"] = 2,
            ["affordance"] = 0,
            ["autonomous"] = false,
        };
        var susceptible = new Godot.Collections.Array { 1 };
        bp["susceptible_states"] = susceptible;
        return bp;
    }

    private static Godot.Collections.Dictionary CampfireBlueprint()
    {
        var bp = new Godot.Collections.Dictionary
        {
            ["id"] = "campfire_level03",
            ["name"] = "campfire",
            ["description"] = "campfire",
            ["visual_description"] = "a small campfire with logs and orange flames",
            ["physics"] = new Godot.Collections.Dictionary
            {
                ["mass_kg"] = 3.0,
                ["height_cm"] = 40,
                ["surface"] = 1,
                ["bounce"] = 5,
                ["gravity"] = 55,
            },
            ["durability"] = 1,
            ["affordance"] = 3,
            ["autonomous"] = false,
        };
        var initial = new Godot.Collections.Array { 1 };
        bp["initial_states"] = initial;
        return bp;
    }

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
        SpawnGameObject(WoodenBoxBlueprint(), new Vector2(200, 536));
        SpawnGameObject(CampfireBlueprint(), new Vector2(600, 536));

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
                Force = 0,
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
