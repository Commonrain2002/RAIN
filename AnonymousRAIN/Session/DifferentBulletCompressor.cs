using System.Text;
using ProofAgent.Coq;
using ProofAgent.Llm;
using ProofAgent.Tools;
using Serilog;

namespace ProofAgent.Session;

/// <summary>
/// Not wired in the main application: enabling this compressor would increase LLM uncertainty.
/// </summary>
public class DifferentBulletCompressor : IContextCompressor
{
    #region Fields

    private const string _RunCheckSucceededMarker = "Result: proof check succeeded";

    private const int _StackBottomPrefixCellCount = 2;

    private const string _ReplaceFrameworkAdjustmentToolResultPrefix =
        "OK. Prior bullet edits were omitted. Focus on the current issues:";

    private readonly ProjectFileSystem _FileSystem;

    private readonly RelativePath _TargetFileRelativePath;

    private readonly CoqBulletAnalyzer _BulletAnalyzer;

    private readonly ICoqSentenceAnalyzer _SentenceAnalyzer;

    private readonly ILogger _Logger;

    private readonly RunCheckToolResultCoqErrorAnchorParser _RunCheckErrorAnchorParser;

    private readonly string _ReplaceToolName;

    private readonly string _RunCheckToolName;

    private CoqBulletStackBottomPrefixSnapshot? _SavedBottomPrefix;

    #endregion Fields

    public DifferentBulletCompressor(
        ProjectFileSystem fileSystem,
        RelativePath targetFileRelativePath,
        CoqBulletAnalyzer bulletAnalyzer,
        ICoqSentenceAnalyzer sentenceAnalyzer,
        ILogger logger,
        RunCheckToolResultCoqErrorAnchorParser runCheckErrorAnchorParser,
        string replaceToolName,
        string runCheckToolName)
    {
        _FileSystem = fileSystem ?? throw new ArgumentNullException(nameof(fileSystem));
        _TargetFileRelativePath = targetFileRelativePath ?? throw new ArgumentNullException(nameof(targetFileRelativePath));
        _BulletAnalyzer = bulletAnalyzer ?? throw new ArgumentNullException(nameof(bulletAnalyzer));
        _SentenceAnalyzer = sentenceAnalyzer ?? throw new ArgumentNullException(nameof(sentenceAnalyzer));
        _Logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _RunCheckErrorAnchorParser = runCheckErrorAnchorParser
            ?? throw new ArgumentNullException(nameof(runCheckErrorAnchorParser));
        _ReplaceToolName = _RequireToolName(replaceToolName, nameof(replaceToolName));
        _RunCheckToolName = _RequireToolName(runCheckToolName, nameof(runCheckToolName));
    }

    public IReadOnlyList<LlmMessage> Compress(IReadOnlyList<LlmMessage> messages)
    {
        if (messages.Count == 0 || !_AnyReplaceToolCall(messages))
        {
            return messages;
        }

        if (!_TryGetLastRunCheckToolMessage(messages, out _, out var lastRunCheckContent))
        {
            return messages;
        }

        if (_RunCheckContentIndicatesSuccess(lastRunCheckContent))
        {
            return messages;
        }

        if (!_RunCheckErrorAnchorParser.TryParse(lastRunCheckContent, out var errorAnchor))
        {
            _Logger.Information(
                "different_bullet_compressor: could not parse Coq error anchor from last run_check tool sections; skipping compression.");
            return messages;
        }

        var currentBottomPrefix = _TryBuildBottomPrefixSnapshotBeforeError(errorAnchor);
        if (currentBottomPrefix is null)
        {
            return messages;
        }

        _LogSavedBottomPrefixState(currentBottomPrefix);

        if (_SavedBottomPrefix is null)
        {
            _SavedBottomPrefix = currentBottomPrefix;
            _Logger.Information(
                "different_bullet_compressor: initialized stack-bottom prefix snapshot (depth={Depth}, identities={Identities}).",
                _StackBottomPrefixCellCount,
                _SavedBottomPrefix.FormatCellIdentitiesForLog());
            return messages;
        }

        if (_SavedBottomPrefix.IdentitiesEqual(currentBottomPrefix))
        {
            return messages;
        }

        _SavedBottomPrefix = currentBottomPrefix;

        _Logger.Information(
            "different_bullet_compressor: stack-bottom prefix identities changed to {Identities}; compressing history view.",
            _SavedBottomPrefix.FormatCellIdentitiesForLog());

        return _TruncateAndRewriteFirstReplaceToolResult(
            messages,
            lastRunCheckContent);
    }

