using System.Text;
using ProofAgent.Tools;
using Serilog;

namespace ProofAgent.Coq;

public record CoqEnvironment(string RawText)
{
    public override string ToString() => RawText;
}

public class CoqEnvironmentCapturer : ICoqEnvironmentCapturer
{
    #region Fields

    private readonly ProjectFileSystem _FileSystem;

    private readonly ILogger _Logger;

    private readonly ICoqChecker _Checker;

    private readonly ICoqSentenceAnalyzer _SentenceAnalyzer;

    private readonly int _CheckTimeoutSeconds;

    private readonly string _CheckCommand;

    private const string _RedirectAuxFileNamePrefix = "_ProofAgent_Aux_Environment_";

    private const string _RedirectShowOutputFileSuffix = ".out";

    #endregion Fields

    public CoqEnvironmentCapturer(
        ProjectFileSystem fileSystem,
        ICoqChecker checker,
        ICoqSentenceAnalyzer sentenceAnalyzer,
        int checkTimeoutSeconds,
        string checkCommand,
        ILogger logger)
    {
        _FileSystem = fileSystem ?? throw new ArgumentNullException(nameof(fileSystem));
        _Checker = checker ?? throw new ArgumentNullException(nameof(checker));
        _SentenceAnalyzer = sentenceAnalyzer ?? throw new ArgumentNullException(nameof(sentenceAnalyzer));
        if (checkTimeoutSeconds <= 0)
        {
            throw new ArgumentOutOfRangeException(
                nameof(checkTimeoutSeconds),
                "checkTimeoutSeconds must be a positive integer.");
        }

        if (string.IsNullOrWhiteSpace(checkCommand))
        {
            throw new ArgumentException("checkCommand must not be empty.", nameof(checkCommand));
        }

        _CheckTimeoutSeconds = checkTimeoutSeconds;
        _CheckCommand = checkCommand.Trim();
        _Logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    /// <summary>Use  Redirect Show to get Hypotheses/Goals before the error; on failure a short explanatory line.</summary>
    public async Task<string> GetEnvironmentTextAsync(
        CoqError error,
        CancellationToken cancellationToken)
    {
        try
        {
            var env = await _GetEnvironmentTextAsync(error, cancellationToken)
                .ConfigureAwait(false);
            return env.RawText;
        }
        catch (Exception ex)
        {
            return $"(CoqEnvironmentCapturer failed to get environment: {ex.Message})";
        }
    }

    #region Private Methods

    private async Task<CoqEnvironment> _GetEnvironmentTextAsync(
        CoqError error,
        CancellationToken cancellationToken,
        Action<string>? environmentCaptureDebugLog = null)
    {
        if (error.Line <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(error), "error.Line must be a positive integer.");
        }

        var relativePath = _ResolveErrorRelativePathOrNull(error);
        if (relativePath == null)
        {
            _Logger.Warning(
                "coq_env_capture: no valid file path on error; skipping Redirect Show capture.");
            return new CoqEnvironment("");
        }

        var relativeFilePathForLog = relativePath.PosixPath;
        var allLines = _FileSystem.ReadAllLines(relativePath);
        var joinedSource = string.Join(Environment.NewLine, allLines);
        var sentenceBeforeError = await _SentenceAnalyzer
            .GetSentenceBeforeAsync(relativePath, error.Line, error.Column, cancellationToken)
            .ConfigureAwait(false);

        if (sentenceBeforeError == null)
        {
            _Logger.Warning(
                "coq_env_capture: could not resolve sentence before error position in {File}; skipping Redirect Show capture.",
                relativeFilePathForLog);
            return new CoqEnvironment("");
        }

        _LogIfSentenceExclusiveEndPastFileLines(
            allLines,
            sentenceBeforeError.EndLineOneBased,
            sentenceBeforeError.EndColumnZeroBased,
            relativeFilePathForLog);
        var insertCutExclusive = _GetPrefixTextBeforeErrorPosition(
                allLines,
                sentenceBeforeError.EndLineOneBased,
                sentenceBeforeError.EndColumnZeroBased).Length;

        var replayPrefixPreview = joinedSource.Length == 0 ? "" : joinedSource[..insertCutExclusive];
        var redirectAuxiliaryStem = _RedirectAuxFileNamePrefix + Guid.NewGuid().ToString("N", null);
        var redirectShowOutputPath = _FileSystem.CreateTempFile(
            redirectAuxiliaryStem + _RedirectShowOutputFileSuffix);
        environmentCaptureDebugLog?.Invoke(_BuildEnvironmentCaptureDebugMessage(
                relativeFilePathForLog,
                error,
                allLines,
                joinedSource,
                insertCutExclusive,
                sentenceBeforeError,
                replayPrefixPreview,
                redirectShowOutputPath));

        var envText = await _GetEnvironmentAsync(
                relativePath,
                joinedSource,
                insertCutExclusive,
                redirectShowOutputPath,
                cancellationToken)
            .ConfigureAwait(false);
        return new CoqEnvironment(envText);
    }

