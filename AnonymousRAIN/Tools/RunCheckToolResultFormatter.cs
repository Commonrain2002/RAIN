using System.Text;

using ProofAgent.Agent;
using ProofAgent.Coq;

namespace ProofAgent.Tools;

/// <summary>Assembles run_check tool result text from Prompts/RunCheck templates.</summary>
public class RunCheckToolResultFormatter : IRunCheckToolResultFormatter
{
    #region Fields

    private const string _RunCheckTimeoutPath = "RunCheck/Timeout.txt";

    private const string _RunCheckSuccessPath = "RunCheck/Success.txt";

    private const string _RunCheckFailedPath = "RunCheck/Failed.txt";

    private const string _RunCheckFailedRawOutputSectionPath = "RunCheck/FailedRawOutputSection.txt";

    private const string _RunCheckProbeFailureBlockPath = "RunCheck/ProbeFailureBlock.txt";

    private const string _RunCheckUnparsedCoqErrorHintPath = "RunCheck/UnparsedCoqErrorHint.txt";

    private readonly IPromptTextSource _PromptTextSource;

    #endregion Fields

    public RunCheckToolResultFormatter(IPromptTextSource promptTextSource)
    {
        _PromptTextSource = promptTextSource ?? throw new ArgumentNullException(nameof(promptTextSource));
    }

    public string FormatRunCheckFailures(IReadOnlyList<CoqRunCheckFailure> failures)
    {
        ArgumentNullException.ThrowIfNull(failures);

        if (failures.Count == 0)
        {
            return _PromptTextSource.GetText(_RunCheckSuccessPath).TrimEnd();
        }

        var firstFailure = failures[0];
        var primary = _FormatPrimaryResult(
            firstFailure.Check,
            firstFailure.EnvironmentText,
            firstFailure.SourceSnippet);

        if (failures.Count == 1)
        {
            return primary;
        }

        return primary + _FormatAdditionalFailures(failures);
    }

    #region Private Methods

    private string _FormatPrimaryResult(
        CoqCheck check,
        string environmentText,
        string errorSourceSnippet = "")
    {
        if (check.TimedOut)
        {
            var timeoutTemplate = _PromptTextSource.GetText(_RunCheckTimeoutPath);
            return _ReplacePlaceholder(
                timeoutTemplate,
                "{{TimeoutSeconds}}",
                check.TimeoutSeconds.ToString()).TrimEnd();
        }

        if (check.Success)
        {
            return _PromptTextSource.GetText(_RunCheckSuccessPath).TrimEnd();
        }

        return _FormatFailedRunCheckResult(check, environmentText, errorSourceSnippet);
    }

    private string _FormatAdditionalFailures(IReadOnlyList<CoqRunCheckFailure> failures)
    {
        var accumulator = new StringBuilder();
        for (var i = 1; i < failures.Count; i++)
        {
            accumulator.Append(Environment.NewLine);
            accumulator.Append(
                _FormatTripleSections(
                    failures[i].Check,
                    failures[i].EnvironmentText,
                    failures[i].SourceSnippet));
        }

        return accumulator.ToString();
    }

    private string _FormatFailedRunCheckResult(
        CoqCheck check,
        string environmentText,
        string errorSourceSnippet)
    {
        var showsUnparsedCoqErrorPlaceholder = check.Error == null;
        var errorBlock = _BuildCoqErrorMessageSection(check.Error);
        var environmentBlock = string.IsNullOrWhiteSpace(environmentText) ? "(none)" : environmentText.Trim();
        var sourceBlock = string.IsNullOrWhiteSpace(errorSourceSnippet) ? "(none)" : errorSourceSnippet.Trim();
        var rawCheckBlock = showsUnparsedCoqErrorPlaceholder
            ? _ReplacePlaceholder(
                _PromptTextSource.GetText(_RunCheckFailedRawOutputSectionPath),
                "{{RawOutput}}",
                check.RawOutput)
            : "";

        var failedTemplate = _PromptTextSource.GetText(_RunCheckFailedPath);
        var withErrorBlock = _ReplacePlaceholder(failedTemplate, "{{ErrBlock}}", errorBlock);
        var withSource = _ReplacePlaceholder(withErrorBlock, "{{SourceBlock}}", sourceBlock);
        var withEnvironmentBlock = _ReplacePlaceholder(withSource, "{{EnvBlock}}", environmentBlock);
        return _ReplacePlaceholder(withEnvironmentBlock, "{{RawCheckBlock}}", rawCheckBlock).TrimEnd();
    }

    private string _FormatTripleSections(
        CoqCheck probeFailed,
        string environmentText,
        string frozenSourceSnippet)
    {
        var showsUnparsedCoqErrorPlaceholder = probeFailed.Error == null;
        var errorBlock = _BuildCoqErrorMessageSection(probeFailed.Error);

        var environmentBlock = string.IsNullOrWhiteSpace(environmentText) ? "(none)" : environmentText.Trim();
        var sourceBlock = string.IsNullOrWhiteSpace(frozenSourceSnippet) ? "(none)" : frozenSourceSnippet.Trim();

        var rawCheckBlock = showsUnparsedCoqErrorPlaceholder
            ? _ReplacePlaceholder(
                _PromptTextSource.GetText(_RunCheckFailedRawOutputSectionPath),
                "{{RawOutput}}",
                probeFailed.RawOutput)
            : "";

        var probeTemplate = _PromptTextSource.GetText(_RunCheckProbeFailureBlockPath);
        var withErrorBlock = _ReplacePlaceholder(probeTemplate, "{{ErrBlock}}", errorBlock);
        var withSource = _ReplacePlaceholder(withErrorBlock, "{{SourceBlock}}", sourceBlock);
        var withEnvironmentBlock = _ReplacePlaceholder(withSource, "{{EnvBlock}}", environmentBlock);
        return _ReplacePlaceholder(withEnvironmentBlock, "{{RawCheckBlock}}", rawCheckBlock);
    }

    private string _BuildCoqErrorMessageSection(CoqError? error)
    {
        return error?.ToString()
            ?? _PromptTextSource.GetText(_RunCheckUnparsedCoqErrorHintPath).TrimEnd();
    }

    private string _ReplacePlaceholder(string text, string placeholder, string value)
    {
        return text.Replace(placeholder, value, StringComparison.Ordinal);
    }

    #endregion Private Methods
}
