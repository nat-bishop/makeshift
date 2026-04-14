using System.Collections.Generic;
using System.Text;
using Godot;
using Makeshift.Autoloads;
using Logger = Makeshift.Autoloads.Logger;
using Makeshift.Data;
using Makeshift.Models;
using Makeshift.Scenes.GameObjects;
using Makeshift.Systems;

namespace Makeshift.UI;

/// <summary>
/// Debug overlay attached above each game object: shows identity, HP, physics,
/// velocity, active/born/susceptible states, and (for autonomous objects) a
/// live behavior-pair table with current target, utility, distance and
/// cooldown.
/// </summary>
public sealed partial class DebugLabel : PanelContainer
{
    // --- Display name tables ------------------------------------------------
    // Canonical tables live on BehaviorFormat; this class just references them.

    private static readonly Color ColBright = new(1.0f, 1.0f, 1.0f, 0.95f);
    private static readonly Color ColMid = new(0.75f, 0.75f, 0.75f, 0.85f);
    private static readonly Color ColDim = new(0.55f, 0.55f, 0.55f, 0.7f);
    private static readonly Color ColBehavior = new(0.95f, 0.85f, 0.5f, 0.9f);

    private const int RefreshInterval = 6; // dynamic update every 6 frames (~10fps)

    // --- Subject + wiring ---------------------------------------------------

    private GameObject _gameObject = null!;
    private ObjectBehavior? _behavior;
    private Label _nameLabel = null!;
    private Label _statsLabel = null!;
    private Label _physicsLabel = null!;
    private string _physicsPrefix = "";
    private HFlowContainer _stateContainer = null!;
    private Label? _targetDetailLabel;
    private Label? _speedsLabel;
    private VBoxContainer? _pairsContainer;
    private readonly Dictionary<string, Label> _pairLabels = new();
    private float _aboveOffset = 8.0f;
    private bool _isCreature;

    private int _lastHp = -1;
    private readonly List<StateId> _lastStates = new();
    private string _lastTarget = "";
    private int? _lastMovement = null;
    private int _lastAction;
    private int _lastActionAmount;
    private readonly List<string> _lastPairsKeys = new();
    private int _frameCounter;

