using System;
using System.Collections.Generic;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Godot;
using Makeshift.Interfaces;
using Makeshift.Models;
using HttpClient = System.Net.Http.HttpClient;
using HttpMethod = System.Net.Http.HttpMethod;
using HttpRequestMessage = System.Net.Http.HttpRequestMessage;
using HttpResponseMessage = System.Net.Http.HttpResponseMessage;
using StringContent = System.Net.Http.StringContent;
using FileAccess = Godot.FileAccess;

namespace Makeshift.Autoloads;

/// <summary>
/// Backend client — HTTP + WebSocket bridge to the Python FastAPI server.
/// Uses a static shared <see cref="HttpClient"/>, Godot's <see cref="WebSocketPeer"/>
/// polled from <see cref="_Process"/>, and <c>System.Text.Json</c> via
/// <see cref="MakeshiftJsonContext"/> for typed message dispatch. Background tasks
/// are tracked in a static set to prevent GC before completion.
/// <c>process_mode = PROCESS_MODE_ALWAYS</c> is required for WS keepalive during pause.
/// </summary>
public sealed partial class Backend : Node
{
    public static Backend Instance { get; private set; } = null!;

    // --- Config ------------------------------------------------------------

    public const string BaseUrl = "http://127.0.0.1:8000";
    public const string WsUrl = "ws://127.0.0.1:8000";
    public const string SavePath = "user://save.json";
    public const double SyncInterval = 10.0;
    public const double MaxReconnectDelay = 30.0;

    // Cached StringName for hot-path group lookup.
    private static readonly StringName WorldGroup = "world";

    // Sprite cache LRU cap — per cache, not total. Textures hold GPU memory so
    // the ceiling stops Backend (an autoload) from leaking across level resets.
    private const int SpriteCacheCapacity = 128;

    private static readonly HttpClient _http = new() { BaseAddress = new Uri(BaseUrl) };
    private static readonly HashSet<Task> _backgroundTasks = new();

    // --- Runtime state -----------------------------------------------------

    public string SessionId { get; private set; } = "";
    public bool OfflineMode { get; private set; }

    private WebSocketPeer? _ws;
    private bool _wsConnected;
    private double _reconnectTimer;
    private double _reconnectDelay = 1.0;
    private double _syncTimer;
    private bool _stateDirty;

    private readonly LruTextureCache _spriteCache = new(SpriteCacheCapacity);
    private readonly LruTextureCache _combinedSpriteCache = new(SpriteCacheCapacity);
    private readonly LruTextureCache _destructionSpriteCache = new(SpriteCacheCapacity);
    private readonly HashSet<string> _pendingSprites = new();

    private readonly CancellationTokenSource _shutdown = new();

    // --- Lifecycle ---------------------------------------------------------

    public override void _EnterTree()
    {
        Instance = this;
    }

    public override void _Ready()
    {
        ProcessMode = ProcessModeEnum.Always;
        LoadSessionId();
    }

    public override void _ExitTree()
    {
        try
        {
            _shutdown.Cancel();
        }
        catch (ObjectDisposedException)
        {
            // Already disposed — safe to ignore.
        }

        try
        {
            _ws?.Close();
        }
        catch (Exception ex)
        {
            Logger.Instance?.Warn($"Backend: WS close during shutdown threw: {ex.Message}");
        }
        _ws = null;

        try
        {
            _shutdown.Dispose();
        }
        catch (Exception)
        {
            // Ignored.
        }
    }

    public override void _Process(double delta)
    {
        ProcessWebsocket(delta);
        ProcessSyncTimer(delta);
        ProcessReconnect(delta);
    }

    // --- Public async API (C# callers) ------------------------------------

