using System;
using System.Collections.Generic;
using Godot;
using Makeshift.Autoloads;
using Logger = Makeshift.Autoloads.Logger;
using Makeshift.Data;
using Makeshift.Interfaces;
using Makeshift.Models;

namespace Makeshift.Systems;

/// <summary>
/// Unified object behavior runtime: per-pair utility-based targeting.
/// Handles BOTH active autonomous objects (approach / flee) and reactive
/// objects (ignore + priority &gt; 0). Each subject x target pair carries
/// movement / priority / action / amount / state_action / state_id / force.
///
/// CRITICAL (CLAUDE.md gotcha): runs in <see cref="_PhysicsProcess"/> at
/// ~60 fps. The first action fires immediately at <see cref="ContactRange"/>
/// (48 units), then on a 1.0s cooldown. Bombs and reactive objects depend on
/// this timing.
/// </summary>
public partial class ObjectBehavior : Node
{
    public const float PerceptionRange = 500.0f;
    public const float ContactRange = 48.0f;
    public const float FleeMultiplier = 1.5f;
    public const float ActionCooldown = 1.0f;
    public const float BaseMoveSpeed = 200.0f;
    public const float BaseFleeSpeed = 250.0f;
    public const int MaxErrors = 5;
    public const int LethalThreshold = 100;
    public const float InstantKillDamage = 99999.0f;
    public const float ForceScale = 5.0f;
    public const float ForceModifierImpulse = 40.0f;

    /// <summary>Speed tier (0..4) → multiplier. Mirrors backend SPEED_MULTIPLIER.</summary>
    private static readonly float[] SpeedMultipliers = { 0.3f, 0.6f, 1.0f, 1.5f, 2.0f };

    // StringName cache for hot-path group lookups (per-frame _PhysicsProcess).
    private static readonly StringName GameObjectsGroup = "game_objects";
    private static readonly StringName PlayerGroup = "player";

    /// <summary>Priority level (0..3) → utility weight. Mirrors backend PRIORITY_WEIGHTS.</summary>
    private static readonly float[] PriorityWeights = { 0.0f, 25.0f, 60.0f, 100.0f };

    /// <summary>Action id (0..4) → human-readable name (mirrors backend).</summary>
    private static readonly string[] ActionNames = { "nothing", "damage", "heal", "consume", "push" };

    // Throttle counter for target-selection debug logging (~once/sec at 60fps).
    private int _debugTick;
    private const int DebugTickInterval = 60;

    private RigidBody2D? _owner;
    private string _ownerName = "";
    private bool _isAutonomous;

    private readonly Dictionary<string, BehaviorEntry> _pairTable = new();
    private readonly Dictionary<string, Node> _targetNodes = new();
    private readonly Dictionary<string, Callable> _exitCallables = new();

    private bool _disabledLogged;

    public float MoveSpeed { get; private set; } = BaseMoveSpeed;
    public float FleeSpeed { get; private set; } = BaseFleeSpeed;
    public int ErrorCount { get; private set; }
    public float ActionTimer { get; private set; }

    public string CurrentTargetName { get; private set; } = "";
    public Movement CurrentMovement { get; private set; } = Movement.Ignore;
    public ActionKind CurrentAction { get; private set; }
    public int CurrentActionAmount { get; private set; }
    public float CurrentBestUtility { get; private set; } = -1.0f;
    public float CurrentTargetDistance { get; private set; }

    /// <summary>Strongly-typed view of the current pair table.</summary>
    public IReadOnlyDictionary<string, BehaviorEntry> Pairs => _pairTable;

    public void InitObject(RigidBody2D owner, string objName, SpeedTier speedTier = SpeedTier.Normal, bool isAutonomous = false)
    {
        _owner = owner;
        _ownerName = objName;
        _isAutonomous = isAutonomous;
        if (isAutonomous)
        {
            var idx = (int)speedTier;
            var mult = idx >= 0 && idx < SpeedMultipliers.Length ? SpeedMultipliers[idx] : 1.0f;
            MoveSpeed = BaseMoveSpeed * mult;
            FleeSpeed = BaseFleeSpeed * mult;
        }
        else
        {
            MoveSpeed = 0.0f;
            FleeSpeed = 0.0f;
        }
        EventBus.Instance.ObjectCreated += OnObjectCreated;
        EventBus.Instance.BehaviorUpdated += OnBehaviorUpdated;
        CallDeferred(MethodName.ScanSceneNodes);
    }

