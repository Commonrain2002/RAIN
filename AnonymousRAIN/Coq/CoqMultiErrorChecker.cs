using ProofAgent.Tools;
using Serilog;

namespace ProofAgent.Coq;

/// <summary>Runs the proof check plus optional probing to accumulate additional Coq errors for <c>run_check</c>.</summary>
public class CoqMultiErrorChecker : ICoqMultiErrorChecker
{
    #region Fields

    private const int _DefaultErrorSourceLinesBefore = 6;

    private const int _DefaultErrorSourceLinesAfter = 3;

    private const string _NoSuchGoal = "No such goal";

    private const string _AttemptToSaveIncompleteProof = "Attempt to save an incomplete proof";

    private const string _AttemptToSaveProof = "Attempt to save a proof";

    private const string _Ellipsis = "...";

    private readonly ILogger _Logger;

    private readonly ICoqChecker _Checker;

    private readonly ICoqEnvironmentCapturer _EnvironmentCapturer;

    private readonly RelativePath _TargetCoqFileRelativePath;

    private readonly ProjectFileSystem _FileSystem;

    private readonly CoqProofBulletIterationPlanner _Planner;

    private readonly int _CheckTimeoutSeconds;

    private readonly string _CheckCommand;

    private readonly int _ExtraErrorCount;

    #endregion Fields

    public CoqMultiErrorChecker(
        ILogger logger,
        ICoqChecker checker,
        ICoqEnvironmentCapturer environmentCapturer,
        RelativePath targetCoqFileRelativePath,
        ProjectFileSystem fileSystem,
        CoqProofBulletIterationPlanner planner,
        int checkTimeoutSeconds,
        string checkCommand,
        int extraErrorCount)
    {
        _Logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _Checker = checker ?? throw new ArgumentNullException(nameof(checker));
        _EnvironmentCapturer = environmentCapturer ?? throw new ArgumentNullException(nameof(environmentCapturer));
        _TargetCoqFileRelativePath = targetCoqFileRelativePath
            ?? throw new ArgumentNullException(nameof(targetCoqFileRelativePath));
        _FileSystem = fileSystem ?? throw new ArgumentNullException(nameof(fileSystem));
        _Planner = planner ?? throw new ArgumentNullException(nameof(planner));
        if (checkTimeoutSeconds <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(checkTimeoutSeconds));
        }

