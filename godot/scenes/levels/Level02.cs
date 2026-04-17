using Godot;
using Makeshift.Autoloads;
using Logger = Makeshift.Autoloads.Logger;
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
    public override void _Ready()
    {
        level_id = 1;
        objective_text = "Get past the guard dog!";
        next_level_path = "res://scenes/levels/level_03.tscn";
        base._Ready();

        BuildTerrain();
        SpawnPrespawn("bone", new Vector2(200, 536));
        SpawnPrespawn("guard_dog", new Vector2(800, 520));

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
            });
    }

    private void BuildTerrain()
    {
        CreatePlatform(new Vector2(0, 568), new Vector2(1280, 64));
        CreateKillZone(new Vector2(0, 700), new Vector2(1280, 64));
    }
}
