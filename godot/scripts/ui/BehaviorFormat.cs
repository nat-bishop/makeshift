using System.Text;
using Makeshift.Data;
using Makeshift.Models;

namespace Makeshift.UI;

/// <summary>
/// Canonical name tables and formatters for behavior entries and object
/// metadata. Consolidates the duplicate abbreviation tables and format switch
/// expressions that used to live in <c>DebugLabel</c> and <c>InfoWidgets</c>.
/// </summary>
public static class BehaviorFormat
{
    /// <summary>Durability display abbreviations; index matches <see cref="Durability"/>.</summary>
    public static readonly string[] DurNames =
    [
        "fragile", "weak", "normal", "sturdy", "tough", "reinforced", "indestructible",
    ];

    /// <summary>Affordance display abbreviations; index matches <see cref="Affordance"/>.</summary>
    public static readonly string[] AffNames = ["carry", "mount", "climb", "none"];

    /// <summary>Surface friction display abbreviations; index matches <see cref="Surface"/>.</summary>
    public static readonly string[] SurfaceNames = ["slip", "norm", "grip"];

    /// <summary>Speed tier display abbreviations; index matches <see cref="SpeedTier"/>.</summary>
    public static readonly string[] SpeedNames = ["slug", "slow", "norm", "fast", "rapid"];

    /// <summary>Movement display abbreviations; index matches <see cref="Movement"/>.</summary>
    public static readonly string[] MoveNames = ["approach", "flee", "idle"];

    /// <summary>Action display abbreviations; index matches <see cref="ActionKind"/>.</summary>
    public static readonly string[] ActNames = ["idle", "dmg", "heal", "eat", "push"];

    /// <summary>State-action prefix sigils; index matches <see cref="StateAction"/>.</summary>
    public static readonly string[] StateActNames = ["", "+", "-"];

    /// <summary>Long-form movement name used by the creation reveal card.</summary>
    public static string MovementName(Movement m) => m switch
    {
        Movement.Approach => "approach",
        Movement.Flee => "flee",
        Movement.Ignore => "idle",
        _ => "?",
    };

    /// <summary>Long-form action name used by the creation reveal card.</summary>
    public static string ActionName(ActionKind a) => a switch
    {
        ActionKind.None => "idle",
        ActionKind.Damage => "dmg",
        ActionKind.Heal => "heal",
        ActionKind.Consume => "eat",
        ActionKind.Push => "push",
        _ => "?",
    };

    /// <summary>
    /// Produce the one-line summary of a behavior entry used by the
    /// object-creation reveal card:
    /// <c>target  movement action[:amount]  [+state|-state]  [kb]</c>
    /// </summary>
    public static string FormatBehaviorEntry(BehaviorEntry entry)
    {
        var target = !string.IsNullOrEmpty(entry.Target) ? entry.Target : "?";

        var sb = new StringBuilder();
        sb.Append(target);
        sb.Append("  ");
        sb.Append(MovementName(entry.Movement));
        sb.Append(' ');
        sb.Append(ActionName(entry.Action));

        if (entry.Amount > 0
            && (entry.Action is ActionKind.Damage or ActionKind.Heal or ActionKind.Push))
        {
            sb.Append(':');
            sb.Append(entry.Amount);
        }

        if (entry.StateAction == StateAction.Add && entry.StateId != StateId.None)
        {
            sb.Append("  +");
            sb.Append(StateContradictions.GetName(entry.StateId));
        }
        else if (entry.StateAction == StateAction.Remove && entry.StateId != StateId.None)
        {
            sb.Append("  -");
            sb.Append(StateContradictions.GetName(entry.StateId));
        }

        if (entry.Force == 1)
        {
            sb.Append("  kb");
        }

        return sb.ToString();
    }

    /// <summary>
    /// Terse debug-row form used by <c>DebugLabel</c>:
    /// <c>target P{pri} movAbbr actAbbr[:amt] [±state] [kb]</c>.
    /// </summary>
    public static string FormatPairDebugRow(string targetName, BehaviorEntry entry)
    {
        var mov = (int)entry.Movement;
        var act = (int)entry.Action;
        var sa = (int)entry.StateAction;
        var sid = (int)entry.StateId;

        var movStr = mov >= 0 && mov < MoveNames.Length ? MoveNames[mov] : "?";
        var actStr = act >= 0 && act < ActNames.Length ? ActNames[act] : "?";

        var text = new StringBuilder();
        text.Append($"{targetName} P{entry.Priority} {movStr} {actStr}");

        if ((act == 1 || act == 2 || act == 4) && entry.Amount > 0)
        {
            text.Append($":{entry.Amount}");
        }

        if ((sa == 1 || sa == 2) && sid >= 1 && sid < StateContradictions.STATE_NAMES.Length)
        {
            text.Append($" {StateActNames[sa]}{StateContradictions.STATE_NAMES[sid]}");
        }

        if (entry.Force == 1)
        {
            text.Append(" kb");
        }

        return text.ToString();
    }
}
