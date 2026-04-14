using Godot;
using Makeshift.Data;
using Makeshift.Models;

namespace Makeshift.UI;

/// <summary>
/// Small factory helpers for debug / HUD widgets: state badges and styled panels.
/// </summary>
public static class InfoWidgets
{
    /// <summary>
    /// Create a small inline state badge: tinted label with rounded stylebox
    /// background. <paramref name="state"/> is the lowercase state name
    /// (<c>burning</c>, <c>frozen</c>, etc.).
    /// </summary>
    public static Label CreateStateBadge(string state, int fontSize = 12)
    {
        var badge = new Label
        {
            Text = $" {state} ",
        };
        badge.AddThemeFontSizeOverride("font_size", fontSize);

        var color = StateVisuals.GetStateColorOr(
            StateContradictions.NameToId(state),
            new Color(0.6f, 0.6f, 0.6f));

        badge.AddThemeColorOverride("font_color", color);
        badge.AddThemeStyleboxOverride(
            "normal",
            MakeStylebox(new Color(color, 0.15f), 3, 4, 1));
        return badge;
    }

    /// <summary>
    /// Build a <see cref="StyleBoxFlat"/> with uniform corner radius + margins
    /// and an optional uniform border.
    /// </summary>
    public static StyleBoxFlat MakeStylebox(
        Color bgColor,
        int cornerRadius,
        float contentMarginH,
        float contentMarginV,
        int borderWidth = 0,
        Color? borderColor = null)
    {
        var style = new StyleBoxFlat
        {
            BgColor = bgColor,
            CornerRadiusTopLeft = cornerRadius,
            CornerRadiusTopRight = cornerRadius,
            CornerRadiusBottomLeft = cornerRadius,
            CornerRadiusBottomRight = cornerRadius,
            ContentMarginLeft = contentMarginH,
            ContentMarginRight = contentMarginH,
            ContentMarginTop = contentMarginV,
            ContentMarginBottom = contentMarginV,
        };

        if (borderWidth > 0)
        {
            style.BorderWidthLeft = borderWidth;
            style.BorderWidthRight = borderWidth;
            style.BorderWidthTop = borderWidth;
            style.BorderWidthBottom = borderWidth;
            style.BorderColor = borderColor ?? Colors.Transparent;
        }

        return style;
    }

    /// <summary>
    /// Small tag chip: grey rounded background with the tag text. Used by the
    /// object-creation reveal card (<see cref="Makeshift.Scenes.Hud.ObjectCreationPanel"/>).
    /// Matches the visual language of <see cref="CreateStateBadge"/> but uses a
    /// neutral colour since tags aren't state-scoped.
    /// </summary>
    public static Label CreateTagBadge(string tag, int fontSize = 11)
    {
        var badge = new Label { Text = $" {tag} " };
        badge.AddThemeFontSizeOverride("font_size", fontSize);
        badge.AddThemeColorOverride("font_color", new Color(0.85f, 0.85f, 0.9f, 0.95f));
        badge.AddThemeStyleboxOverride(
            "normal",
            MakeStylebox(new Color(0.25f, 0.28f, 0.35f, 0.8f), 3, 6, 2));
        return badge;
    }

    /// <summary>
    /// Compact one-line summary of a typed <see cref="BehaviorEntry"/> record
    /// (as delivered by the backend creation response). Used in the
    /// object-creation reveal card behavior list.
    ///
    /// Renders:  <c>target  movement action[:amount]  [+state|-state]  [kb]</c>
    /// </summary>
    public static Label CreateBehaviorLabel(BehaviorEntry entry)
    {
        var label = new Label();
        label.AddThemeFontSizeOverride("font_size", 11);
        label.AddThemeColorOverride("font_color", new Color(0.85f, 0.8f, 0.55f, 0.95f));
        label.Text = BehaviorFormat.FormatBehaviorEntry(entry);
        return label;
    }
}