        if (extraErrorCount < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(extraErrorCount));
        }

        if (string.IsNullOrWhiteSpace(checkCommand))
        {
            throw new ArgumentException("checkCommand must not be empty.", nameof(checkCommand));
        }

        _CheckTimeoutSeconds = checkTimeoutSeconds;
        _CheckCommand = checkCommand.Trim();
        _ExtraErrorCount = extraErrorCount;
    }

    public async Task<IReadOnlyList<CoqRunCheckFailure>> RunMultiErrorCheckAsync(CancellationToken cancellationToken)
    {
        var frozenLinesByRelativePath = new Dictionary<RelativePath, string[]>();
        var dirtyRelativePaths = new HashSet<RelativePath>();
        try
        {
            return await _GetFailuresAsync(frozenLinesByRelativePath, dirtyRelativePaths, cancellationToken)
                .ConfigureAwait(false);
        }
        finally
        {
            _RestoreDirtyFiles(dirtyRelativePaths, frozenLinesByRelativePath);
        }
    }

    #region Private Methods

    private async Task<IReadOnlyList<CoqRunCheckFailure>> _GetFailuresAsync(
        Dictionary<RelativePath, string[]> frozenLinesByRelativePath, HashSet<RelativePath> dirtyRelativePaths,
        CancellationToken cancellationToken)
    {
        var workingLinesByRelativePath = new Dictionary<RelativePath, string[]>();
        var failures = new List<CoqRunCheckFailure>();
        for (var i = 0; i <= _ExtraErrorCount; i++)
        {
            var check = await _Checker.CheckAsync(_TargetCoqFileRelativePath, _CheckTimeoutSeconds, _CheckCommand,
                    cancellationToken).ConfigureAwait(false);

            var needCheckMore = await _AppendFailureFromCheckAsync(failures, check, frozenLinesByRelativePath, i, cancellationToken);
            if (!needCheckMore)
            {
                break;
            }

            var commentWritten = await _WriteCommentAsync(
                    check.Error!,
                    i,
                    frozenLinesByRelativePath,
                    workingLinesByRelativePath,
                    dirtyRelativePaths,
                    cancellationToken)
                .ConfigureAwait(false);
            if (!commentWritten)
            {
                return failures;
            }
        }

        return failures;
    }

    private async Task<bool> _AppendFailureFromCheckAsync(
        List<CoqRunCheckFailure> failures,
        CoqCheck check,
        Dictionary<RelativePath, string[]> frozenLinesByRelativePath,
        int loopIndex,
        CancellationToken cancellationToken)
    {
        if (check.Success)
        {
            return false;
        }

        if ((check.TimedOut && loopIndex == 0) || check.Error == null)
        {
            failures.Add(
                new CoqRunCheckFailure
                {
                    Check = check,
                    EnvironmentText = "",
                    SourceSnippet = ""
                });
            
            return false;
        }

        if (_CheckIsMisleadingError(check.Error, loopIndex))
        {
            return false;
        }

        var environment = await _EnvironmentCapturer
            .GetEnvironmentTextAsync(check.Error, cancellationToken)
            .ConfigureAwait(false);
        var snippet = _SnippetForError(check.Error, frozenLinesByRelativePath);
        failures.Add(
            new CoqRunCheckFailure
            {
                Check = check,
                EnvironmentText = environment,
                SourceSnippet = snippet
            });

        return loopIndex < _ExtraErrorCount;
    }

    private bool _CheckIsMisleadingError(
        CoqError error,
        int iteration)
    {
        if (iteration == 0)
        {
            return false;
        }

        if (_CheckErrorIsNoSuchGoal(error))
        {
            _Logger.Information(
                "coq_multi_error: error is '{Prefix}' before iteration {Iteration}; stopping comment loop.",
                _NoSuchGoal,
                iteration);
            return true;
        }

        if (_CheckErrorIsIncompleteProof(error))
        {
            _Logger.Information(
                "coq_multi_error: error indicates incomplete proof or attempt to save a proof before iteration {Iteration}; stopping comment loop.",
                iteration);
            return true;
        }

        return false;
    }

    private static bool _CheckErrorIsNoSuchGoal(CoqError error)
    {
        return (error.Message ?? "").Trim().IndexOf(_NoSuchGoal, StringComparison.Ordinal) >= 0;
    }

    private static bool _CheckErrorIsIncompleteProof(CoqError error)
    {
        var message = error.Message ?? "";
        return message.IndexOf(_AttemptToSaveIncompleteProof, StringComparison.Ordinal) >= 0
            || message.IndexOf(_AttemptToSaveProof, StringComparison.Ordinal) >= 0;
    }

    private string _SnippetForError(
        CoqError? error,
        Dictionary<RelativePath, string[]> frozenLinesByRelativePath)
    {
        if (error == null || error.Line <= 0)
        {
            return "";
        }

        var relativePath = _ResolveErrorRelativePathOrNull(error);
        if (relativePath == null)
        {
            return "";
        }

        var frozenLines = _GetFrozenLines(relativePath, frozenLinesByRelativePath);
        if (frozenLines == null || frozenLines.Length == 0)
        {
            return "";
        }

        return _FormatSnippet(frozenLines, error);
    }

    private async Task<bool> _WriteCommentAsync(
        CoqError error,
        int iteration,
        Dictionary<RelativePath, string[]> frozenLinesByRelativePath,
        Dictionary<RelativePath, string[]> workingLinesByRelativePath,
        HashSet<RelativePath> dirtyRelativePaths,
        CancellationToken cancellationToken)
    {
        var relativePath = _ResolveErrorRelativePathOrNull(error);
        if (relativePath == null)
        {
            _Logger.Information("coq_multi_error: could not normalize error path; stopping comment loop.");
            return false;
        }

        var workingLines = _GetWorkingLines(relativePath, frozenLinesByRelativePath, workingLinesByRelativePath);
        if (workingLines == null)
        {
            _Logger.Information(
                "coq_multi_error: target file for error not found ({RelativePath}); stopping comment loop.",
                relativePath);
            return false;
        }

        var plan = await _Planner
            .PlanEditAsync(relativePath, (string[])workingLines.Clone(), error, cancellationToken)
            .ConfigureAwait(false);
        if (!plan.Succeeded || plan.CommentEditLines.Length == 0)
        {
            _Logger.Information(
                "coq_multi_error: planner did not produce a comment for iteration {Iteration}: {Reason}",
                iteration,
                string.IsNullOrEmpty(plan.FailureReason) ? "(none)" : plan.FailureReason);
            return false;
        }

        workingLinesByRelativePath[relativePath] = plan.CommentEditLines;
        _FileSystem.WriteAllLines(relativePath, plan.CommentEditLines);
        dirtyRelativePaths.Add(relativePath);
        return true;
    }

    private string _FormatSnippet(IReadOnlyList<string> lines, CoqError error)
    {
        var window = _FileSystem.LinesAround(
            lines,
            error.Line,
            _DefaultErrorSourceLinesBefore,
            _DefaultErrorSourceLinesAfter);
        return _RenderSnippet(window, error);
    }

    private static string _RenderSnippet(LineWindow window, CoqError error)
    {
        var output = new List<string>();
        if (window.HasLeadingEllipsis)
        {
            output.Add(_Ellipsis);
        }

        for (var line = window.StartLine; line <= window.EndLine; line++)
        {
            var content = window.Lines[line - window.StartLine];
            output.Add($"{line}: {content}");
            if (line == error.Line)
            {
                output.Add(_FormatCaretLine(line, content, error.Column));
            }
        }

        if (window.HasTrailingEllipsis)
        {
            output.Add(_Ellipsis);
        }

        return string.Join(Environment.NewLine, output);
    }

    private static string _FormatCaretLine(int lineNumber, string lineContent, int columnZeroBased)
    {
        var prefixLength = lineNumber.ToString().Length + 2;
        var column = Math.Clamp(columnZeroBased, 0, lineContent.Length);
        return new string(' ', prefixLength + column) + "^";
    }

    private string[]? _GetFrozenLines(
        RelativePath relativePath,
        Dictionary<RelativePath, string[]> frozenLinesByRelativePath)
    {
        if (frozenLinesByRelativePath.TryGetValue(relativePath, out var existing))
        {
            return existing;
        }

        if (!_FileSystem.Exists(relativePath))
        {
            return null;
        }

        var lines = _FileSystem.ReadAllLines(relativePath);
        frozenLinesByRelativePath[relativePath] = lines;
        return lines;
    }

    private string[]? _GetWorkingLines(
        RelativePath relativePath,
        Dictionary<RelativePath, string[]> frozenLinesByRelativePath,
        Dictionary<RelativePath, string[]> workingLinesByRelativePath)
    {
        if (workingLinesByRelativePath.TryGetValue(relativePath, out var existing))
        {
            return existing;
        }

        var frozenLines = _GetFrozenLines(relativePath, frozenLinesByRelativePath);
        if (frozenLines == null)
        {
            return null;
        }

        var clone = frozenLines.ToArray();
        workingLinesByRelativePath[relativePath] = clone;
        return clone;
    }

    private void _RestoreDirtyFiles(
        HashSet<RelativePath> dirtyRelativePaths,
        Dictionary<RelativePath, string[]> frozenLinesByRelativePath)
    {
        foreach (var relativePath in dirtyRelativePaths)
        {
            if (frozenLinesByRelativePath.TryGetValue(relativePath, out var frozenLines))
            {
                _FileSystem.WriteAllLines(relativePath, frozenLines);
            }
        }
    }

    private RelativePath? _ResolveErrorRelativePathOrNull(CoqError error)
    {
        if (error.RelativeFilePath == null || error.RelativeFilePath.EscapesBase)
        {
            return null;
        }

        return error.RelativeFilePath;
    }

    #endregion Private Methods
}
