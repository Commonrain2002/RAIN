using System.Reflection;
using ProofAgent.Coq;
using ProofAgent.Tools;
using Serilog;
using Xunit;

namespace ProofAgent.Tests;

public class CoqProofBulletIterationPlannerTests
{
    [Fact]
    public async Task TryPlanEdit_CommentsErroredBulletSpine_LinePreservingAdmitsOnSamePhysicalLine()
    {
        var lines = new[]
        {
            "Lemma u : True.",
            "Proof.",
            "-",
            "failnow.",
            "-",
            "idtac.",
        };

        var classByIndex = new[]
        {
            "VtStartProof(GuaranteesOpacity,[u])",
            "VtProofStep(bullet)",
            "VtProofStep(bullet)",
            "VtProofStep",
            "VtProofStep(bullet)",
            "VtProofStep",
        };

        var errorMessage = PathTests.Error("Any.v", 4, 0, "boom");

        ILogger logger = TestInjectedLogger.CreateFatalOnly();
        var (iterationPlannerUnderTestInstance, relativeVPath, tempDir) = await _CreatePlannerWithTempFileAsync(
            logger,
            lines,
            classByIndex);
        try
        {
            var editOutcome = await iterationPlannerUnderTestInstance.PlanEditAsync(
                relativeVPath,
                lines,
                errorMessage,
                CancellationToken.None);

            Assert.True(editOutcome.Succeeded, editOutcome.FailureReason);
            Assert.NotEmpty(editOutcome.CommentEditLines);

            Assert.Equal(lines.Length, editOutcome.CommentEditLines.Length);

            Assert.Equal(lines[0], editOutcome.CommentEditLines[0]);

            Assert.Equal(lines[1], editOutcome.CommentEditLines[1]);

            Assert.Equal(lines[2], editOutcome.CommentEditLines[2]);

            Assert.Equal("(*failnow.*) all: admit.", editOutcome.CommentEditLines[3]);

            Assert.Equal(lines[4], editOutcome.CommentEditLines[4]);

            Assert.Equal(lines[5], editOutcome.CommentEditLines[5]);
        }
        finally
        {
            _TryDeleteTempDirForPath(tempDir);
        }
    }

    [Fact]
    public async Task TryPlanEdit_FocusSubgoalBrace_ClosingBracePopsOnlyFocusNotAssertOpen()
    {
        var lines = new[]
        {
            "Lemma u : True.",
            "Proof.",
            "-",
            "assert (H : True).",
            "{",
            "2: {",
            "idtac.",
            "}",
            "}",
            "fail.",
        };

        var classByIndex = new[]
        {
            "VtStartProof(GuaranteesOpacity,[u])",
            "VtProofStep(bullet)",
            "VtProofStep(bullet)",
            "VtProofStep",
            "VtProofStep(bullet)",
            "VtProofStep(bullet)",
            "VtProofStep",
            "VtProofStep(curly)",
            "VtProofStep(curly)",
            "VtProofStep",
        };

        var sentencesRecordList = CoqLineAlignedSentenceTestHelper.SentencesLineAlignedOnePerPhysicalLine(lines, classByIndex);
        var errorMessage = PathTests.Error("Any.v", 10, 0, "boom");

        ILogger logger = TestInjectedLogger.CreateFatalOnly();
        var (iterationPlannerUnderTestInstance, relativeVPath, tempDir) = await _CreatePlannerWithTempFileAsync(
            logger,
            lines,
            classByIndex);
        try
        {
            var editOutcome = await iterationPlannerUnderTestInstance.PlanEditAsync(
                relativeVPath,
                lines,
                errorMessage,
                CancellationToken.None);

            Assert.True(editOutcome.Succeeded, editOutcome.FailureReason);
        }
        finally
        {
            _TryDeleteTempDirForPath(tempDir);
        }
    }

