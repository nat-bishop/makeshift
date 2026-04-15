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
        var tag = string.IsNullOrEmpty(callerTag) ? "BlueprintMarshal" : callerTag;
        try
        {
            var filtered = new Godot.Collections.Dictionary();
            foreach (var key in dict.Keys)
            {
                if (key.AsString() is string k && !k.StartsWith('_'))
                {
                    filtered[k] = NormalizeIntegerFloats(dict[key]);
                }
            }
            var json = Godot.Json.Stringify(filtered);
            try
            {
                return JsonSerializer.Deserialize(json, MakeshiftJsonContext.Default.Blueprint);
            }
            catch (System.Exception deserEx)
            {
                Logger.Instance?.Warn($"{tag}: Blueprint deserialize failed: {deserEx.Message}");
                Logger.Instance?.Warn($"{tag}: Failing JSON: {json}");
                return null;
            }
        }
        catch (System.Exception e)
        {
            Logger.Instance?.Warn($"{tag}: Blueprint marshal error: {e.Message}");
            return null;
        }
    }

    // Godot's Json.ParseString stores every JSON number as a Variant.Type.Float
    // (double), so a backend int like `"bounce": 0` round-trips to `"bounce": 0.0`
    // after Json.Stringify — which System.Text.Json then refuses to map to an
    // int-backed field or enum. Walk the Variant tree and demote any
    // integer-valued Float back to Int before we stringify. Legitimately
    // fractional values are left alone; float-typed fields on the C# side
    // (e.g. PhysicsData.MassKg) still accept a JSON integer, so no precision
    // is lost on the deserialize side.
    private static Variant NormalizeIntegerFloats(Variant value)
    {
        switch (value.VariantType)
        {
            case Variant.Type.Float:
                double d = value.AsDouble();
                if (!double.IsNaN(d) && !double.IsInfinity(d) &&
                    d >= long.MinValue && d <= long.MaxValue &&
                    d == System.Math.Truncate(d))
                {
                    return (long)d;
                }
                return value;

            case Variant.Type.Dictionary:
                var src = value.AsGodotDictionary();
                var dst = new Godot.Collections.Dictionary();
                foreach (var k in src.Keys)
                {
                    dst[k] = NormalizeIntegerFloats(src[k]);
                }
                return dst;

            case Variant.Type.Array:
                var srcArr = value.AsGodotArray();
                var dstArr = new Godot.Collections.Array();
                foreach (var item in srcArr)
                {
                    dstArr.Add(NormalizeIntegerFloats(item));
                }
                return dstArr;

            default:
                return value;
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