    /// <summary>
    /// Create a new backend session. On success caches <see cref="SessionId"/>,
    /// persists it to disk, and opens the WebSocket.
    /// </summary>
    public async Task<Godot.Collections.Dictionary> CreateSessionAsync()
    {
        var result = await HttpPostAsync("/api/sessions", "{}");
        if (result.GetBoolOrDefault("error"))
        {
            Logger.Instance?.Warn($"Backend: Session creation failed: {result.GetStringOrDefault("message", "unknown")}");
            OfflineMode = true;
            return result;
        }

        SessionId = result.GetStringOrDefault("session_id");
        if (!string.IsNullOrEmpty(SessionId))
        {
            SaveSessionId();
            InteractionCache.Instance?.ClearAll();
            ConnectWebsocket();
        }

        Logger.Instance?.Info($"Backend: Session created id={SessionId}");
        return result;
    }

    public async Task<Godot.Collections.Dictionary> RestoreSessionAsync(string id)
    {
        var result = await HttpGetAsync($"/api/sessions/{id}");
        if (result.GetBoolOrDefault("error"))
        {
            Logger.Instance?.Warn($"Backend: Session restore failed for {id}: {result.GetStringOrDefault("message", "unknown")}");
            return result;
        }

        Logger.Instance?.Info($"Backend: Session restored id={id}");
        SessionId = id;
        SaveSessionId();
        InteractionCache.Instance?.ClearAll();
        ConnectWebsocket();
        return result;
    }

    public async Task<Godot.Collections.Dictionary> CreateObjectAsync(string description)
    {
        if (string.IsNullOrEmpty(SessionId))
        {
            return new Godot.Collections.Dictionary
            {
                ["error"] = true,
                ["message"] = "No active session",
            };
        }

        Logger.Instance?.Info($"Backend: Creating object from '{description}'");

        var bodyJson = JsonSerializer.Serialize(
            new Dictionary<string, string> { ["description"] = description });
        var result = await HttpPostAsync($"/api/sessions/{SessionId}/objects", bodyJson);

        if (result.GetBoolOrDefault("error"))
        {
            Logger.Instance?.Warn($"Backend: Object creation failed: {result.GetStringOrDefault("message", "unknown")}");
            return result;
        }

        // Backend may return either {"blueprint": {...}} or the blueprint
        // fields at the root — unwrap both shapes.
        var blueprintDict = result.ContainsKey("blueprint")
            ? (Godot.Collections.Dictionary)result["blueprint"]
            : result;

        var objName = blueprintDict.GetStringOrDefault("name", "?");
        var objectId = blueprintDict.GetStringOrDefault("id", "?");
        Logger.Instance?.Info($"Backend: Object created '{objName}' (id={objectId})");

        EventBus.Instance.EmitSignal(EventBus.SignalName.ObjectCreated, blueprintDict);
        if (!string.IsNullOrEmpty(objectId) && objectId != "?")
        {
            _pendingSprites.Add(objectId);
        }

        return result;
    }

    public async Task SyncStateAsync()
    {
        if (string.IsNullOrEmpty(SessionId) || OfflineMode)
        {
            return;
        }
        Logger.Instance?.Debug("Backend: Syncing state to server");
        var state = GatherGameState();
        var json = Godot.Json.Stringify(state);
        await HttpPutAsync($"/api/sessions/{SessionId}/sync", json);
    }

    /// <summary>
    /// Fire-and-forget: create the debris object and spawn it at the death
    /// position. The source object may already be freed by the time this
    /// completes.
    /// </summary>
    public void RequestDestructionSpawn(string debrisName, Vector2 pos)
    {
        TrackBackground(RequestDestructionSpawnAsync(debrisName, pos));
    }