    #region Private Methods

    private static string _RequireToolName(string toolName, string parameterName)
    {
        if (string.IsNullOrWhiteSpace(toolName))
        {
            throw new ArgumentException("Tool name must be non-empty.", parameterName);
        }

        return toolName;
    }

    private void _LogSavedBottomPrefixState(CoqBulletStackBottomPrefixSnapshot currentBottomPrefix)
    {
        var savedDescription = _SavedBottomPrefix is null
            ? "(null)"
            : _SavedBottomPrefix.FormatCellIdentitiesForLog();
        _Logger.Information(
            "different_bullet_compressor: _SavedBottomPrefix={SavedIdentities}; current bottom prefix={CurrentIdentities}.",
            savedDescription,
            currentBottomPrefix.FormatCellIdentitiesForLog());
    }

    private CoqBulletStackBottomPrefixSnapshot? _TryBuildBottomPrefixSnapshotBeforeError(
        RunCheckToolResultCoqErrorAnchor errorAnchor)
    {
        if (!_FileSystem.Exists(_TargetFileRelativePath))
        {
            _Logger.Information(
                "different_bullet_compressor: target file missing at {Path}.",
                _TargetFileRelativePath.PosixPath);
            return null;
        }

        var sentenceBeforeErrorHeld = _SentenceAnalyzer
            .GetSentenceBeforeAsync(
                _TargetFileRelativePath,
                errorAnchor.LineOneBased,
                errorAnchor.ColumnZeroBased,
                CancellationToken.None)
            .ConfigureAwait(false)
            .GetAwaiter()
            .GetResult();
        if (sentenceBeforeErrorHeld == null)
        {
            _Logger.Information(
                "different_bullet_compressor: no sentence ends before error position at line {Line} column {Column}.",
                errorAnchor.LineOneBased,
                errorAnchor.ColumnZeroBased);
            return null;
        }

        CoqBulletStack? stack;
        string stackFailureReason = "";
        try
        {
            var stackTry = _BulletAnalyzer
                .GetBulletStackAsync(
                    _TargetFileRelativePath,
                    sentenceBeforeErrorHeld.StartLineOneBased,
                    sentenceBeforeErrorHeld.StartColumnZeroBased,
                    CancellationToken.None)
                .ConfigureAwait(false)
                .GetAwaiter()
                .GetResult();
            stack = stackTry.Succeeded ? stackTry.BulletStack : null;
            stackFailureReason = stackTry.FailureReason;
        }
        catch (Exception ex)
        {
            _Logger.Warning(
                ex,
                "different_bullet_compressor: TryGetBulletStackAsync failed for {Path}.",
                _TargetFileRelativePath);
            return null;
        }
        if (stack == null || stack.Cells.Count == 0)
        {
            _Logger.Information(
                "different_bullet_compressor: TryGetBulletStack at sentence index {BeforeIndex} before error failed: {Reason}",
                sentenceBeforeErrorHeld.Index,
                string.IsNullOrEmpty(stackFailureReason) ? "(unknown)" : stackFailureReason);
            return null;
        }

        return CoqBulletStackBottomPrefixSnapshot.FromStackCells(
            stack.Cells,
            _StackBottomPrefixCellCount);
    }

    private IReadOnlyList<LlmMessage> _TruncateAndRewriteFirstReplaceToolResult(
        IReadOnlyList<LlmMessage> messages,
        string lastRunCheckContent)
    {
        var firstReplaceToolIndex = _TryFindFirstReplaceToolMessageIndex(messages);
        if (firstReplaceToolIndex < 0)
        {
            _Logger.Warning(
                "different_bullet_compressor: first replace tool result not found; skipping truncation.");
            return messages;
        }

        var truncated = new List<LlmMessage>(firstReplaceToolIndex + 1);
        for (var i = 0; i < firstReplaceToolIndex; i++)
        {
            truncated.Add(messages[i]);
        }

        var replaceToolMessage = messages[firstReplaceToolIndex];
        if (replaceToolMessage.Role != LlmParticipantRole.Tool ||
            string.IsNullOrEmpty(replaceToolMessage.ToolCallID))
        {
            _Logger.Warning(
                "different_bullet_compressor: expected replace tool message at index {Index}.",
                firstReplaceToolIndex);
            return messages;
        }

        var rewrittenContent = _ReplaceFrameworkAdjustmentToolResultPrefix
            + Environment.NewLine
            + Environment.NewLine
            + lastRunCheckContent;
        truncated.Add(LlmMessage.CreateTool(replaceToolMessage.ToolCallID, rewrittenContent));
        return truncated;
    }

