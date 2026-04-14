using Makeshift.Data;

namespace Makeshift.Interfaces;

/// <summary>Holds elemental states (burning / frozen / wet / electrified).</summary>
public interface IStateful
{
    void AddState(StateId state, float duration);
    void RemoveState(StateId state);
    bool HasState(StateId state);
}