    private async Task RequestDestructionSpawnAsync(string debrisName, Vector2 pos)
    {
        var result = await CreateObjectAsync(debrisName);
        if (result.GetBoolOrDefault("error"))
        {
            Logger.Instance?.Warn($"Backend: Failed to create destruction debris '{debrisName}'");
            return;
        }

        var bpDict = result.ContainsKey("blueprint")
            ? (Godot.Collections.Dictionary)result["blueprint"]
            : result;

        // If a pre-generated img2img destruction sprite exists, attach it so the
        // debris object can use it immediately instead of waiting for text-to-image.
        var preloaded = _destructionSpriteCache.Get(debrisName);
        if (preloaded is not null)
        {
            bpDict["_preloaded_sprite"] = preloaded;
        }

        var worldNode = GetTree().GetFirstNodeInGroup(WorldGroup);
        if (worldNode is IWorld world)
        {
            var blueprint = BlueprintMarshal.FromGodotDictionary(bpDict, "Backend");
            if (blueprint is not null)
            {
                world.SpawnObject(blueprint, pos);
                Logger.Instance?.Info($"Backend: Spawned destruction debris '{debrisName}'");
            }
            else
            {
                Logger.Instance?.Warn($"Backend: Destruction blueprint deserialize failed for '{debrisName}' — nothing spawned");
            }
        }
        else
        {
            Logger.Instance?.Warn(
                $"Backend: No IWorld node in 'world' group — destruction debris '{debrisName}' dropped");
        }
    }

    /// <summary>
    /// Notify backend that an object's states changed (triggers behavioral re-eval).
    /// </summary>
    public void SendStateChanged(string objectName, Godot.Collections.Array activeStates)
    {
        if (_ws is null || !_wsConnected)
        {
            return;
        }
        var msg = new Godot.Collections.Dictionary
        {
            ["type"] = "state_changed",
            ["object_name"] = objectName,
            ["active_states"] = activeStates,
        };
        _ws.SendText(Godot.Json.Stringify(msg));
    }

    public Texture2D? GetCachedSprite(string objectId) =>
        _spriteCache.Get(objectId);

    public Texture2D? GetCombinedSprite(string objectId) =>
        _combinedSpriteCache.Get(objectId);

    public Texture2D? GetDestructionSprite(string debrisName) =>
        _destructionSpriteCache.Get(debrisName);

    public void MarkDirty()
    {
        _stateDirty = true;
    }

    // --- WebSocket ---------------------------------------------------------

    private void ConnectWebsocket()
    {
        if (string.IsNullOrEmpty(SessionId))
        {
            Logger.Instance?.Warn("Backend: ConnectWebsocket called with empty session_id");
            return;
        }

        _ws = new WebSocketPeer();
        var url = $"{WsUrl}/ws/{SessionId}";
        var err = _ws.ConnectToUrl(url);
        if (err != Error.Ok)
        {
            Logger.Instance?.Warn($"Backend: WebSocket connection failed: {(int)err}");
            _wsConnected = false;
            _reconnectTimer = _reconnectDelay;
        }
        else
        {
            _wsConnected = false; // will flip on STATE_OPEN
        }
    }

    private void ProcessWebsocket(double _delta)
    {
        if (_ws is null)
        {
            return;
        }

        _ws.Poll();

        var state = _ws.GetReadyState();
        switch (state)
        {
            case WebSocketPeer.State.Open:
                if (!_wsConnected)
                {
                    _wsConnected = true;
                    _reconnectDelay = 1.0;
                    Logger.Instance?.Info($"Backend: WebSocket connected to session {SessionId}");
                    foreach (var objId in _pendingSprites)
                    {
                        var requestMsg = new Godot.Collections.Dictionary
                        {
                            ["type"] = "request_sprite",
                            ["object_id"] = objId,
                        };
                        _ws.SendText(Godot.Json.Stringify(requestMsg));
                    }
                }

                while (_ws.GetAvailablePacketCount() > 0)
                {
                    var packet = _ws.GetPacket();
                    var text = packet.GetStringFromUtf8();
                    HandleWsMessage(text);
                }
                break;

            case WebSocketPeer.State.Closing:
                break;

            case WebSocketPeer.State.Closed:
                _wsConnected = false;
                _reconnectTimer = _reconnectDelay;
                break;
        }
    }