    /// <summary>
    /// Initialize the debug panel from its owning <paramref name="gameObj"/>.
    /// Typed signature: DebugLabel only attaches to C# <see cref="GameObject"/>
    /// instances (this matches the only call site in
    /// <see cref="GameObject.InitFromBlueprint"/>).
    /// </summary>
    public void Init(GameObject gameObj)
    {
        _gameObject = gameObj;
        _isCreature = gameObj.Autonomous;
        _behavior = gameObj.GetObjectBehavior();
        Visible = GameManager.Instance.DebugMode;
        SetProcess(Visible);

        AddThemeStyleboxOverride("panel",
            InfoWidgets.MakeStylebox(new Color(0.05f, 0.05f, 0.08f, 0.75f), 3, 4, 3));

        var bp = gameObj.TypedBlueprint;
        var phys = bp?.Physics ?? new PhysicsData();
        var heightCm = phys.HeightCm;
        _aboveOffset = PhysicsComposer.WorldSpriteSize(heightCm) / 2.0f + 4;

        Resized += Reposition;

        var vbox = new VBoxContainer();
        vbox.AddThemeConstantOverride("separation", 1);
        AddChild(vbox);

        // Row 1: name + id
        var row1 = new HBoxContainer();
        row1.AddThemeConstantOverride("separation", 6);
        vbox.AddChild(row1);

        _nameLabel = MakeLabel(10, ColBright);
        _nameLabel.Text = bp?.Name ?? gameObj.ObjectName;
        row1.AddChild(_nameLabel);

        var idLabel = MakeLabel(9, ColDim);
        var objectId = gameObj.ObjectId;
        idLabel.Text = objectId.Length >= 6 ? objectId[..6] : objectId;
        row1.AddChild(idLabel);

        // Row 2: stats (dynamic HP)
        _statsLabel = MakeLabel(9, ColMid);
        vbox.AddChild(_statsLabel);

        // Row 3: physics + velocity (dynamic suffix)
        var surfIdx = (int)phys.Surface;
        var surfStr = surfIdx >= 0 && surfIdx < BehaviorFormat.SurfaceNames.Length
            ? BehaviorFormat.SurfaceNames[surfIdx]
            : "?";
        var pxSize = PhysicsComposer.WorldSpriteSize(heightCm);
        var massKg = (int)phys.MassKg;
        var gravity = phys.Gravity;
        var bounce = phys.Bounce;
        _physicsPrefix = $"{massKg}kg {heightCm}cm({(int)pxSize}px)  g:{gravity} b:{bounce}  {surfStr}";
        _physicsLabel = MakeLabel(9, ColDim);
        _physicsLabel.Text = _physicsPrefix;
        vbox.AddChild(_physicsLabel);

        // Row 4: field + destruction (static, conditional)
        var detailParts = new List<string>();
        if (gameObj.HasField)
        {
            detailParts.Add($"field:{gameObj.FieldRangeCm}cm");
        }
        var destructionName = gameObj.DestructionResultName;
        if (!string.IsNullOrEmpty(destructionName))
        {
            detailParts.Add($"→{destructionName}");
        }
        if (detailParts.Count > 0)
        {
            var detailLabel = MakeLabel(9, ColDim);
            detailLabel.Text = string.Join("  ", detailParts);
            vbox.AddChild(detailLabel);
        }

        // Row 5: initial + susceptible states (static, conditional)
        var stateParts = new List<string>();
        var initialStates = gameObj.InitialStates;
        if (initialStates.Length > 0)
        {
            var names = new List<string>();
            foreach (var sid in initialStates)
            {
                if (sid != StateId.None)
                {
                    names.Add(StateContradictions.GetName(sid));
                }
            }
            if (names.Count > 0)
            {
                stateParts.Add($"born: {string.Join(" ", names)}");
            }
        }
        var susceptibleStates = gameObj.SusceptibleStates;
        if (susceptibleStates.Length > 0)
        {
            var names = new List<string>();
            foreach (var sid in susceptibleStates)
            {
                if (sid != StateId.None)
                {
                    names.Add(StateContradictions.GetName(sid));
                }
            }
            if (names.Count > 0)
            {
                stateParts.Add($"vuln: {string.Join(" ", names)}");
            }
        }
        if (stateParts.Count > 0)
        {
            var propsLabel = MakeLabel(9, ColDim);
            propsLabel.Text = string.Join("  ", stateParts);
            vbox.AddChild(propsLabel);
        }

        // Row 6: state badges (dynamic)
        _stateContainer = new HFlowContainer();
        _stateContainer.AddThemeConstantOverride("h_separation", 2);
        _stateContainer.AddThemeConstantOverride("v_separation", 1);
        vbox.AddChild(_stateContainer);

        // Rows 7-9+: creature behavior details
        if (_isCreature)
        {
            var sep = MakeLabel(8, ColDim);
            sep.Text = "── behaviors ──";
            vbox.AddChild(sep);

            _targetDetailLabel = MakeLabel(9, ColBehavior);
            _targetDetailLabel.Text = "-> idle (no target)";
            vbox.AddChild(_targetDetailLabel);

            _speedsLabel = MakeLabel(9, ColMid);
            vbox.AddChild(_speedsLabel);

            _pairsContainer = new VBoxContainer();
            _pairsContainer.AddThemeConstantOverride("separation", 0);
            vbox.AddChild(_pairsContainer);

            if (_behavior is not null)
            {
                _speedsLabel.Text = FormatSpeeds(_behavior);
            }
        }

        EventBus.Instance.DebugToggled += OnDebugToggled;

        if (Visible)
        {
            Refresh();
        }
    }

    private void Reposition()
    {
        var pos = Position;
        pos.X = -Size.X / 2.0f;
        pos.Y = -_aboveOffset - Size.Y;
        Position = pos;
    }

