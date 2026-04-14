using Godot;
using Makeshift.Autoloads;
using Makeshift.Data;
using Makeshift.Models;

namespace Makeshift.Scenes.Levels;

/// <summary>
/// Level 1: The Acid Moat. Two platforms separated by a 480px acid-filled pit.
/// Player must create a durable bridge to cross. Stone resists acid; wood
/// corrodes.
/// </summary>
[GlobalClass]
public partial class Level01 : BaseLevel
{
    private static Godot.Collections.Dictionary CrateBlueprint() => new()
    {
        ["id"] = "crate_level01",
        ["name"] = "wooden crate",
        ["description"] = "wooden crate",
        ["visual_description"] = "a small wooden shipping crate with planks and nails",
        ["physics"] = new Godot.Collections.Dictionary
        {
            ["mass_kg"] = 5.0,
            ["height_cm"] = 40,
            ["surface"] = 1,
            ["bounce"] = 10,
            ["gravity"] = 55,
        },
        ["durability"] = 2,
        ["affordance"] = 0,
        ["autonomous"] = false,
    };

    private static Godot.Collections.Dictionary AcidPoolBp() => new()
    {
        ["name"] = "acid pool",
        ["physics"] = new Godot.Collections.Dictionary
        {
            ["mass_kg"] = 100.0,
            ["height_cm"] = 10,
            ["surface"] = 0,
            ["bounce"] = 0,
            ["gravity"] = 50,
        },
        ["durability"] = 6,
    };

    public override void _Ready()
    {
        level_id = 0;
        objective_text = "Cross the acid moat!";
        next_level_path = "res://scenes/levels/level_02.tscn";
        base._Ready();

        BuildTerrain();
        SpawnGameObject(CrateBlueprint(), new Vector2(280, 536));

        // Pre-populate behavior: acid pool damages wooden crate (reactive).
        InteractionCache.Instance.StoreBehavior("acid pool", "wooden crate",
            new BehaviorEntry
            {
                Target = "wooden crate",
                Movement = Movement.Ignore,
                Priority = 2,
                Action = ActionKind.Damage,
                Amount = 15,
                StateAction = StateAction.None,
                StateId = StateId.None,
                Force = 0,
            });
    }

    private void BuildTerrain()
    {
        CreatePlatform(new Vector2(0, 568), new Vector2(384, 64));
        CreatePlatform(new Vector2(896, 568), new Vector2(384, 64));
        CreatePlatform(new Vector2(384, 568), new Vector2(16, 128));
        CreatePlatform(new Vector2(880, 568), new Vector2(16, 128));
        CreateEnvBody(
            new Vector2(400, 632), new Vector2(480, 48),
            "acid pool", AcidPoolBp(),
            new Color(0.2f, 0.9f, 0.1f, 0.8f), solid: false);
        CreateKillZone(new Vector2(400, 700), new Vector2(480, 64));
    }
}