    private void HandleWsMessage(string text)
    {
        WsMessage? message;
        try
        {
            message = JsonSerializer.Deserialize(text, MakeshiftJsonContext.Default.WsMessage);
        }
        catch (JsonException ex)
        {
            Logger.Instance?.Warn($"Backend: Failed to parse WS message: {ex.Message}");
            return;
        }

        if (message is null)
        {
            Logger.Instance?.Warn("Backend: WS message deserialized to null");
            return;
        }

        switch (message)
        {
            case SpriteReadyMessage m:
                TrackBackground(HandleSpriteReadyAsync(m));
                break;
            case SpriteFailedMessage m:
                HandleSpriteFailed(m);
                break;
            case CombinedSpriteReadyMessage m:
                TrackBackground(HandleCombinedSpriteReadyAsync(m));
                break;
            case DestructionSpriteReadyMessage m:
                TrackBackground(HandleDestructionSpriteReadyAsync(m));
                break;
            case BehaviorsReadyMessage m:
                HandleBehaviorsReady(m);
                break;
            case BehaviorUpdatedMessage m:
                HandleBehaviorUpdated(m);
                break;
            case WsErrorMessage m:
                HandleWsError(m);
                break;
        }
    }

    private async Task<Texture2D?> FetchTextureAsync(string spriteUrl, string label)
    {
        var fullUrl = BaseUrl + spriteUrl;
        byte[] body;
        try
        {
            body = await _http.GetByteArrayAsync(fullUrl, _shutdown.Token);
        }
        catch (OperationCanceledException)
        {
            return null;
        }
        catch (Exception ex)
        {
            Logger.Instance?.Warn($"Backend: {label} fetch failed for {spriteUrl}: {ex.Message}");
            return null;
        }

        if (body.Length == 0)
        {
            Logger.Instance?.Warn($"Backend: {label} fetch returned empty body for {spriteUrl}");
            return null;
        }

        var image = new Image();
        if (image.LoadPngFromBuffer(body) != Error.Ok)
        {
            Logger.Instance?.Warn($"Backend: Failed to decode {label} PNG from {spriteUrl}");
            return null;
        }
        return ImageTexture.CreateFromImage(image);
    }

    private async Task HandleSpriteReadyAsync(SpriteReadyMessage m)
    {
        if (string.IsNullOrEmpty(m.ObjectId) || string.IsNullOrEmpty(m.SpriteUrl))
        {
            Logger.Instance?.Warn($"Backend: Malformed sprite_ready message (object_id='{m.ObjectId}', sprite_url='{m.SpriteUrl}')");
            return;
        }

        var texture = await FetchTextureAsync(m.SpriteUrl, "sprite");
        if (texture is null)
        {
            return;
        }

        // Marshal the cache mutation + signal emission back to the main thread.
        // HttpClient continuations resume on the threadpool (no Godot sync ctx),
        // so touching _spriteCache / _pendingSprites here would race _Process.
        CallDeferred(MethodName.ApplySpriteReady, m.ObjectId, texture);
    }

    private void ApplySpriteReady(string objectId, Texture2D texture)
    {
        _spriteCache.Set(objectId, texture);
        _pendingSprites.Remove(objectId);
        Logger.Instance?.Info($"Backend: Sprite ready for {objectId}");
        EventBus.Instance.EmitSignal(EventBus.SignalName.SpriteReady, objectId, texture);
    }

    private void HandleSpriteFailed(SpriteFailedMessage m)
    {
        if (string.IsNullOrEmpty(m.ObjectId))
        {
            Logger.Instance?.Warn("Backend: sprite_failed message missing object_id");
            return;
        }
        _pendingSprites.Remove(m.ObjectId);
        Logger.Instance?.Warn($"Backend: Sprite generation failed for {m.ObjectId}: {m.Reason}");
        EventBus.Instance.EmitSignal(EventBus.SignalName.SpriteFailed, m.ObjectId);
    }