    /// <summary>
    /// Build source prefix before error: full preceding lines; on error line keep only chars before Coq 0-based column (keeps prior tactics on same line).
    /// </summary>
    private static string _GetPrefixTextBeforeErrorPosition(
        IReadOnlyList<string> allLines,
        int lineOneBased,
        int errorStartColumnZeroBased)
    {
        if (allLines.Count == 0)
        {
            return "";
        }

        if (lineOneBased < 1)
        {
            lineOneBased = 1;
        }

        if (errorStartColumnZeroBased < 0)
        {
            errorStartColumnZeroBased = 0;
        }

        if (lineOneBased > allLines.Count)
        {
            return string.Join(Environment.NewLine, allLines);
        }

        var stringBuilder = new StringBuilder();
        for (var i = 0; i < allLines.Count; i++)
        {
            var currentLineOneBased = i + 1;
            if (currentLineOneBased < lineOneBased)
            {
                stringBuilder.Append(allLines[i]);
                stringBuilder.Append(Environment.NewLine);
            }
            else if (currentLineOneBased == lineOneBased)
            {
                var lineText = allLines[i];
                var take = Math.Clamp(errorStartColumnZeroBased, 0, lineText.Length);
                stringBuilder.Append(lineText.AsSpan(0, take));
                break;
            }
            else
            {
                break;
            }
        }

        return stringBuilder.ToString();
    }
    
    private async Task<string> _GetEnvironmentAsync(
        RelativePath relativePath,
        string joinedSource,
        int cutExclusive,
        AbsolutePath redirectShowOutputPath,
        CancellationToken cancellationToken)
    {
        var cut = Math.Clamp(cutExclusive, 0, joinedSource.Length);
        var before = joinedSource[..cut];
        var after = joinedSource[cut..];
        var redirectProbeSentence = _BuildEnvironmentProbe(redirectShowOutputPath);
        var modified =
            before +
            Environment.NewLine +
            redirectProbeSentence +
            Environment.NewLine +
            after;

        try
        {
            await _FileSystem
                .WriteAllTextAsync(relativePath, modified, cancellationToken)
                .ConfigureAwait(false);
            var checkResult = await _Checker
                .CheckAsync(relativePath, _CheckTimeoutSeconds, _CheckCommand, cancellationToken)
                .ConfigureAwait(false);
            if (checkResult.TimedOut)
            {
                return string.Empty;
            }

            return _ReadEnvironmentOutputFile(redirectShowOutputPath);
        }
        finally
        {
            try
            {
                await _FileSystem
                    .WriteAllTextAsync(relativePath, joinedSource, cancellationToken)
                    .ConfigureAwait(false);
            }
            finally
            {
                _DeleteRedirectShowOutputFile(redirectShowOutputPath);
            }
        }
    }

    /// <summary>Map 0-based index in <paramref name="prefixText"/> to 1-based line and 0-based column (same as Coq error columns).</summary>
    private static void _PrefixIndexToLineColumnOneBased(string prefixText, int index, out int lineOneBased, out int columnZeroBased)
    {
        lineOneBased = 1;
        columnZeroBased = 0;
        if (string.IsNullOrEmpty(prefixText) || index <= 0)
        {
            return;
        }

        index = Math.Clamp(index, 0, prefixText.Length);
        var lineStartIdx = 0;
        for (var i = 0; i < index; i++)
        {
            if (i >= prefixText.Length)
            {
                break;
            }

            if (prefixText[i] == '\r' && i + 1 < prefixText.Length && prefixText[i + 1] == '\n')
            {
                lineOneBased++;
                lineStartIdx = i + 2;
                i++;
            }
            else if (prefixText[i] == '\n' || prefixText[i] == '\r')
            {
                lineOneBased++;
                lineStartIdx = i + 1;
            }
        }

        columnZeroBased = index - lineStartIdx;
    }

