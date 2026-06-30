using System.Diagnostics;
using System.Text.RegularExpressions;
using ProofAgent.Tools;
using Serilog;

namespace ProofAgent.Coq;

public class CoqChecker : ICoqChecker
{
    #region Fields

    private static readonly Regex _CoqErrorRegex = new(
        "File \"(?<file>.+?)\", line (?<line>\\d+), characters (?<c1>\\d+)-(?<c2>\\d+):\\s*Error:\\s*(?<msg>[\\s\\S]*?)(?=(?:\\r?\\nFile \")|\\z)",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    /// <summary>
    /// GNU make recursive failure echoes after Coq errors, e.g.
    /// <c>make[1]: *** [Makefile:10: tgt.vo] Error 1</c>,
    /// <c>make: *** [Makefile:243: all] Error 2 (ignored)</c>,
    /// <c>make[2]: *** [flocq/Core/Ulp.vo] Deleting file 'flocq/Core/Ulp.glob'</c>.
    /// </summary>
    private static readonly Regex _MakeRecursiveErrorEchoLineRegex = new(
        @"^\s*make(?:\[\d+\])?\s*:\s*\*{2,}\s*\[[^\]\r\n]+\]\s*(?:Error\s*\d+(?:\s*\(ignored\))?|Deleting\s+file\b.+)\s*$",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    private readonly ILogger _Logger;

    private readonly ProcessRunner _ProcessRunner;

    private readonly AbsolutePath _ProjectRoot;

    private readonly CoqProofSkipFinder _ProofSkipFinder;

    #endregion Fields

    public CoqChecker(
        ILogger logger,
        ProcessRunner processRunner,
        AbsolutePath projectRoot,
        CoqProofSkipFinder proofSkipFinder)
    {
        _Logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _ProcessRunner = processRunner ?? throw new ArgumentNullException(nameof(processRunner));
        _ProjectRoot = projectRoot ?? throw new ArgumentNullException(nameof(projectRoot));
        _ProofSkipFinder = proofSkipFinder ?? throw new ArgumentNullException(nameof(proofSkipFinder));
    }

    /// <summary>
    /// Run the proof check at the configured project root. When the command exits 0 and
    /// <paramref name="targetFileRelativePath"/> is set, scan that file for the first
    /// <c>Admitted.</c> / <c>Abort.</c> outside comments/strings; if found, return
    /// <see cref="CoqCheckType.Failed"/> with a synthetic error at the skip position.
    /// </summary>
    public async Task<CoqCheck> CheckAsync(
        RelativePath? targetFileRelativePath,
        int checkTimeoutSeconds,
        string checkCommand,
        CancellationToken cancellationToken)
    {
        _CheckArguments(checkTimeoutSeconds, checkCommand);

        var shellLine = checkCommand.Trim();

        _Logger.Information(
            "proof_check start: cwd={ProjectRoot} shellCommandLine={ShellCommandLine} checkTimeoutSeconds={CheckTimeoutSeconds}",
            _ProjectRoot.FullPath,
            shellLine,
            checkTimeoutSeconds);

        var psi = _CreatePSI(_ProjectRoot.FullPath, shellLine);
        var run = await _ProcessRunner
            .RunProcessAsync(
                psi,
                TimeSpan.FromSeconds(checkTimeoutSeconds),
                cancellationToken)
            .ConfigureAwait(false);

        if (run.TimedOut)
        {
            return _BuildTimedOutCheck(_ProjectRoot.FullPath, shellLine, checkTimeoutSeconds, run);
        }

        if (run.ExitCode != 0)
        {
            return _BuildFailedCheck(checkTimeoutSeconds, run);
        }

        var proofSkipFailure = _BuildProofSkipFailure(targetFileRelativePath, run, checkTimeoutSeconds);
        if (proofSkipFailure != null)
        {
            return proofSkipFailure;
        }

        return _BuildSuccessCheck(_ProjectRoot.FullPath, shellLine, checkTimeoutSeconds, run);
    }

    #region Private Methods

    private static void _CheckArguments(int checkTimeoutSeconds, string checkCommand)
    {
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
    }

    private static ProcessStartInfo _CreatePSI(string projectRoot, string commandLine)
    {
        var psi = new ProcessStartInfo
        {
            WorkingDirectory = projectRoot,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true
        };
        if (OperatingSystem.IsWindows())
        {
            psi.FileName = "cmd.exe";
            psi.ArgumentList.Add("/c");
            psi.ArgumentList.Add(commandLine);
        }
        else
        {
            psi.FileName = "/bin/sh";
            psi.ArgumentList.Add("-c");
            psi.ArgumentList.Add(commandLine);
        }

        return psi;
    }

    private CoqCheck _BuildTimedOutCheck(
        string projectRoot,
        string shellLine,
        int checkTimeoutSeconds,
        ProcessRunResult run)
    {
        _Logger.Warning(
            "proof_check timed_out: cwd={ProjectRoot} shellCommandLine={ShellCommandLine} checkTimeoutSeconds={CheckTimeoutSeconds} outputLength={OutputLength}",
            projectRoot,
            shellLine,
            checkTimeoutSeconds,
            run.CombinedOutput.Length);

        var timedOutShown = string.IsNullOrWhiteSpace(run.CombinedOutput)
            ? "(check timed out)"
            : _FilterMakeSummaryLines(run.CombinedOutput);
        return new CoqCheck(CoqCheckType.TimedOut, null, timedOutShown, checkTimeoutSeconds);
    }

    private CoqCheck _BuildSuccessCheck(
        string projectRoot,
        string shellLine,
        int checkTimeoutSeconds,
        ProcessRunResult run)
    {
        _Logger.Information(
            "proof_check success: cwd={ProjectRoot} shellCommandLine={ShellCommandLine} checkTimeoutSeconds={CheckTimeoutSeconds} outputLength={OutputLength}",
            projectRoot,
            shellLine,
            checkTimeoutSeconds,
            run.CombinedOutput.Length);

        var successOut = _FilterMakeSummaryLines(run.CombinedOutput);
        return new CoqCheck(CoqCheckType.Success, null, successOut, checkTimeoutSeconds);
    }

    private CoqCheck? _BuildProofSkipFailure(
        RelativePath? targetFileRelativePath,
        ProcessRunResult run,
        int checkTimeoutSeconds)
    {
        if (targetFileRelativePath == null)
        {
            return null;
        }

        var proofSkip = _ProofSkipFinder.FindFirstProofSkip(targetFileRelativePath);
        if (proofSkip == null)
        {
            return null;
        }

        var message = proofSkip.Type == CoqProofSkipType.Abort ? "Abort." : "Admitted.";
        _Logger.Information(
            "proof_check skip_detected: file={File} line={Line} column={Column} type={Type}; reporting as failed.",
            targetFileRelativePath.PosixPath,
            proofSkip.LineOneBased,
            proofSkip.ColumnZeroBased,
            proofSkip.Type);
        var error = new CoqError(
            targetFileRelativePath,
            proofSkip.LineOneBased,
            proofSkip.ColumnZeroBased,
            message);
        var filteredOutput = _FilterMakeSummaryLines(run.CombinedOutput);
        return new CoqCheck(CoqCheckType.Failed, error, filteredOutput, checkTimeoutSeconds);
    }

    private CoqCheck _BuildFailedCheck(int checkTimeoutSeconds, ProcessRunResult run)
    {
        var failedOut = _FilterMakeSummaryLines(run.CombinedOutput);
        var error = _TryExtractFirstCoqError(failedOut, _ProjectRoot);
        return new CoqCheck(CoqCheckType.Failed, error, failedOut, checkTimeoutSeconds);
    }

    /// <summary>
    /// Drops GNU make lines of the form <c>make: *** [path/to/Makefile:line: target] Error N</c> (and <c>make[job]:</c> variants).
    /// Coq errors above them stay; other make messages (e.g. "No rule to make target") are kept.
    /// </summary>
    private static string _FilterMakeSummaryLines(string? makeCombinedOutput)
    {
        if (string.IsNullOrEmpty(makeCombinedOutput))
        {
            return makeCombinedOutput ?? "";
        }

        var normalized = makeCombinedOutput.Replace("\r\n", "\n").Replace('\r', '\n');
        var lines = normalized.Split('\n');
        var kept = new List<string>(lines.Length);
        foreach (var line in lines)
        {
            if (_IsMakeRecursiveErrorEchoLine(line))
            {
                continue;
            }

            kept.Add(line);
        }

        return string.Join(Environment.NewLine, kept).TrimEnd();
    }

    private static bool _IsMakeRecursiveErrorEchoLine(string line)
    {
        return _MakeRecursiveErrorEchoLineRegex.IsMatch(line.Trim());
    }

    /// <summary>
    /// The regex <c>msg</c> group can extend to EOF and include make echo lines; drop them anywhere in the block.
    /// </summary>
    private static string _RemoveMakeEchoLinesFromText(string text)
    {
        if (string.IsNullOrWhiteSpace(text))
        {
            return text;
        }

        var normalized = text.Replace("\r\n", "\n").Replace('\r', '\n');
        var kept = new List<string>();
        foreach (var line in normalized.Split('\n'))
        {
            if (_IsMakeRecursiveErrorEchoLine(line))
            {
                continue;
            }

            kept.Add(line);
        }

        return string.Join(Environment.NewLine, kept).TrimEnd();
    }

    private static CoqError? _TryExtractFirstCoqError(string? combinedOutput, AbsolutePath projectRoot)
    {
        if (string.IsNullOrWhiteSpace(combinedOutput))
        {
            return null;
        }

        var match = _CoqErrorRegex.Match(combinedOutput);
        if (!match.Success)
        {
            return null;
        }

        var file = match.Groups["file"].Value.Trim();
        var lineRaw = match.Groups["line"].Value;
        var colRaw = match.Groups["c1"].Value;
        var msg = _RemoveMakeEchoLinesFromText(match.Groups["msg"].Value.Trim());

        _ = int.TryParse(lineRaw, out var line);
        _ = int.TryParse(colRaw, out var col);

        if (line <= 0)
        {
            line = 1;
        }

        if (col < 0)
        {
            col = 0;
        }

        return new CoqError(
            RelativeFilePath: string.IsNullOrWhiteSpace(file) ? null : new RelativePath(file, projectRoot),
            Line: line,
            Column: col,
            Message: string.IsNullOrWhiteSpace(msg) ? "(no error message)" : msg);
    }

    #endregion Private Methods
}