    private async Task HandleCombinedSpriteReadyAsync(CombinedSpriteReadyMessage m)
    {
        if (string.IsNullOrEmpty(m.ObjectId) || string.IsNullOrEmpty(m.SpriteUrl))
        {
            Logger.Instance?.Warn($"Backend: Malformed combined_sprite_ready message (object_id='{m.ObjectId}', sprite_url='{m.SpriteUrl}')");
            return;
        }

        var texture = await FetchTextureAsync(m.SpriteUrl, "combined sprite");
        if (texture is null)
        {
            return;
        }

        CallDeferred(MethodName.ApplyCombinedSpriteReady, m.ObjectId, texture);
    }

    private void ApplyCombinedSpriteReady(string objectId, Texture2D texture)
    {
        // Buffer in cache so objects can pick it up even if they aren't placed yet.
        _combinedSpriteCache.Set(objectId, texture);
        EventBus.Instance.EmitSignal(EventBus.SignalName.CombinedSpriteReady, objectId, texture);
    }

    private async Task HandleDestructionSpriteReadyAsync(DestructionSpriteReadyMessage m)
    {
        if (string.IsNullOrEmpty(m.DestructionResultName) || string.IsNullOrEmpty(m.SpriteUrl))
        {
            Logger.Instance?.Warn($"Backend: Malformed destruction_sprite_ready message (name='{m.DestructionResultName}', url='{m.SpriteUrl}')");
            return;
        }

        var texture = await FetchTextureAsync(m.SpriteUrl, "destruction sprite");
        if (texture is null)
        {
            return;
        }

        CallDeferred(MethodName.ApplyDestructionSpriteReady, m.DestructionResultName, texture);
    }

    private void ApplyDestructionSpriteReady(string debrisName, Texture2D texture)
    {
        _destructionSpriteCache.Set(debrisName, texture);
        Logger.Instance?.Info($"Backend: Destruction sprite cached for debris '{debrisName}'");
    }

    private void HandleBehaviorsReady(BehaviorsReadyMessage m)
    {
        StoreBehaviorBatch(m.SubjectName, m.Behaviors);
        EventBus.Instance.EmitSignal(EventBus.SignalName.BehaviorUpdated, m.SubjectName);
        Logger.Instance?.Info($"Backend: Behaviors ready for '{m.SubjectName}' ({m.Behaviors.Length} entries)");
    }

    private void HandleBehaviorUpdated(BehaviorUpdatedMessage m)
    {
        StoreBehaviorBatch(m.SubjectName, m.Behaviors);
        EventBus.Instance.EmitSignal(EventBus.SignalName.BehaviorUpdated, m.SubjectName);
        Logger.Instance?.Info($"Backend: Behavior updated for '{m.SubjectName}' ({m.Behaviors.Length} entries)");
    }

    private static void StoreBehaviorBatch(string subjectName, BehaviorEntry[] entries)
    {
        var cache = InteractionCache.Instance;
        if (cache is null)
        {
            return;
        }
        foreach (var entry in entries)
        {
            var target = entry.Target;
            if (!string.IsNullOrEmpty(target))
            {
                cache.StoreBehavior(subjectName, target, entry);
            }
        }
    }

    private void HandleWsError(WsErrorMessage m)
    {
        Logger.Instance?.Warn($"Backend WS error: {m.Message}");
    }

    private void ProcessReconnect(double delta)
    {
        if (_wsConnected || _ws is null)
        {
            return;
        }
        if (_reconnectTimer <= 0.0)
        {
            return;
        }

        _reconnectTimer -= delta;
        if (_reconnectTimer <= 0.0)
        {
            Logger.Instance?.Debug($"Backend: Reconnecting WebSocket (delay={_reconnectDelay:F1}s)");
            _reconnectDelay = Math.Min(_reconnectDelay * 2.0, MaxReconnectDelay);
            ConnectWebsocket();
        }
    }

    // --- Sync timer --------------------------------------------------------

