using Godot;
using Makeshift.Models;

namespace Makeshift.Interfaces;

/// <summary>
/// World contract: spawns game objects at a position and gathers per-object
/// session-sync state for the backend.
/// </summary>
public interface IWorld
{
    /// <summary>Spawn a game object from a typed blueprint record.</summary>
    void SpawnObject(Blueprint blueprint, Vector2 position);

    /// <summary>
    /// Snapshot of every currently spawned object's blueprint + position,
    /// serialized as a <see cref="Godot.Collections.Array"/> of dictionaries
    /// so it can feed the session-sync JSON payload unchanged.
    /// </summary>
    Godot.Collections.Array GetObjectsData();
}