    private static string _FormatMessagesForLog(IReadOnlyList<LlmMessage> messages)
    {
        var sb = new StringBuilder();
        for (var i = 0; i < messages.Count; i++)
        {
            var m = messages[i];
            sb.Append('[').Append(i).Append("] role=").Append(m.Role);
            if (!string.IsNullOrEmpty(m.ToolCallID))
            {
                sb.Append(" toolCallID=").Append(m.ToolCallID);
            }

            if (m.AssistantToolCalls is { Count: > 0 } calls)
            {
                sb.Append(" toolCalls=").Append(calls.Count);
            }

            var content = m.Content;
            sb.Append(" contentLength=").Append(content.Length);
            if (content.Length > 0)
            {
                sb.Append(" content=\n").Append(content);
            }

            sb.AppendLine();
        }

        return sb.ToString();
    }

    private int _TryFindFirstReplaceToolMessageIndex(IReadOnlyList<LlmMessage> messages)
    {
        var toolCallIDToName = _BuildToolCallIDToName(messages);
        for (var i = 0; i < messages.Count; i++)
        {
            var m = messages[i];
            if (m.Role != LlmParticipantRole.Tool || string.IsNullOrEmpty(m.ToolCallID))
            {
                continue;
            }

            if (_IsToolResultOfName(m.ToolCallID, toolCallIDToName, _ReplaceToolName))
            {
                return i;
            }
        }

        return -1;
    }

    private bool _TryGetLastRunCheckToolMessage(
        IReadOnlyList<LlmMessage> messages,
        out string toolCallID,
        out string content)
    {
        toolCallID = "";
        content = "";
        var last = messages[^1];
        if (last.Role != LlmParticipantRole.Tool || string.IsNullOrEmpty(last.ToolCallID))
        {
            return false;
        }

        var toolCallIDToName = _BuildToolCallIDToName(messages);
        if (!_IsToolResultOfName(last.ToolCallID, toolCallIDToName, _RunCheckToolName))
        {
            return false;
        }

        toolCallID = last.ToolCallID;
        content = last.Content;
        return true;
    }

    private static bool _RunCheckContentIndicatesSuccess(string runCheckContent)
    {
        return runCheckContent.Contains(_RunCheckSucceededMarker, StringComparison.Ordinal);
    }

    private static Dictionary<string, string> _BuildToolCallIDToName(IReadOnlyList<LlmMessage> messages)
    {
        var dict = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var m in messages)
        {
            if (m.Role != LlmParticipantRole.Assistant || m.AssistantToolCalls is not { Count: > 0 } calls)
            {
                continue;
            }

            foreach (var c in calls)
            {
                if (string.IsNullOrWhiteSpace(c.ToolCallID) || string.IsNullOrWhiteSpace(c.Name))
                {
                    continue;
                }

                dict[c.ToolCallID] = c.Name;
            }
        }

        return dict;
    }

    private static bool _IsToolResultOfName(
        string toolCallID,
        IReadOnlyDictionary<string, string> toolCallIDToName,
        string toolName)
    {
        return toolCallIDToName.TryGetValue(toolCallID, out var name) &&
               string.Equals(name, toolName, StringComparison.Ordinal);
    }

    private bool _AnyReplaceToolCall(IReadOnlyList<LlmMessage> messages)
    {
        foreach (var m in messages)
        {
            if (m.Role != LlmParticipantRole.Assistant || m.AssistantToolCalls is not { Count: > 0 } calls)
            {
                continue;
            }

            foreach (var c in calls)
            {
                if (string.IsNullOrWhiteSpace(c.Name))
                {
                    continue;
                }

                if (string.Equals(c.Name, _ReplaceToolName, StringComparison.Ordinal))
                {
                    return true;
                }
            }
        }

        return false;
    }

    #endregion Private Methods
}