    /// <summary>
    /// Iterate all scene-known potential targets and attempt to add any not
    /// already in the pair table. Safe to call repeatedly (e.g. after
    /// behaviors arrive late and a previous TryAddTarget missed due to an
    /// empty lookup).
    /// </summary>
    private void ScanSceneNodes()
    {
        if (_owner is null || !IsInstanceValid(_owner))
        {
            return;
        }
        var tree = _owner.GetTree();
        if (tree is null)
        {
            return;
        }
        foreach (var node in tree.GetNodesInGroup(GameObjectsGroup))
        {
            if (node == _owner)
            {
                continue;
            }
            TryAddTarget(node);
        }
        // Player is in a separate group.
        foreach (var node in tree.GetNodesInGroup(PlayerGroup))
        {
            TryAddTarget(node);
        }
    }

    private void OnObjectCreated(Godot.Collections.Dictionary blueprint)
    {
        var name = blueprint.TryGetValue("name", out var v) ? v.AsString() : "";
        // Defer because the object enters the group only after init_from_blueprint.
        CallDeferred(MethodName.ScanForNew, name);
    }

    private void ScanForNew(string targetName)
    {
        if (_owner is null || string.IsNullOrEmpty(targetName) || _pairTable.ContainsKey(targetName))
        {
            return;
        }
        foreach (var node in _owner.GetTree().GetNodesInGroup(GameObjectsGroup))
        {
            if (node == _owner)
            {
                continue;
            }
            if (node is IObjectNamed named && named.GetObjectName() == targetName)
            {
                TryAddTarget(node);
                break;
            }
        }
    }

    private void TryAddTarget(Node node)
    {
        if (node is not IObjectNamed named)
        {
            return;
        }
        var targetName = named.GetObjectName();
        if (string.IsNullOrEmpty(targetName) || targetName == _ownerName)
        {
            return;
        }
        if (_pairTable.ContainsKey(targetName))
        {
            return;
        }
        var entry = InteractionCache.Instance.LookupBehavior(_ownerName, targetName);
        if (entry is null)
        {
            Logger.Instance?.Info($"ObjectBehavior: '{_ownerName}' has no cached behavior for '{targetName}' yet (scan race?)");
            return;
        }
        _pairTable[targetName] = entry;
        _targetNodes[targetName] = node;
        if (Logger.Instance?.IsDebugEnabled ?? false)
        {
            Logger.Instance.Debug(
                $"ObjectBehavior: '{_ownerName}' added target '{targetName}' " +
                $"mv:{(int)entry.Movement} p:{entry.Priority} " +
                $"act:{(int)entry.Action} amt:{entry.Amount}");
        }
        var capturedName = targetName;
        var callable = Callable.From(() => OnTargetRemoved(capturedName));
        _exitCallables[targetName] = callable;
        node.Connect(Node.SignalName.TreeExiting, callable);
    }

    private void OnTargetRemoved(string targetName)
    {
        _pairTable.Remove(targetName);
        _targetNodes.Remove(targetName);
        _exitCallables.Remove(targetName);
    }

    private void OnBehaviorUpdated(string subjectName)
    {
        if (!string.Equals(subjectName, _ownerName, StringComparison.OrdinalIgnoreCase))
        {
            return;
        }
        // Refresh all existing pairs from InteractionCache.
        var keys = new List<string>(_pairTable.Keys);
        foreach (var tname in keys)
        {
            var entry = InteractionCache.Instance.LookupBehavior(_ownerName, tname);
            if (entry is not null)
            {
                _pairTable[tname] = entry;
            }
        }
        // Retry adding any scene nodes that were missed by earlier scans (the
        // common case: ScanSceneNodes ran before our behaviors_ready WS
        // message arrived, so LookupBehavior returned null and the target was
        // skipped).
        ScanSceneNodes();
    }

