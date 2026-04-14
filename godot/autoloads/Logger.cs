using Godot;
using FileAccess = Godot.FileAccess;

namespace Makeshift.Autoloads;

/// <summary>
/// Logging autoload. Registered in <c>project.godot</c> under the name
/// <c>Log</c>. Call via <see cref="Instance"/> (e.g.
/// <c>Logger.Instance?.Info("msg")</c>).
/// </summary>
public sealed partial class Logger : Node
{
    public enum Level
    {
        Debug = 0,
        Info = 1,
        Warn = 2,
        Error = 3,
    }

    public static Logger Instance { get; private set; } = null!;

    public Level CurrentLevel { get; set; } = Level.Debug;
    public bool FileLoggingEnabled { get; set; } = true;

    public bool IsEnabled(Level level) => level >= CurrentLevel;
    public bool IsDebugEnabled => CurrentLevel <= Level.Debug;
    public bool IsInfoEnabled => CurrentLevel <= Level.Info;
    public bool IsWarnEnabled => CurrentLevel <= Level.Warn;

    private const string LogDir = "user://logs/";
    private const float FlushInterval = 1.0f;

    private FileAccess? _logFile;
    private float _flushTimer;

    public override void _EnterTree()
    {
        Instance = this;
    }

    public override void _Ready()
    {
        if (!OS.IsDebugBuild())
        {
            CurrentLevel = Level.Warn;
        }
        OpenLogFile();
    }

    public override void _Process(double delta)
    {
        if (_logFile is not null)
        {
            _flushTimer += (float)delta;
            if (_flushTimer >= FlushInterval)
            {
                _flushTimer = 0.0f;
                _logFile.Flush();
            }
        }
    }

    public override void _ExitTree()
    {
        if (_logFile is not null)
        {
            _logFile.Flush();
            _logFile.Close();
            _logFile = null;
        }
    }

    public void Debug(string msg)
    {
        bool needsConsole = CurrentLevel <= Level.Debug;
        if (_logFile is null && !needsConsole)
        {
            return;
        }
        var ts = Timestamp();
        WriteToFile("DEBUG", msg, ts);
        if (needsConsole)
        {
            GD.PrintRich($"[color=gray]{ts} [DEBUG] {msg}[/color]");
        }
    }

    public void Info(string msg)
    {
        bool needsConsole = CurrentLevel <= Level.Info;
        if (_logFile is null && !needsConsole)
        {
            return;
        }
        var ts = Timestamp();
        WriteToFile("INFO", msg, ts);
        if (needsConsole)
        {
            GD.PrintRich($"{ts} [color=cyan][INFO][/color] {msg}");
        }
    }

    public void Warn(string msg)
    {
        bool needsConsole = CurrentLevel <= Level.Warn;
        if (_logFile is null && !needsConsole)
        {
            return;
        }
        var ts = Timestamp();
        WriteToFile("WARN", msg, ts);
        if (needsConsole)
        {
            GD.PrintRich($"{ts} [color=yellow][WARN][/color] {msg}");
            GD.PushWarning(msg);
        }
    }

    public void Error(string msg)
    {
        var ts = Timestamp();
        WriteToFile("ERROR", msg, ts);
        if (CurrentLevel <= Level.Error)
        {
            GD.PrintRich($"{ts} [color=red][ERROR][/color] {msg}");
            GD.PushError(msg);
        }
    }

    private static string Timestamp()
    {
        return Time.GetDatetimeStringFromSystem(true);
    }

    private void OpenLogFile()
    {
        if (!FileLoggingEnabled)
        {
            return;
        }
        DirAccess.MakeDirRecursiveAbsolute(LogDir);
        var datetime = Time.GetDatetimeStringFromSystem(true)
            .Replace(":", "")
            .Replace("-", "")
            .Replace("T", "_");
        var path = LogDir + datetime + ".log";
        _logFile = FileAccess.Open(path, FileAccess.ModeFlags.Write);
        if (_logFile is not null)
        {
            _logFile.StoreLine($"{Timestamp()} [INFO] Log file opened");
        }
    }

    private void WriteToFile(string level, string msg, string ts)
    {
        _logFile?.StoreLine($"{ts} [{level}] {msg}");
    }
}
