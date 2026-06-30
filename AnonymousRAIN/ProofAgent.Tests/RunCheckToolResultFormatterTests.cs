using ProofAgent.Agent;
using ProofAgent.Coq;
using ProofAgent.Tools;
using Xunit;

namespace ProofAgent.Tests;

public class RunCheckToolResultFormatterTests
{
    [Fact]
    public void FormatToolResult_Failed_IncludesErrorEnv_ExcludesRaw()
    {
        var formatter = PromptTestFixtures.CreateRunCheckToolResultFormatter(TestInjectedLogger.CreateFatalOnly());
        var err = PathTests.Error("A.v", 2, 0, "bad");
        var check = new CoqCheck(CoqCheckType.Failed, err, "RAW_OUT", 30);
        var msg = _InvokeFormatToolResult(formatter, check, "EnvText", "snippet line");

        Assert.Contains("proof check failed", msg, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("## Coq Error Message", msg, StringComparison.Ordinal);
        Assert.Contains("## Error line around", msg, StringComparison.Ordinal);
        Assert.Contains("snippet line", msg, StringComparison.Ordinal);
        Assert.Contains("## Environment before error", msg, StringComparison.Ordinal);
        Assert.Contains("EnvText", msg, StringComparison.Ordinal);
        Assert.DoesNotContain("## Full command output", msg, StringComparison.Ordinal);
        Assert.DoesNotContain("RAW_OUT", msg, StringComparison.Ordinal);
    }

    [Fact]
    public void FormatToolResult_Failed_ParseFailed_IncludesFullRawCheckOutput()
    {
        var formatter = PromptTestFixtures.CreateRunCheckToolResultFormatter(TestInjectedLogger.CreateFatalOnly());
        var longRaw = "coqc: " + new string('z', 200);
        var check = new CoqCheck(CoqCheckType.Failed, null, longRaw, 30);
        var msg = _InvokeFormatToolResult(formatter, check, "", "");

        Assert.Contains("proof check failed", msg, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Could not parse a standard Coq Error block", msg, StringComparison.Ordinal);
        Assert.Contains("## Full command output", msg, StringComparison.Ordinal);
        Assert.Contains(longRaw, msg, StringComparison.Ordinal);
    }

    [Fact]
    public void FormatToolResult_Success_ExcludesRaw()
    {
        var formatter = PromptTestFixtures.CreateRunCheckToolResultFormatter(TestInjectedLogger.CreateFatalOnly());
        var check = new CoqCheck(CoqCheckType.Success, null, "some raw output", 30);
        var msg = _InvokeFormatToolResult(formatter, check, "", "");

        Assert.Contains("proof check succeeded", msg, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("some raw output", msg, StringComparison.Ordinal);
    }

    [Fact]
    public void FormatRunCheckFailures_EmptyList_ReportsSuccess()
    {
        var formatter = PromptTestFixtures.CreateRunCheckToolResultFormatter(TestInjectedLogger.CreateFatalOnly());
        var full = formatter.FormatRunCheckFailures(Array.Empty<CoqRunCheckFailure>());

        Assert.Contains("proof check succeeded", full, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void FormatRunCheckFailures_AdmittedFailure_ReportsFailedWithSyntheticError()
    {
        var formatter = PromptTestFixtures.CreateRunCheckToolResultFormatter(TestInjectedLogger.CreateFatalOnly());
        var admittedError = PathTests.Error("A.v", 4, 0, "Admitted.");
        var check = new CoqCheck(CoqCheckType.Failed, admittedError, "", 30);
        var failures = new List<CoqRunCheckFailure>
        {
            new CoqRunCheckFailure
            {
                Check = check,
                EnvironmentText = "Goal\n---\nTrue",
                SourceSnippet = "4: Admitted."
            }
        };

        var full = formatter.FormatRunCheckFailures(failures);

        Assert.Contains("proof check failed", full, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Admitted.", full, StringComparison.Ordinal);
        Assert.Contains("Goal", full, StringComparison.Ordinal);
        Assert.DoesNotContain("# Additional Coq error", full, StringComparison.Ordinal);
    }

    [Fact]
    public void FormatRunCheckFailures_SecondFailure_IncludesAdditionalSectionsAndHeading()
    {
        var formatter = PromptTestFixtures.CreateRunCheckToolResultFormatter(TestInjectedLogger.CreateFatalOnly());
        var firstCheck = new CoqCheck(
            CoqCheckType.Failed,
            PathTests.Error("A.v", 1, 0, "first"),
            "",
            30);
        var failedProbe = new CoqCheck(
            CoqCheckType.Failed,
            PathTests.Error("SimpleTest/Z.v", 3, 0, "boom"),
            "",
            30);
        var failures = new List<CoqRunCheckFailure>
        {
            new CoqRunCheckFailure
            {
                Check = firstCheck,
                EnvironmentText = "first env",
                SourceSnippet = "first line"
            },
            new CoqRunCheckFailure
            {
                Check = failedProbe,
                EnvironmentText = "(env text)",
                SourceSnippet = "tactical line."
            }
        };

        var full = formatter.FormatRunCheckFailures(failures);

        Assert.Contains("proof check failed", full, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("# Additional Coq error", full, StringComparison.Ordinal);
        Assert.Contains("boom", full, StringComparison.Ordinal);
        Assert.Contains("tactical line.", full, StringComparison.Ordinal);
        Assert.Contains("(env text)", full, StringComparison.Ordinal);
    }

    [Fact]
    public void FormatRunCheckFailures_SingleFailure_ExcludesAdditionalHeading()
    {
        var formatter = PromptTestFixtures.CreateRunCheckToolResultFormatter(TestInjectedLogger.CreateFatalOnly());
        var check = new CoqCheck(
            CoqCheckType.Failed,
            PathTests.Error("A.v", 2, 0, "bad"),
            "",
            30);
        var failures = new List<CoqRunCheckFailure>
        {
            new CoqRunCheckFailure
            {
                Check = check,
                EnvironmentText = "EnvText",
                SourceSnippet = "snippet"
            }
        };

        var full = formatter.FormatRunCheckFailures(failures);

        Assert.DoesNotContain("# Additional Coq error", full, StringComparison.Ordinal);
    }

    [Fact]
    public void FormatRunCheckFailures_SecondFailureUnparsed_IncludesRawOutputSection()
    {
        var formatter = PromptTestFixtures.CreateRunCheckToolResultFormatter(TestInjectedLogger.CreateFatalOnly());
        var firstCheck = new CoqCheck(
            CoqCheckType.Failed,
            PathTests.Error("A.v", 1, 0, "first"),
            "",
            30);
        var failedProbeUnparsed = new CoqCheck(
            CoqCheckType.Failed,
            null,
            "Makefile: hello",
            20);
        var failures = new List<CoqRunCheckFailure>
        {
            new CoqRunCheckFailure { Check = firstCheck, EnvironmentText = "", SourceSnippet = "" },
            new CoqRunCheckFailure { Check = failedProbeUnparsed, EnvironmentText = "", SourceSnippet = "" }
        };

        var full = formatter.FormatRunCheckFailures(failures);

        Assert.Contains("## Full command output", full, StringComparison.Ordinal);
        Assert.Contains("Makefile: hello", full, StringComparison.Ordinal);
    }

    private static string _InvokeFormatToolResult(
        RunCheckToolResultFormatter formatter,
        CoqCheck check,
        string environmentText,
        string errorSourceSnippet)
    {
        return ReflectionTestAccess.InvokeInstanceNonPublic<string>(
            formatter,
            "_FormatPrimaryResult",
            new object?[]
            {
                check,
                environmentText,
                errorSourceSnippet
            })!;
    }
}