    /// <summary>For debugging: parse-script sentence choice, line/column insert point, and replay tail before probe.</summary>
    private static string _BuildEnvironmentCaptureDebugMessage(
        string relativeFilePathForLog,
        CoqError error,
        IReadOnlyList<string> allLines,
        string joinedSource,
        int insertCutExclusiveChar,
        CoqSentence chosenSentence,
        string replayPrefix,
        AbsolutePath redirectShowOutputPath)
    {
        var prefixText = _GetPrefixTextBeforeErrorPosition(allLines, error.Line, error.Column);
        _PrefixIndexToLineColumnOneBased(joinedSource, insertCutExclusiveChar, out var insertLine, out var insertCol);
        _PrefixIndexToLineColumnOneBased(prefixText, prefixText.Length, out var errLine, out var errCol);
        var redirectBasePathForCoq = _GetRedirectBasePathForCoq(redirectShowOutputPath);

        var sb = new StringBuilder();
        sb.AppendLine($"[coq_env_capture] file={relativeFilePathForLog}");
        sb.AppendLine(
            $"[coq_env_capture] coq_error position: line {error.Line} column {error.Column} (1-based line, 0-based column, from checker)");
        sb.AppendLine(
            $"[coq_env_capture] prefixToError: length={prefixText.Length} chars (source from BOF up to before error column)");
        sb.AppendLine(
            $"[coq_env_capture] chosen sentence index={chosenSentence.Index} end_line={chosenSentence.EndLineOneBased} end_column={chosenSentence.EndColumnZeroBased} insertCutExclusiveChar={insertCutExclusiveChar}");
        sb.AppendLine(
            $"[coq_env_capture] Redirect Show inserts at line {insertLine} column {insertCol} (0-based column in joined-source model)");
        sb.AppendLine(
            $"[coq_env_capture] prefix ends at line {errLine} column {errCol} (first excluded char = error column)");
        sb.AppendLine(
            "[coq_env_capture] insertion offset: parse-sentence-script sentence exclusive end (line/column), then Redirect Show probe and CoqChecker.CheckAsync, then file restore.");
        sb.AppendLine(
            $"[coq_env_capture] Redirect Show path={redirectBasePathForCoq} output file={redirectShowOutputPath.FullPath}");

        const int tailMax = 240;
        var tail = replayPrefix.Length <= tailMax
            ? replayPrefix
            : replayPrefix[^tailMax..];
        sb.AppendLine($"[coq_env_capture] replay prefix tail (last up to {tailMax} chars, then probe):");
        sb.AppendLine(string.IsNullOrEmpty(tail) ? "    (empty)" : "    " + tail.Replace("\n", "\\n", StringComparison.Ordinal));

        return sb.ToString().TrimEnd();
    }

    private void _LogIfSentenceExclusiveEndPastFileLines(
        IReadOnlyList<string> allLines,
        int endLineOneBased,
        int endColumnZeroBased,
        string relativeFilePathForLog)
    {
        if (endLineOneBased > allLines.Count)
        {
            _Logger.Warning(
                "coq_env_capture: sentence exclusive end line {EndLine} column {EndColumn} is past file line count {LineCount} in {File}; insert will clamp to EOF.",
                endLineOneBased,
                endColumnZeroBased,
                allLines.Count,
                relativeFilePathForLog);
        }
    }

    private static string _GetRedirectBasePathForCoq(AbsolutePath redirectShowOutputPath)
    {
        var outputFullPath = redirectShowOutputPath.FullPath;
        if (!outputFullPath.EndsWith(_RedirectShowOutputFileSuffix, StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                "Redirect Show output path must end with the configured output suffix.");
        }

        return outputFullPath[..^_RedirectShowOutputFileSuffix.Length];
    }

    private static string _BuildEnvironmentProbe(AbsolutePath redirectShowOutputPath)
    {
        var redirectBasePathForCoq = _GetRedirectBasePathForCoq(redirectShowOutputPath);
        var coqPathLiteral = _EscapePathForCoqStringLiteral(redirectBasePathForCoq);
        return $"Redirect \"{coqPathLiteral}\" Show.";
    }

    private static string _EscapePathForCoqStringLiteral(string path)
    {
        var normalized = path.Replace('\\', '/');
        return normalized
            .Replace("\\", "\\\\", StringComparison.Ordinal)
            .Replace("\"", "\\\"", StringComparison.Ordinal);
    }

    private string _ReadEnvironmentOutputFile(AbsolutePath redirectShowOutputPath)
    {
        if (!_FileSystem.Exists(redirectShowOutputPath))
        {
            _Logger.Warning(
                "coq_env_capture: Redirect Show output file missing at {OutputPath}.",
                redirectShowOutputPath.FullPath);
            return "";
        }

        try
        {
            return _FileSystem.ReadAllText(redirectShowOutputPath).Trim();
        }
        catch (Exception ex)
        {
            _Logger.Warning(
                ex,
                "coq_env_capture: failed to read Redirect Show output at {OutputPath}.",
                redirectShowOutputPath.FullPath);
            return "";
        }
    }

    private void _DeleteRedirectShowOutputFile(AbsolutePath redirectShowOutputPath)
    {
        try
        {
            _FileSystem.DeleteOwnedTempFile(redirectShowOutputPath);
        }
        catch (Exception ex)
        {
            _Logger.Warning(
                ex,
                "coq_env_capture: failed to delete Redirect Show output file {OutputPath}.",
                redirectShowOutputPath.FullPath);
        }
    }

    private static RelativePath? _ResolveErrorRelativePathOrNull(CoqError error)
    {
        if (error.RelativeFilePath == null || error.RelativeFilePath.EscapesBase)
        {
            return null;
        }

        return error.RelativeFilePath;
    }

    #endregion Private Methods
}

