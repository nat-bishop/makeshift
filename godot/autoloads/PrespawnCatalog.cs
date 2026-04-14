using Godot;
using Makeshift.Data;
using Makeshift.Models;
using FileAccess = Godot.FileAccess;

namespace Makeshift.Autoloads;

/// <summary>
/// Hand-authored catalog of prespawned level objects.
///
/// Loaded once from <c>res://data/prespawns.json</c> at autoload startup.
/// Levels look up entries by type_id via <see cref="BuildBlueprint"/> and pass
/// the result to <c>BaseLevel.SpawnPrespawn</c> (which handles runtime id
/// assignment + spawn).
///
/// Adding a new prespawn type:
///   1. Bake a sprite PNG into <c>godot/assets/prespawn/</c> via
///      <c>python backend/scripts/bake_prespawn_sprite.py</c>.
///   2. Add an entry to <c>res://data/prespawns.json</c>.
///   3. Reference it from a level with <c>SpawnPrespawn("type_id", pos)</c>.
/// </summary>
public sealed partial class PrespawnCatalog : Node
{
    public static PrespawnCatalog Instance { get; private set; } = null!;

    private const string CatalogPath = "res://data/prespawns.json";

    private Godot.Collections.Dictionary _entries = new();

    public override void _EnterTree()
    {
        Instance = this;
    }

    public override void _Ready()
    {
        LoadCatalog();
    }

    private void LoadCatalog()
    {
        if (!FileAccess.FileExists(CatalogPath))
        {
            Logger.Instance?.Warn($"PrespawnCatalog: Missing {CatalogPath}");
            return;
        }
        using var file = FileAccess.Open(CatalogPath, FileAccess.ModeFlags.Read);
        if (file is null)
        {
            Logger.Instance?.Warn($"PrespawnCatalog: Failed to open {CatalogPath}");
            return;
        }
        var text = file.GetAsText();
        var variant = Json.ParseString(text);
        if (variant.VariantType != Variant.Type.Dictionary)
        {
            Logger.Instance?.Warn($"PrespawnCatalog: {CatalogPath} is not a JSON object");
            return;
        }
        _entries = variant.AsGodotDictionary();
        Logger.Instance?.Info($"PrespawnCatalog: Loaded {_entries.Count} entries");
    }

    /// <summary>
    /// Build a full GameObject blueprint for <paramref name="typeId"/>,
    /// merging in <paramref name="overrides"/> and preloading the baked
    /// sprite. Returns an empty dict if the type is unknown.
    /// </summary>
    public Godot.Collections.Dictionary BuildBlueprint(string typeId, Godot.Collections.Dictionary? overrides = null)
    {
        if (!_entries.TryGetValue(typeId, out var entryVariant) ||
            entryVariant.VariantType != Variant.Type.Dictionary)
        {
            return new Godot.Collections.Dictionary();
        }

        var bp = entryVariant.AsGodotDictionary().Duplicate(deep: true);
        if (overrides is not null)
        {
            DeepMerge(bp, overrides);
        }

        var spritePath = bp.GetStringOrDefault("sprite", "");
        if (!string.IsNullOrEmpty(spritePath))
        {
            if (ResourceLoader.Load(spritePath) is Texture2D texture)
            {
                bp["_preloaded_sprite"] = texture;
            }
            else
            {
                Logger.Instance?.Warn(
                    $"PrespawnCatalog: Failed to load sprite '{spritePath}' for '{typeId}'");
            }
        }

        // Prespawns bypass the backend img2img pipeline, so the "player holding
        // object" sprite that AffordanceSystem needs on pickup must be baked
        // offline.
        var affordance = (Affordance)(int)bp.GetValueOrDefault("affordance", (int)Affordance.None).AsInt32();
        if (affordance == Affordance.Carry || affordance == Affordance.Mount)
        {
            var combinedPath = $"res://assets/prespawn/combined_{typeId}.png";
            if (ResourceLoader.Exists(combinedPath))
            {
                if (ResourceLoader.Load(combinedPath) is Texture2D combined)
                {
                    bp["_preloaded_combined_sprite"] = combined;
                }
            }
            else
            {
                Logger.Instance?.Warn(
                    $"PrespawnCatalog: Missing combined sprite for carry prespawn '{typeId}'");
            }
        }

        return bp;
    }

    private static void DeepMerge(Godot.Collections.Dictionary target, Godot.Collections.Dictionary source)
    {
        foreach (var key in source.Keys)
        {
            var sv = source[key];
            if (sv.VariantType == Variant.Type.Dictionary &&
                target.TryGetValue(key, out var tv) &&
                tv.VariantType == Variant.Type.Dictionary)
            {
                DeepMerge(tv.AsGodotDictionary(), sv.AsGodotDictionary());
            }
            else
            {
                target[key] = sv;
            }
        }
    }
}
