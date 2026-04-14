using System.Text.Json;
using Godot;
using Makeshift.Autoloads;
using Logger = Makeshift.Autoloads.Logger;

namespace Makeshift.Models;

/// <summary>
/// Single source of truth for Blueprint &lt;-&gt; Godot.Collections.Dictionary
/// round-tripping. Consolidates the five duplicate sites that used to hand-roll
/// a Godot.Json.Stringify -&gt; JsonSerializer.Deserialize pipeline.
/// </summary>
public static class BlueprintMarshal
{
    /// <summary>
    /// Deserialize a <see cref="Blueprint"/> from a Godot Dictionary. Internal
    /// <c>_</c>-prefixed keys (e.g. <c>_preloaded_sprite</c>) are stripped so
    /// the JSON payload stays consistent with the backend wire contract.
    /// Returns null on failure; the <paramref name="callerTag"/> is used in
    /// the warning message for caller attribution.
    /// </summary>
    public static Blueprint? FromGodotDictionary(
        Godot.Collections.Dictionary dict, string callerTag = "")
    {
        try
        {
            var filtered = new Godot.Collections.Dictionary();
            foreach (var key in dict.Keys)
            {
                if (key.AsString() is string k && !k.StartsWith('_'))
                {
                    filtered[k] = dict[key];
                }
            }
            var json = Godot.Json.Stringify(filtered);
            try
            {
                return JsonSerializer.Deserialize(json, MakeshiftJsonContext.Default.Blueprint);
            }
            catch (System.Exception deserEx)
            {
                var tag = string.IsNullOrEmpty(callerTag) ? "BlueprintMarshal" : callerTag;
                Logger.Instance?.Warn($"{tag}: Blueprint deserialize failed: {deserEx.Message}");
                Logger.Instance?.Warn($"{tag}: Failing JSON: {json}");
                return null;
            }
        }
        catch (System.Exception e)
        {
            var tag = string.IsNullOrEmpty(callerTag) ? "BlueprintMarshal" : callerTag;
            Logger.Instance?.Warn($"{tag}: Blueprint marshal error: {e.Message}");
            return null;
        }
    }

    /// <summary>
    /// Serialize a typed <see cref="Blueprint"/> back to a Godot Dictionary via
    /// a JSON round-trip so downstream dict-consumers see the same shape the
    /// backend originally delivered.
    /// </summary>
    public static Godot.Collections.Dictionary ToGodotDictionary(Blueprint bp)
    {
        try
        {
            var json = JsonSerializer.Serialize(bp, MakeshiftJsonContext.Default.Blueprint);
            var parsed = Godot.Json.ParseString(json);
            if (parsed.VariantType == Variant.Type.Dictionary)
            {
                return parsed.AsGodotDictionary();
            }
        }
        catch (System.Exception e)
        {
            Logger.Instance?.Warn(
                $"BlueprintMarshal: Blueprint serialize failed: {e.Message}");
        }
        return new Godot.Collections.Dictionary();
    }
}