    public override void _Process(double delta)
    {
        _ = delta;
        // --- Discrete change detection ---
        // Avoid allocating per frame: compare states/pairs in place against
        // the stored "last" copies without building fresh lists.
        var hp = _gameObject.CurrentHp;
        var needsRefresh = hp != _lastHp || !StatesEqualLast();

        if (_isCreature && _behavior is not null)
        {
            var targetName = _behavior.CurrentTargetName;
            var movement = (int)_behavior.CurrentMovement;
            var action = (int)_behavior.CurrentAction;
            var actionAmount = _behavior.CurrentActionAmount;
            if (targetName != _lastTarget
                || movement != _lastMovement
                || action != _lastAction
                || actionAmount != _lastActionAmount)
            {
                needsRefresh = true;
            }

            // Detect pair additions/removals by walking _behavior.Pairs.Keys
            // directly against _lastPairsKeys — no List allocation per frame.
            if (!PairsKeysEqualLast())
            {
                _lastPairsKeys.Clear();
                foreach (var key in _behavior.Pairs.Keys)
                {
                    _lastPairsKeys.Add(key);
                }
                RefreshPairs(_behavior);
            }
        }

        if (needsRefresh)
        {
            Refresh();
        }

        // --- Throttled continuous update ---
        _frameCounter++;
        if (_frameCounter >= RefreshInterval)
        {
            _frameCounter = 0;
            RefreshDynamic();
        }
    }

    /// <summary>
    /// True iff <see cref="_gameObject"/>.States matches <see cref="_lastStates"/>
    /// element-for-element. Walks both without allocating.
    /// </summary>
    private bool StatesEqualLast()
    {
        var current = _gameObject.States;
        if (current.Count != _lastStates.Count)
        {
            return false;
        }
        int i = 0;
        foreach (var s in current)
        {
            if (i >= _lastStates.Count || _lastStates[i] != s)
            {
                return false;
            }
            i++;
        }
        return true;
    }

    /// <summary>
    /// True iff <see cref="_behavior"/>.Pairs.Keys matches
    /// <see cref="_lastPairsKeys"/> element-for-element. Order-sensitive, but
    /// Dictionary.Keys iteration is stable until a structural mutation — any
    /// change in the pair table flips this to false.
    /// </summary>
    private bool PairsKeysEqualLast()
    {
        if (_behavior is null)
        {
            return true;
        }
        if (_behavior.Pairs.Count != _lastPairsKeys.Count)
        {
            return false;
        }
        int i = 0;
        foreach (var key in _behavior.Pairs.Keys)
        {
            if (i >= _lastPairsKeys.Count || _lastPairsKeys[i] != key)
            {
                return false;
            }
            i++;
        }
        return true;
    }

    private void Refresh()
    {
        _lastHp = _gameObject.CurrentHp;
        _lastStates.Clear();
        foreach (var s in _gameObject.States)
        {
            _lastStates.Add(s);
        }

        var dur = (int)_gameObject.Durability;
        var durStr = dur >= 0 && dur < BehaviorFormat.DurNames.Length
            ? BehaviorFormat.DurNames[dur]
            : "?";
        var aff = (int)_gameObject.Affordance;
        var affStr = aff >= 0 && aff < BehaviorFormat.AffNames.Length
            ? BehaviorFormat.AffNames[aff]
            : "?";
        var maxHp = _gameObject.MaxHp;

        var statsText = new StringBuilder();
        statsText.Append($"[{_lastHp}/{maxHp}] {durStr}  {affStr}");
        if (_isCreature)
        {
            var spd = (int)_gameObject.Speed;
            var spdStr = spd >= 0 && spd < BehaviorFormat.SpeedNames.Length
                ? BehaviorFormat.SpeedNames[spd]
                : "?";
            statsText.Append($"  {spdStr}");
        }
        _statsLabel.Text = statsText.ToString();

        // State badges
        foreach (var child in _stateContainer.GetChildren())
        {
            child.QueueFree();
        }
        foreach (var sid in _lastStates)
        {
            _stateContainer.AddChild(
                InfoWidgets.CreateStateBadge(StateContradictions.GetName(sid), 9));
        }

        // Creature behavior: update cached values
        if (_isCreature && _behavior is not null)
        {
            _lastTarget = _behavior.CurrentTargetName;
            _lastMovement = (int)_behavior.CurrentMovement;
            _lastAction = (int)_behavior.CurrentAction;
            _lastActionAmount = _behavior.CurrentActionAmount;
        }
    }