    private void ProcessSyncTimer(double delta)
    {
        if (string.IsNullOrEmpty(SessionId) || OfflineMode || !_stateDirty)
        {
            return;
        }

        _syncTimer += delta;
        if (_syncTimer >= SyncInterval)
        {
            _syncTimer = 0.0;
            _stateDirty = false;
            OnSyncTimer();
        }
    }

    private void OnSyncTimer()
    {
        TrackBackground(SyncStateAsync());
    }

    private Godot.Collections.Dictionary GatherGameState()
    {
        var objects = new Godot.Collections.Array();
        var worldNode = GetTree().GetFirstNodeInGroup(WorldGroup);
        if (worldNode is IWorld world)
        {
            objects = world.GetObjectsData();
        }
        else if (worldNode is not null)
        {
            Logger.Instance?.Warn(
                "Backend: World node in 'world' group does not implement IWorld — sync payload will be empty");
        }
        return new Godot.Collections.Dictionary { ["objects"] = objects };
    }

    // --- HTTP helpers ------------------------------------------------------

    private async Task<Godot.Collections.Dictionary> HttpPostAsync(string path, string bodyJson)
    {
        return await RequestAsync(HttpMethod.Post, path, bodyJson);
    }

    private async Task<Godot.Collections.Dictionary> HttpGetAsync(string path)
    {
        return await RequestAsync(HttpMethod.Get, path, null);
    }

    private async Task<Godot.Collections.Dictionary> HttpPutAsync(string path, string bodyJson)
    {
        return await RequestAsync(HttpMethod.Put, path, bodyJson);
    }

    private async Task<Godot.Collections.Dictionary> RequestAsync(HttpMethod method, string path, string? bodyJson)
    {
        Logger.Instance?.Debug($"Backend: {method.Method} {BaseUrl}{path}");
        using var request = new HttpRequestMessage(method, path);
        if (!string.IsNullOrEmpty(bodyJson))
        {
            request.Content = new StringContent(bodyJson, Encoding.UTF8, "application/json");
        }

        HttpResponseMessage response;
        try
        {
            response = await _http.SendAsync(request, _shutdown.Token);
        }
        catch (OperationCanceledException)
        {
            return new Godot.Collections.Dictionary
            {
                ["error"] = true,
                ["message"] = "cancelled",
                ["cancelled"] = true,
            };
        }
        catch (Exception ex)
        {
            Logger.Instance?.Warn($"Backend: HTTP request failed {path}: {ex.Message}");
            return new Godot.Collections.Dictionary
            {
                ["error"] = true,
                ["message"] = $"HTTP request failed: {ex.Message}",
            };
        }

        using (response)
        {
            var statusCode = (int)response.StatusCode;

            if (statusCode == 304)
            {
                return new Godot.Collections.Dictionary { ["status_code"] = 304 };
            }

            if (statusCode < 200 || statusCode >= 300)
            {
                Logger.Instance?.Warn($"Backend: HTTP {statusCode} from {path}");
                return new Godot.Collections.Dictionary
                {
                    ["error"] = true,
                    ["message"] = $"HTTP {statusCode}",
                    ["status_code"] = statusCode,
                };
            }

            string text;
            try
            {
                text = await response.Content.ReadAsStringAsync(_shutdown.Token);
            }
            catch (OperationCanceledException)
            {
                return new Godot.Collections.Dictionary
                {
                    ["error"] = true,
                    ["message"] = "cancelled",
                    ["cancelled"] = true,
                };
            }
            catch (Exception ex)
            {
                Logger.Instance?.Warn($"Backend: Failed to read body from {path}: {ex.Message}");
                return new Godot.Collections.Dictionary
                {
                    ["error"] = true,
                    ["message"] = "body read error",
                };
            }

            if (string.IsNullOrEmpty(text))
            {
                return new Godot.Collections.Dictionary { ["status_code"] = statusCode };
            }

            var variant = Godot.Json.ParseString(text);
            Godot.Collections.Dictionary result;
            if (variant.VariantType == Variant.Type.Dictionary)
            {
                result = variant.AsGodotDictionary();
            }
            else if (variant.VariantType == Variant.Type.Nil)
            {
                Logger.Instance?.Warn($"Backend: JSON parse error from {path}");
                return new Godot.Collections.Dictionary
                {
                    ["error"] = true,
                    ["message"] = "JSON parse error",
                };
            }
            else
            {
                result = new Godot.Collections.Dictionary { ["data"] = variant };
            }

            // Copy the ETag header into the result dict so callers can use it
            // for conditional requests.
            if (response.Headers.TryGetValues("ETag", out var etags))
            {
                foreach (var etag in etags)
                {
                    result["etag"] = etag;
                    break;
                }
            }

            result["status_code"] = statusCode;
            return result;
        }
    }