    public override void _PhysicsProcess(double delta)
    {
        if (ErrorCount >= MaxErrors)
        {
            if (!_disabledLogged)
            {
                Logger.Instance?.Warn($"ObjectBehavior: Disabled after {MaxErrors} errors for '{_ownerName}'");
                _disabledLogged = true;
            }
            return;
        }
        if (_owner is null || !IsInstanceValid(_owner))
        {
            return;
        }
        ActionTimer = Mathf.Max(0.0f, ActionTimer - (float)delta);

        // Clear debug state (overwritten below if a target is found). Only
        // touched when the debug overlay is live — avoids per-frame property
        // writes for every object when debug is off.
        var debugMode = GameManager.Instance?.DebugMode ?? false;
        if (debugMode)
        {
            CurrentTargetName = "";
            CurrentMovement = Movement.Ignore;
            CurrentAction = ActionKind.None;
            CurrentActionAmount = 0;
            CurrentBestUtility = -1.0f;
            CurrentTargetDistance = 0.0f;
        }

        // Utility scoring for ALL pairs (active + reactive). Skip inert pairs,
        // drop out-of-range, apply the flee-vs-approach multiplier.
        Node? bestTarget = null;
        float bestUtility = -1.0f;
        BehaviorEntry? bestEntry = null;

        foreach (var (tname, entry) in _pairTable)
        {
            if (!_targetNodes.TryGetValue(tname, out var node) || !IsInstanceValid(node))
            {
                continue;
            }
            if (node is not Node2D node2d)
            {
                continue;
            }

            var movement = entry.Movement;
            var priority = entry.Priority;
            var dist = _owner.GlobalPosition.DistanceTo(node2d.GlobalPosition);
            var weight = priority >= 0 && priority < PriorityWeights.Length
                ? PriorityWeights[priority]
                : 0.0f;

            var utility = (movement, priority) switch
            {
                (Movement.Ignore, 0) => -1f,
                _ when dist > PerceptionRange => -1f,
                (Movement.Flee, _) => (weight / (1.0f + dist / PerceptionRange)) * FleeMultiplier,
                _ => weight / (1.0f + dist / PerceptionRange),
            };

            if (utility > bestUtility)
            {
                bestUtility = utility;
                bestTarget = node;
                bestEntry = entry;
            }
        }

        if (bestTarget is null || bestEntry is null)
        {
            return;
        }

        var bestTargetNode2d = bestTarget as Node2D;
        if (bestTargetNode2d is null)
        {
            return;
        }

        // Expose for debug overlay — only when the overlay is active.
        if (debugMode)
        {
            CurrentTargetName = bestTarget is IObjectNamed nm ? nm.GetObjectName() : "?";
            CurrentMovement = bestEntry.Movement;
            CurrentAction = bestEntry.Action;
            CurrentActionAmount = bestEntry.Amount;
            CurrentBestUtility = bestUtility;
            CurrentTargetDistance = _owner.GlobalPosition.DistanceTo(bestTargetNode2d.GlobalPosition);
        }

        var dir = (bestTargetNode2d.GlobalPosition - _owner.GlobalPosition).Normalized();
        var d = _owner.GlobalPosition.DistanceTo(bestTargetNode2d.GlobalPosition);

        _debugTick++;
        if (_debugTick >= DebugTickInterval)
        {
            _debugTick = 0;
            if (Logger.Instance?.IsDebugEnabled ?? false)
            {
                var actionIdx = (int)bestEntry.Action;
                var actionName = actionIdx >= 0 && actionIdx < ActionNames.Length
                    ? ActionNames[actionIdx]
                    : "?";
                var tname = bestTarget is IObjectNamed bnm ? bnm.GetObjectName() : "?";
                Logger.Instance.Debug(
                    $"ObjectBehavior: '{_ownerName}' → '{tname}' " +
                    $"mv:{(int)bestEntry.Movement} u:{bestUtility:F1} " +
                    $"dist:{d:F0} act:{actionName}");
            }
        }

        switch (bestEntry.Movement)
        {
            case Movement.Approach:
                if (_isAutonomous)
                {
                    WorldMutations.ApplyMovementForce(_owner, dir, MoveSpeed, MoveSpeed);
                }
                if (d <= ContactRange && ActionTimer <= 0.0f)
                {
                    ExecuteAction(bestEntry, bestTarget);
                    ActionTimer = ActionCooldown;
                }
                break;
            case Movement.Flee:
                if (_isAutonomous)
                {
                    WorldMutations.ApplyMovementForce(_owner, -dir, FleeSpeed, FleeSpeed);
                }
                break;
            case Movement.Ignore:
                if (d <= ContactRange && ActionTimer <= 0.0f)
                {
                    ExecuteAction(bestEntry, bestTarget);
                    ActionTimer = ActionCooldown;
                }
                break;
        }
    }