    [Fact]
    public async Task TryPlanEdit_ClosingBraceBeforeError_FailsWhenWouldPopRootBrace()
    {
        var lines = new[]
        {
            "Lemma u : True.",
            "Proof.",
            "}",
            "fail.",
        };

        var classByIndex = new[]
        {
            "VtStartProof(GuaranteesOpacity,[u])",
            "VtProofStep(bullet)",
            "VtProofStep(curly)",
            "VtProofStep",
        };

        var errorMessage = PathTests.Error("Any.v", 4, 0, "boom");

        ILogger logger = TestInjectedLogger.CreateFatalOnly();
        var (iterationPlannerUnderTestInstance, relativeVPath, tempDir) = await _CreatePlannerWithTempFileAsync(
            logger,
            lines,
            classByIndex);
        try
        {
            var editOutcome = await iterationPlannerUnderTestInstance.PlanEditAsync(
                relativeVPath,
                lines,
                errorMessage,
                CancellationToken.None);

            Assert.False(editOutcome.Succeeded);
            Assert.Contains("stack[0]", editOutcome.FailureReason, StringComparison.Ordinal);
        }
        finally
        {
            _TryDeleteTempDirForPath(tempDir);
        }
    }

    private static async Task<(CoqProofBulletIterationPlanner Planner, RelativePath RelativeVPath, string TempDir)> _CreatePlannerWithTempFileAsync(
        ILogger logger,
        string[] lines,
        string[] classificationByAscendingIndexExclusive)
    {
        var sentencesRecordList = CoqLineAlignedSentenceTestHelper.SentencesLineAlignedOnePerPhysicalLine(
            lines,
            classificationByAscendingIndexExclusive);
        var tempDir = Path.Combine(Path.GetTempPath(), "ProofAgentPlanner_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempDir);
        await File.WriteAllLinesAsync(Path.Combine(tempDir, "A.v"), lines).ConfigureAwait(false);
        var sentenceSplitter = new FixedCoqSentenceSplitter(sentencesRecordList);
        var sentenceAnalyzer = new CoqSentenceAnalyzer(logger, sentenceSplitter);
        var bulletAnalyzer = new CoqBulletAnalyzer(logger, sentenceSplitter, sentenceAnalyzer);
        return (new CoqProofBulletIterationPlanner(logger, bulletAnalyzer, sentenceSplitter), new RelativePath("A.v", new AbsolutePath(tempDir)), tempDir);
    }

    private static void _TryDeleteTempDirForPath(string tempDir)
    {
        try
        {
            var dir = tempDir;
            if (dir != null && Directory.Exists(dir))
            {
                Directory.Delete(dir, recursive: true);
            }
        }
        catch
        {
            // best-effort cleanup
        }
    }

    [Fact]
    public void BuildMutatedLinesWithSentenceSpanComments_ExclusiveEndColumnLeavesTrailingBraceOutsideComment()
    {
        var physicalLineHeld =
            "        rewrite H1. simpl. auto. }";
        var coreTextHeld = "rewrite H1. simpl. auto.";
        var startColumnInclusiveZeroBased = 8;
        var exclusiveEndColumnZeroBased = startColumnInclusiveZeroBased + coreTextHeld.Length;

        var ordered = new List<CoqSentence>
        {
            new CoqSentence
            {
                Index = 0,
                StartLineOneBased = 1,
                StartColumnZeroBased = startColumnInclusiveZeroBased,
                EndLineOneBased = 1,
                EndColumnZeroBased = exclusiveEndColumnZeroBased,
                Text = coreTextHeld,
                Classification = CoqSentenceClassification.Step
            }
        };

        var workingLines = new[] { physicalLineHeld };
        var buildMethod = typeof(CoqProofBulletIterationPlanner).GetMethod(
            "_BuildCommentEditLines",
            BindingFlags.Static | BindingFlags.NonPublic);
        Assert.NotNull(buildMethod);
        var invokeArgs = new object?[] { workingLines, ordered, 0, 0, null };
        var applied = (bool)buildMethod!.Invoke(null, invokeArgs)!;
        Assert.True(applied);
        var rebuiltLines = (string[])invokeArgs[4]!;

        Assert.Single(rebuiltLines);
        Assert.Contains("(*rewrite H1. simpl. auto.*) all: admit.", rebuiltLines[0], StringComparison.Ordinal);
        Assert.Contains("*) all: admit. }", rebuiltLines[0], StringComparison.Ordinal);
        Assert.DoesNotContain("}*)", rebuiltLines[0], StringComparison.Ordinal);
    }
}
