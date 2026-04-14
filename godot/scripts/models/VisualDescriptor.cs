namespace Makeshift.Models;

/// <summary>
/// LLM-generated visual metadata. Only <see cref="SizeCategory"/> is read
/// by the client (reveal card); other payload fields are ignored.
/// </summary>
public sealed record VisualDescriptor
{
    public string SizeCategory { get; init; } = "medium";
}