    private void RecordError(string reason)
    {
        ErrorCount++;
        Logger.Instance?.Warn($"ObjectBehavior: Action error for '{_ownerName}' - {reason} ({ErrorCount}/{MaxErrors})");
    }

    private void ExecuteAction(BehaviorEntry entry, Node target)
    {
        if (!IsInstanceValid(target))
        {
            RecordError("invalid target");
            return;
        }
        if (_owner is null)
        {
            return;
        }

        var action = entry.Action;
        var amount = entry.Amount;
        var stateAction = entry.StateAction;
        var stateId = entry.StateId;
        var force = entry.Force;

        if (action != ActionKind.None)
        {
            var tname = target is IObjectNamed nm ? nm.GetObjectName() : target.Name.ToString();
            var actionIdx = (int)action;
            var actionName = actionIdx >= 0 && actionIdx < ActionNames.Length
                ? ActionNames[actionIdx]
                : "?";
            Logger.Instance?.Info($"ObjectBehavior: '{_ownerName}' → {actionName} on '{tname}' ({amount})");
        }

        // Primary action
        switch (action)
        {
            case ActionKind.None:
                break;
            case ActionKind.Damage:
            {
                if (target is not IDamageable)
                {
                    RecordError("target missing take_damage");
                    return;
                }
                var effective = amount >= LethalThreshold
                    ? InstantKillDamage
                    : (amount > 0 ? amount : 15.0f);
                WorldMutations.ApplyDamage(target, effective);
                break;
            }
            case ActionKind.Heal:
            {
                if (target is not IHealable)
                {
                    RecordError("target missing heal");
                    return;
                }
                WorldMutations.ApplyHeal(target, amount > 0 ? amount : 10.0f);
                break;
            }
            case ActionKind.Consume:
            {
                if (target is not IDamageable)
                {
                    RecordError("target missing take_damage for consume");
                    return;
                }
                WorldMutations.ApplyDamage(target, InstantKillDamage);
                break;
            }
            case ActionKind.Push:
            {
                if (target is Node2D tn2d)
                {
                    var forceDir = (tn2d.GlobalPosition - _owner.GlobalPosition).Normalized();
                    var magnitude = amount > 0 ? amount * ForceScale : 30.0f * ForceScale;
                    WorldMutations.ApplyImpulse(target, forceDir, magnitude);
                }
                break;
            }
        }

        // State modifier
        if (stateAction == StateAction.Add && stateId != StateId.None)
        {
            if (target is IStateful)
            {
                WorldMutations.ApplyAddState(target, stateId, 10.0f);
            }
        }
        else if (stateAction == StateAction.Remove && stateId != StateId.None)
        {
            if (target is IStateful)
            {
                WorldMutations.ApplyRemoveState(target, stateId);
            }
        }

        // Force modifier (knockback on damage only)
        if (force == 1 && action == ActionKind.Damage && target is Node2D node2D)
        {
            var forceDir = (node2D.GlobalPosition - _owner.GlobalPosition).Normalized();
            WorldMutations.ApplyImpulse(target, forceDir, ForceModifierImpulse * ForceScale);
        }
    }

    public override void _ExitTree()
    {
        if (EventBus.Instance is not null)
        {
            EventBus.Instance.ObjectCreated -= OnObjectCreated;
            EventBus.Instance.BehaviorUpdated -= OnBehaviorUpdated;
        }

        // Disconnect every TreeExiting callable wired in TryAddTarget. Without
        // this, freed ObjectBehavior instances get called when their targets
        // later exit the tree — a classic stale-callable crash across reloads.
        foreach (var (targetName, callable) in _exitCallables)
        {
            if (_targetNodes.TryGetValue(targetName, out var node) && IsInstanceValid(node))
            {
                node.Disconnect(Node.SignalName.TreeExiting, callable);
            }
        }
        _exitCallables.Clear();
        _targetNodes.Clear();
        _pairTable.Clear();
    }

}
