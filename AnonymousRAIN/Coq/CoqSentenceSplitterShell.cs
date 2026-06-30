using System.Diagnostics;
using System.Text.Json;
using ProofAgent.Tools;
using Serilog;

namespace ProofAgent.Coq;

/// <summary>
/// Parses sentence JSON from a configured external shell script (CoqStoq-compatible output).
/// Full invocation and JSON contract: <c>Docs/parse_sentence_contract.md</c>.
/// </summary>
public class CoqSentenceSplitterShell : ICoqSentenceSplitter
{
    #region Fields

    private const int _LogOutputPreviewMaxChars = 12000;

    private readonly string _ParseSentenceShellLine;

    private readonly int _TimeoutSeconds;

    private readonly ILogger _Logger;

    private readonly ProcessRunner _ProcessRunner;

    private readonly ProjectFileSystem _FileSystem;

    #endregion Fields

    public CoqSentenceSplitterShell(
        ProjectFileSystem fileSystem,
        string parseSentenceShellLine,
        int timeoutSeconds,
        ILogger logger,
        ProcessRunner processRunner)
    {
        _FileSystem = fileSystem ?? throw new ArgumentNullException(nameof(fileSystem));

        if (string.IsNullOrWhiteSpace(parseSentenceShellLine))
        {
            throw new ArgumentException("parseSentenceShellLine must not be empty.", nameof(parseSentenceShellLine));
        }

        if (timeoutSeconds <= 0)
        {
            throw new ArgumentOutOfRangeException(
                nameof(timeoutSeconds),
                "timeoutSeconds must be a positive integer.");
        }

        _ParseSentenceShellLine = parseSentenceShellLine.Trim();
        _TimeoutSeconds = timeoutSeconds;
        _Logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _ProcessRunner = processRunner ?? throw new ArgumentNullException(nameof(processRunner));
    }

    public async Task<IReadOnlyList<CoqSentence>> SplitAsync(RelativePath relativeCoqFilePath, CancellationToken cancellationToken)
    {
        if (relativeCoqFilePath == null)
        {
            throw new ArgumentNullException(nameof(relativeCoqFilePath));
        }

        if (!_FileSystem.Exists(relativeCoqFilePath))
        {
            _Logger.Warning("parse-sentence-script: file does not exist: {Path}", relativeCoqFilePath.PosixPath);
            return Array.Empty<CoqSentence>();
        }

        var relativePosix = relativeCoqFilePath.PosixPath;
        var shellLine = _BuildShellCommandLine(relativePosix);
        var projectRootFullPath = _FileSystem.Root.FullPath;
        _Logger.Information(
            "parse-sentence-script: cwd={Cwd} shellCommand={Command}",
            projectRootFullPath,
            shellLine);

        var psi = _CreateShellStartInfo(projectRootFullPath, shellLine);

        ProcessRunResult runResult;
        try
        {
            runResult = await _ProcessRunner
                .RunProcessAsync(psi, TimeSpan.FromSeconds(_TimeoutSeconds), cancellationToken)
                .ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception ex)
        {
            _Logger.Warning(ex, "parse-sentence-script: failed to run splitter process.");
            return Array.Empty<CoqSentence>();
        }

        if (runResult.TimedOut)
        {
            return _HandleSplitTimedOut(runResult);
        }

        if (runResult.ExitCode != 0)
        {
            return _HandleSplitNonZeroExit(runResult);
        }

        return _TryDeserializeResponse(runResult.CombinedOutput ?? "");
    }

    #region Private Methods

    private IReadOnlyList<CoqSentence> _HandleSplitTimedOut(ProcessRunResult runResult)
    {
        _Logger.Warning(
            "parse-sentence-script timed out after {Seconds}s (cwd={Cwd}). Combined output ({Length} chars):\n{Preview}",
            _TimeoutSeconds,
            _FileSystem.Root.FullPath,
            runResult.CombinedOutput.Length,
            _FormatMultilineOutputForLog(runResult.CombinedOutput));
        return Array.Empty<CoqSentence>();
    }

    private IReadOnlyList<CoqSentence> _HandleSplitNonZeroExit(ProcessRunResult runResult)
    {
        _Logger.Warning(
            "parse-sentence-script exited {Exit}. Combined output ({Length} chars):\n{Preview}",
            runResult.ExitCode,
            runResult.CombinedOutput.Length,
            _FormatMultilineOutputForLog(runResult.CombinedOutput));
        return Array.Empty<CoqSentence>();
    }

    private IReadOnlyList<CoqSentence> _TryDeserializeResponse(string combinedOutput)
    {
        if (string.IsNullOrWhiteSpace(combinedOutput))
        {
            _Logger.Warning("parse-sentence-script produced empty combined stdout/stderr after exit 0.");
            return Array.Empty<CoqSentence>();
        }

        var trimmed = combinedOutput.Trim();
        try
        {
            var envelope = JsonSerializer.Deserialize<CoqParseSentenceScriptJsonEnvelope>(
                trimmed,
                new JsonSerializerOptions
                {
                    PropertyNameCaseInsensitive = true,
                    ReadCommentHandling = JsonCommentHandling.Skip,
                    AllowTrailingCommas = true
                });

            if (envelope?.Sentences == null || envelope.Sentences.Count == 0)
            {
                _Logger.Warning(
                    "parse-sentence-script JSON has no sentences (parsed ok but empty). Raw output ({Length} chars):\n{Preview}",
                    trimmed.Length,
                    _FormatMultilineOutputForLog(trimmed));
                return Array.Empty<CoqSentence>();
            }

            _Logger.Information(
                "parse-sentence-script: deserialized {SentenceCount} sentence(s).",
                envelope.Sentences.Count);
            return envelope.Sentences;
        }
        catch (JsonException ex)
        {
            _Logger.Warning(
                ex,
                "parse-sentence-script JSON parse failed. Raw output ({Length} chars):\n{Preview}",
                trimmed.Length,
                _FormatMultilineOutputForLog(trimmed));
            return Array.Empty<CoqSentence>();
        }
    }

    private static string _FormatMultilineOutputForLog(string? text)
    {
        if (string.IsNullOrEmpty(text))
        {
            return "(empty)";
        }

        var normalized = text.Replace("\r\n", "\n", StringComparison.Ordinal);
        if (normalized.Length <= _LogOutputPreviewMaxChars)
        {
            return normalized;
        }

        var head = _LogOutputPreviewMaxChars / 2;
        var tail = _LogOutputPreviewMaxChars - head;
        return normalized[..head] + "\n...(truncated " + (normalized.Length - _LogOutputPreviewMaxChars) + " chars)...\n" + normalized[^tail..];
    }

    private string _BuildShellCommandLine(string relativeCoqFilePathPosix)
    {
        return $"{_ParseSentenceShellLine} {_ShellQuotePathForHost(relativeCoqFilePathPosix)}";
    }

    private static string _ShellQuotePathForHost(string path)
    {
        if (OperatingSystem.IsWindows())
        {
            return "\"" + path.Replace("\"", "\\\"", StringComparison.Ordinal) + "\"";
        }

        return "'" + path.Replace("'", "'\\''", StringComparison.Ordinal) + "'";
    }

    private static ProcessStartInfo _CreateShellStartInfo(string projectRoot, string commandLine)
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

    #endregion Private Methods
}