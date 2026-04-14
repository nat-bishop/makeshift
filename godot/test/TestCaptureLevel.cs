using Godot;
using Makeshift.Autoloads;

namespace Makeshift.Tests;

/// <summary>
/// Capture level 1 visuals by simulating the real game startup flow.
/// </summary>
public sealed partial class TestCaptureLevel : Node
{
    private int _frame;
    private bool _started;

    public override void _Ready()
    {
        GD.Print("CAPTURE: Waiting for main menu to load...");
    }

    public override void _Process(double delta)
    {
        _frame++;

        // Frame 5: trigger game start (gives autoloads time to initialize)
        if (_frame == 5 && !_started)
        {
            _started = true;
            GD.Print("CAPTURE: Starting game via GameManager.StartGame(0)");
            GameManager.Instance.StartGame(0);
        }

        // Frame 15: log what we see
        if (_frame == 15)
        {
            var root = GetTree().Root;
            var player = FindNodeByName(root, "Player");
            if (player is not null)
            {
                var global = player is Node2D n2d ? n2d.GlobalPosition.ToString() : "<non-Node2D>";
                GD.Print($"ASSERT PASS: Player at {global}");
            }
            else
            {
                GD.Print("ASSERT FAIL: Player not found");
            }

            var level = FindNodeByName(root, "Level01");
            GD.Print(level is not null ? "ASSERT PASS: Level01 loaded" : "ASSERT FAIL: Level01 not found");
        }
    }

    private static Node? FindNodeByName(Node node, string target)
    {
        if (node.Name == target)
        {
            return node;
        }
        foreach (var child in node.GetChildren())
        {
            var found = FindNodeByName(child, target);
            if (found is not null)
            {
                return found;
            }
        }
        return null;
    }
}
