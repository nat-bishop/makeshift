using Godot;
using Makeshift.Autoloads;
using Makeshift.Data;
using Makeshift.Models;

namespace Makeshift.Scenes.Levels;

/// <summary>
/// Level 2: The Sentry. A hostile creature guards the goal. Player must
/// create something to distract, defeat, or bypass it.
/// </summary>
[GlobalClass]
public partial class Level02 : BaseLevel
{
    private static Godot.Collections.Dictionary GuardDogBlueprint() => new()
    {
        ["id"] = "guard_dog_level02",
        ["name"] = "guard dog",
        ["description"] = "guard dog",
        ["visual_description"] = "a fierce black guard dog with a spiked collar, crouching stance",
        ["physics"] = new Godot.Collections.Dictionary
        {
            ["mass_kg"] = 30.0,
            ["height_cm"] = 80,
            ["surface"] = 1,
            ["bounce"] = 15,
            ["gravity"] = 50,
        },
        ["durability"] = 3,
        ["affordance"] = 3,
        ["autonomous"] = true,
        ["speed"] = 3,
    };

    private static Godot.Collections.Dictionary BoneBlueprint() => new()
    {
        ["id"] = "bone_level02",
        ["name"] = "bone",
        ["description"] = "bone",
        ["visual_description"] = "a white dog bone, cartoon style",
        ["physics"] = new Godot.Collections.Dictionary
        {
            ["mass_kg"] = 0.3,
            ["height_cm"] = 20,
            ["surface"] = 1,
            ["bounce"] = 20,
            ["gravity"] = 50,
        },
        ["durability"] = 2,
        ["affordance"] = 0,
        ["autonomous"] = false,
    };

    public override void _Ready()
    {
        level_id = 1;
        objective_text = "Get past the guard dog!";
        next_level_path = "res://scenes/levels/level_03.tscn";
        base._Ready();

        BuildTerrain();
        SpawnGameObject(BoneBlueprint(), new Vector2(200, 536));
        SpawnGameObject(GuardDogBlueprint(), new Vector2(800, 520));

        // Pre-populate behavior: dog approaches and attacks player.
        InteractionCache.Instance.StoreBehavior("guard dog", "player",
            new BehaviorEntry
            {
                Target = "player",
                Movement = Movement.Approach,
                Priority = 2,
                Action = ActionKind.Damage,
                Amount = 20,
                StateAction = StateAction.None,
                StateId = StateId.None,
                Force = 0,
            });
        // Dog approaches bone (distraction, higher priority than player).
        InteractionCache.Instance.StoreBehavior("guard dog", "bone",
            new BehaviorEntry
            {
                Target = "bone",
                Movement = Movement.Approach,
                Priority = 3,
                Action = ActionKind.Consume,
                Amount = 0,
                StateAction = StateAction.None,
                StateId = StateId.None,
                Force = 0,
            });
    }

    private void BuildTerrain()
    {
        CreatePlatform(new Vector2(0, 568), new Vector2(1280, 64));
        CreateKillZone(new Vector2(0, 700), new Vector2(1280, 64));
    }
}
