namespace Makeshift.Interfaces;

/// <summary>
/// Anything that can be identified for behavior targeting: exposes a name
/// and a (state-derived) tag list.
/// </summary>
public interface IObjectNamed
{
    string GetObjectName();
    string[] GetTags();
}