    private void RefreshDynamic()
    {
        // Velocity (GameObject is a RigidBody2D)
        var velMag = (int)_gameObject.LinearVelocity.Length();
        _physicsLabel.Text = $"{_physicsPrefix}  v:{velMag}";

        if (!_isCreature || _behavior is null || _targetDetailLabel is null || _speedsLabel is null)
        {
            return;
        }

        var targetName = _behavior.CurrentTargetName;
        if (string.IsNullOrEmpty(targetName))
        {
            _targetDetailLabel.Text = "-> idle (no target)";
        }
        else
        {
            var movement = (int)_behavior.CurrentMovement;
            var moveStr = movement >= 0 && movement < BehaviorFormat.MoveNames.Length
                ? BehaviorFormat.MoveNames[movement]
                : "?";
            var actStr = FormatAction(_behavior);
            var dist = (int)_behavior.CurrentTargetDistance;
            var utility = _behavior.CurrentBestUtility;
            var cooldown = _behavior.ActionTimer;
            _targetDetailLabel.Text =
                $"-> {moveStr} {targetName} | {actStr}  d:{dist} u:{utility:F1} cd:{cooldown:F1}s";
        }

        _speedsLabel.Text = FormatSpeeds(_behavior);

        // Update pair highlight colors
        foreach (var (tname, label) in _pairLabels)
        {
            if (tname == targetName)
            {
                label.AddThemeColorOverride("font_color", ColBehavior);
            }
            else
            {
                label.AddThemeColorOverride("font_color", ColDim);
            }
        }
    }

    private void RefreshPairs(ObjectBehavior behavior)
    {
        if (_pairsContainer is null)
        {
            return;
        }

        foreach (var child in _pairsContainer.GetChildren())
        {
            child.QueueFree();
        }
        _pairLabels.Clear();

        // Sort pairs by priority descending
        var entries = new List<KeyValuePair<string, BehaviorEntry>>(behavior.Pairs);
        entries.Sort((a, b) => b.Value.Priority.CompareTo(a.Value.Priority));

        foreach (var (tname, entry) in entries)
        {
            var label = MakeLabel(8, ColDim);
            label.Text = BehaviorFormat.FormatPairDebugRow(tname, entry);
            _pairLabels[tname] = label;
            _pairsContainer.AddChild(label);
        }
    }

    private static string FormatAction(ObjectBehavior behavior)
    {
        var action = (int)behavior.CurrentAction;
        var baseStr = action >= 0 && action < BehaviorFormat.ActNames.Length
            ? BehaviorFormat.ActNames[action]
            : "?";
        if (action == 1 || action == 2 || action == 4) // damage, heal, push
        {
            return $"{baseStr}:{behavior.CurrentActionAmount}";
        }
        return baseStr;
    }

    private static string FormatSpeeds(ObjectBehavior behavior)
    {
        var moveSpeed = (int)behavior.MoveSpeed;
        var fleeSpeed = (int)behavior.FleeSpeed;
        var errorCount = behavior.ErrorCount;
        var maxErrors = ObjectBehavior.MaxErrors;
        return $"spd:{moveSpeed}/{fleeSpeed}  err:{errorCount}/{maxErrors}";
    }

    private static Label MakeLabel(int fontSize, Color color)
    {
        var label = new Label();
        label.AddThemeFontSizeOverride("font_size", fontSize);
        label.AddThemeColorOverride("font_color", color);
        return label;
    }

    private void OnDebugToggled(bool on)
    {
        Visible = on;
        SetProcess(on);
        if (on)
        {
            _lastHp = -1;
            _lastStates.Clear();
            _lastTarget = "";
            _lastMovement = null;
            _lastAction = 0;
            _lastActionAmount = 0;
            _lastPairsKeys.Clear();
            _frameCounter = 0;
        }
    }

    public override void _ExitTree()
    {
        if (EventBus.Instance is not null)
        {
            EventBus.Instance.DebugToggled -= OnDebugToggled;
        }
    }

}