    // --- Session persistence ----------------------------------------------

    private void SaveSessionId()
    {
        if (string.IsNullOrEmpty(SessionId))
        {
            return;
        }
        using var file = FileAccess.Open(SavePath, FileAccess.ModeFlags.Write);
        if (file is not null)
        {
            var payload = new Godot.Collections.Dictionary { ["session_id"] = SessionId };
            file.StoreString(Godot.Json.Stringify(payload));
            Logger.Instance?.Debug("Backend: Saved session_id to disk");
        }
    }

    private void LoadSessionId()
    {
        if (!FileAccess.FileExists(SavePath))
        {
            return;
        }
        using var file = FileAccess.Open(SavePath, FileAccess.ModeFlags.Read);
        if (file is null)
        {
            return;
        }
        var text = file.GetAsText();
        var variant = Godot.Json.ParseString(text);
        if (variant.VariantType == Variant.Type.Dictionary)
        {
            var dict = variant.AsGodotDictionary();
            var id = dict.GetStringOrDefault("session_id");
            if (!string.IsNullOrEmpty(id))
            {
                SessionId = id;
                Logger.Instance?.Debug($"Backend: Loaded session_id={SessionId} from disk");
            }
        }
    }

    // --- Background task tracking -----------------------------------------

    private static void TrackBackground(Task task)
    {
        lock (_backgroundTasks)
        {
            _backgroundTasks.Add(task);
        }
        task.ContinueWith(t =>
        {
            lock (_backgroundTasks)
            {
                _backgroundTasks.Remove(t);
            }
        }, TaskScheduler.Default);
    }

    // --- LRU texture cache -------------------------------------------------

    /// <summary>
    /// Bounded LRU cache for sprite textures. Keyed by object id / debris name,
    /// bounded to a fixed capacity to stop the Backend autoload from retaining
    /// GPU memory indefinitely across level resets. Single-threaded — callers
    /// must only touch it from the main thread (ApplySpriteReady etc. are
    /// CallDeferred'd from HTTP continuations).
    /// </summary>
    private sealed class LruTextureCache
    {
        private readonly int _capacity;
        private readonly LinkedList<string> _order = new();
        private readonly Dictionary<string, (LinkedListNode<string> Node, Texture2D Texture)> _entries = new();

        public LruTextureCache(int capacity)
        {
            _capacity = capacity;
        }

        public Texture2D? Get(string key)
        {
            if (_entries.TryGetValue(key, out var hit))
            {
                // Move to front (most-recently used).
                _order.Remove(hit.Node);
                _order.AddFirst(hit.Node);
                return hit.Texture;
            }
            return null;
        }

        public void Set(string key, Texture2D texture)
        {
            if (_entries.TryGetValue(key, out var existing))
            {
                _order.Remove(existing.Node);
                _order.AddFirst(existing.Node);
                _entries[key] = (existing.Node, texture);
                return;
            }

            var node = _order.AddFirst(key);
            _entries[key] = (node, texture);

            while (_entries.Count > _capacity && _order.Last is not null)
            {
                var evictKey = _order.Last.Value;
                _order.RemoveLast();
                _entries.Remove(evictKey);
            }
        }
    }

}
