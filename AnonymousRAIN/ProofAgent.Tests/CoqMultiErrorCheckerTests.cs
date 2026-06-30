using ProofAgent.Coq;
using ProofAgent.Tests.Fakes;
using ProofAgent.Tools;
using Serilog;
using Xunit;

namespace ProofAgent.Tests;

public class CoqMultiErrorCheckerTests
{
    private const int _CheckTimeoutSeconds = 60;

    [Fact]
    public async Task RunMultiErrorCheckAsync_FirstCheckSuccess_ReturnsEmpty()
    {
        var tempDir = _NewTempProjectDir();
        var (checker, _) = _CreateChecker(
            tempDir,
            new QueueCoqProjectChecker(new[]
            {
                new CoqCheck(CoqCheckType.Success, null, "", _CheckTimeoutSeconds)
            }),
            extraErrorCount: 2);
        try
        {
            var failures = await checker.RunMultiErrorCheckAsync(CancellationToken.None);
            Assert.Empty(failures);
        }
        finally
        {
            _TryDeleteTempDir(tempDir);
        }
    }

    [Fact]
    public async Task RunMultiErrorCheckAsync_FirstCheckTimedOut_ReturnsSingleFailure()
    {
        var tempDir = _NewTempProjectDir();
        var timedOut = new CoqCheck(CoqCheckType.TimedOut, null, "hang", _CheckTimeoutSeconds);
        var (multiErrorChecker, _) = _CreateChecker(
            tempDir,
            new QueueCoqProjectChecker(new[] { timedOut }),
            extraErrorCount: 2);
        try
        {
            var failures = await multiErrorChecker.RunMultiErrorCheckAsync(CancellationToken.None);
            Assert.Single(failures);
            Assert.Same(timedOut, failures[0].Check);
            Assert.Equal("", failures[0].EnvironmentText);
        }
        finally
        {
            _TryDeleteTempDir(tempDir);
        }
    }

    [Fact]
    public async Task RunMultiErrorCheckAsync_FirstCheckFailedWithoutParseableError_ReturnsSingleFailure()
    {
        var tempDir = _NewTempProjectDir();
        var failedWithoutError = new CoqCheck(CoqCheckType.Failed, null, "make failed", _CheckTimeoutSeconds);
        var (multiErrorChecker, _) = _CreateChecker(
            tempDir,
            new QueueCoqProjectChecker(new[] { failedWithoutError }),
            extraErrorCount: 2);
        try
        {
            var failures = await multiErrorChecker.RunMultiErrorCheckAsync(CancellationToken.None);
            Assert.Single(failures);
            Assert.Same(failedWithoutError, failures[0].Check);
        }
        finally
        {
            _TryDeleteTempDir(tempDir);
        }
    }

    [Fact]
    public async Task RunMultiErrorCheckAsync_ExtraErrorCountZero_ReturnsOnlyInitialFailure()
    {
        var tempDir = _NewTempProjectDir();
        var firstError = PathTests.Error("A.v", 4, 0, "boom", tempDir);
        var firstFailed = new CoqCheck(CoqCheckType.Failed, firstError, "raw", _CheckTimeoutSeconds);
        var (multiErrorChecker, _) = _CreateChecker(
            tempDir,
            new QueueCoqProjectChecker(new[] { firstFailed }),
            extraErrorCount: 0);
        try
        {
            var failures = await multiErrorChecker.RunMultiErrorCheckAsync(CancellationToken.None);
            Assert.Single(failures);
            Assert.Equal("env-fixed", failures[0].EnvironmentText);
        }
        finally
        {
            _TryDeleteTempDir(tempDir);
        }
    }

    [Fact]
    public async Task RunMultiErrorCheckAsync_ProbeSuccessAfterComment_DoesNotAddSecondFailureAndRestoresFile()
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
        var tempDir = await _NewTempProjectDirWithLinesAsync(lines);
        var firstError = PathTests.Error("A.v", 4, 0, "boom", tempDir);
        var firstFailed = new CoqCheck(CoqCheckType.Failed, firstError, "raw1", _CheckTimeoutSeconds);
        var probeSuccess = new CoqCheck(CoqCheckType.Success, null, "raw2", _CheckTimeoutSeconds);
        var (multiErrorChecker, originalText) = await _CreateCheckerWithPlannerAsync(
            tempDir,
            new QueueCoqProjectChecker(new[] { firstFailed, probeSuccess }),
            lines,
            classByIndex,
            extraErrorCount: 2);
        try
        {
            var failures = await multiErrorChecker.RunMultiErrorCheckAsync(CancellationToken.None);
            Assert.Single(failures);
            Assert.Same(firstFailed, failures[0].Check);
            var afterText = await File.ReadAllTextAsync(Path.Combine(tempDir, "A.v"));
            Assert.Equal(originalText, afterText);
        }
        finally
        {
            _TryDeleteTempDir(tempDir);
        }
    }

    [Fact]
    public async Task RunMultiErrorCheckAsync_AfterProbeNoSuchGoalOnNextIteration_RemovesLastFailure()
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
        var tempDir = await _NewTempProjectDirWithLinesAsync(lines);
        var firstError = PathTests.Error("A.v", 4, 0, "boom", tempDir);
        var probeError = PathTests.Error("A.v", 4, 0, "Error: No such goal.", tempDir);
        var firstFailed = new CoqCheck(CoqCheckType.Failed, firstError, "raw1", _CheckTimeoutSeconds);
        var probeFailed = new CoqCheck(CoqCheckType.Failed, probeError, "raw2", _CheckTimeoutSeconds);
        var (multiErrorChecker, _) = await _CreateCheckerWithPlannerAsync(
            tempDir,
            new QueueCoqProjectChecker(new[] { firstFailed, probeFailed }),
            lines,
            classByIndex,
            extraErrorCount: 2);
        try
        {
            var failures = await multiErrorChecker.RunMultiErrorCheckAsync(CancellationToken.None);
            Assert.Single(failures);
            Assert.Same(firstFailed, failures[0].Check);
        }
        finally
        {
            _TryDeleteTempDir(tempDir);
        }
    }

    [Fact]
    public async Task RunMultiErrorCheckAsync_FirstErrorIsNoSuchGoal_DoesNotEnterCommentLoop()
    {
        var tempDir = _NewTempProjectDir();
        var noSuchGoalError = PathTests.Error("A.v", 1, 0, "Error: No such goal.", tempDir);
        var firstFailed = new CoqCheck(CoqCheckType.Failed, noSuchGoalError, "raw", _CheckTimeoutSeconds);
        var (multiErrorChecker, _) = _CreateChecker(
            tempDir,
            new QueueCoqProjectChecker(new[] { firstFailed }),
            extraErrorCount: 2);
        try
        {
            var failures = await multiErrorChecker.RunMultiErrorCheckAsync(CancellationToken.None);
            Assert.Single(failures);
        }
        finally
        {
            _TryDeleteTempDir(tempDir);
        }
    }

    [Fact]
    public async Task RunMultiErrorCheckAsync_ExtraErrorCountTwo_ThreeChecksAccumulatesThreeFailures()
    {
        var (lines, classByIndex) = _BulletCommentProofLines();
        var tempDir = await _NewTempProjectDirWithLinesAsync(lines);
        var errorA = PathTests.Error("A.v", 4, 0, "first error", tempDir);
        var errorB = PathTests.Error("A.v", 4, 0, "second error", tempDir);
        var errorC = PathTests.Error("A.v", 4, 0, "third error", tempDir);
        var checkA = new CoqCheck(CoqCheckType.Failed, errorA, "raw1", _CheckTimeoutSeconds);
        var checkB = new CoqCheck(CoqCheckType.Failed, errorB, "raw2", _CheckTimeoutSeconds);
        var checkC = new CoqCheck(CoqCheckType.Failed, errorC, "raw3", _CheckTimeoutSeconds);
        var (multiErrorChecker, originalText) = await _CreateCheckerWithPlannerAsync(
            tempDir,
            new QueueCoqProjectChecker(new[] { checkA, checkB, checkC }),
            lines,
            classByIndex,
            extraErrorCount: 2);
        try
        {
            var failures = await multiErrorChecker.RunMultiErrorCheckAsync(CancellationToken.None);
            Assert.Equal(3, failures.Count);
            Assert.Same(checkA, failures[0].Check);
            Assert.Same(checkB, failures[1].Check);
            Assert.Same(checkC, failures[2].Check);
            var afterText = await File.ReadAllTextAsync(Path.Combine(tempDir, "A.v"));
            Assert.Equal(originalText, afterText);
        }
        finally
        {
            _TryDeleteTempDir(tempDir);
        }
    }

    [Fact]
    public async Task RunMultiErrorCheckAsync_ExtraErrorCountOne_TwoChecksAccumulatesTwoFailures()
    {
        var (lines, classByIndex) = _BulletCommentProofLines();
        var tempDir = await _NewTempProjectDirWithLinesAsync(lines);
        var errorA = PathTests.Error("A.v", 4, 0, "first error", tempDir);
        var errorB = PathTests.Error("A.v", 4, 0, "second error", tempDir);
        var checkA = new CoqCheck(CoqCheckType.Failed, errorA, "raw1", _CheckTimeoutSeconds);
        var checkB = new CoqCheck(CoqCheckType.Failed, errorB, "raw2", _CheckTimeoutSeconds);
        var (multiErrorChecker, _) = await _CreateCheckerWithPlannerAsync(
            tempDir,
            new QueueCoqProjectChecker(new[] { checkA, checkB }),
            lines,
            classByIndex,
            extraErrorCount: 1);
        try
        {
            var failures = await multiErrorChecker.RunMultiErrorCheckAsync(CancellationToken.None);
            Assert.Equal(2, failures.Count);
            Assert.Same(checkA, failures[0].Check);
            Assert.Same(checkB, failures[1].Check);
        }
        finally
        {
            _TryDeleteTempDir(tempDir);
        }
    }

    [Fact]
    public async Task RunMultiErrorCheckAsync_CommentWriteFailsAfterFirstFailure_StopsWithSingleFailure()
    {
        var tempDir = _NewTempProjectDir();
        var firstError = PathTests.Error("A.v", 4, 0, "boom", tempDir);
        var firstFailed = new CoqCheck(CoqCheckType.Failed, firstError, "raw", _CheckTimeoutSeconds);
        var queueChecker = new QueueCoqProjectChecker(new[] { firstFailed });
        var (multiErrorChecker, _) = _CreateChecker(tempDir, queueChecker, extraErrorCount: 2);
        try
        {
            var failures = await multiErrorChecker.RunMultiErrorCheckAsync(CancellationToken.None);
            Assert.Single(failures);
            Assert.Same(firstFailed, failures[0].Check);
        }
        finally
        {
            _TryDeleteTempDir(tempDir);
        }
    }

    [Fact]
    public async Task RunMultiErrorCheckAsync_ProbeIncompleteProofMessage_StopsWithoutAddingSecondFailure()
    {
        var (lines, classByIndex) = _BulletCommentProofLines();
        var tempDir = await _NewTempProjectDirWithLinesAsync(lines);
        var firstError = PathTests.Error("A.v", 4, 0, "boom", tempDir);
        var probeError = PathTests.Error(
            "A.v",
            4,
            0,
            "Attempt to save an incomplete proof",
            tempDir);
        var firstFailed = new CoqCheck(CoqCheckType.Failed, firstError, "raw1", _CheckTimeoutSeconds);
        var probeFailed = new CoqCheck(CoqCheckType.Failed, probeError, "raw2", _CheckTimeoutSeconds);
        var (multiErrorChecker, _) = await _CreateCheckerWithPlannerAsync(
            tempDir,
            new QueueCoqProjectChecker(new[] { firstFailed, probeFailed }),
            lines,
            classByIndex,
            extraErrorCount: 2);
        try
        {
            var failures = await multiErrorChecker.RunMultiErrorCheckAsync(CancellationToken.None);
            Assert.Single(failures);
            Assert.Same(firstFailed, failures[0].Check);
        }
        finally
        {
            _TryDeleteTempDir(tempDir);
        }
    }

    private static (string[] Lines, string[] ClassByIndex) _BulletCommentProofLines()
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
        return (lines, classByIndex);
    }

    private static string _NewTempProjectDir()
    {
        var tempDir = Path.Combine(Path.GetTempPath(), "ProofAgentMultiErr_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempDir);
        File.WriteAllText(Path.Combine(tempDir, "A.v"), "Lemma u : True.\nQed.\n");
        return tempDir;
    }

    private static async Task<string> _NewTempProjectDirWithLinesAsync(string[] lines)
    {
        var tempDir = Path.Combine(Path.GetTempPath(), "ProofAgentMultiErr_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempDir);
        await File.WriteAllLinesAsync(Path.Combine(tempDir, "A.v"), lines).ConfigureAwait(false);
        return tempDir;
    }

    private static (CoqMultiErrorChecker Checker, string TempDir) _CreateChecker(
        string tempDir,
        ICoqChecker projectChecker,
        int extraErrorCount)
    {
        var logger = TestInjectedLogger.CreateFatalOnly();
        var fileSystem = new ProjectFileSystem(tempDir);
        var targetCoqFileRelativePath = new RelativePath("A.v", fileSystem.Root);
        var sentenceSplitter = new FixedCoqSentenceSplitter(Array.Empty<CoqSentence>());
        var sentenceAnalyzer = new CoqSentenceAnalyzer(logger, sentenceSplitter);
        var bulletAnalyzer = new CoqBulletAnalyzer(logger, sentenceSplitter, sentenceAnalyzer);
        var planner = new CoqProofBulletIterationPlanner(logger, bulletAnalyzer, sentenceSplitter);
        var environment = new FixedCoqEnvironmentTextSource("env-fixed");
        var checker = new CoqMultiErrorChecker(
            logger,
            projectChecker,
            environment,
            targetCoqFileRelativePath,
            fileSystem,
            planner,
            _CheckTimeoutSeconds,
            checkCommand: "make",
            extraErrorCount);
        return (checker, tempDir);
    }

    private static async Task<(CoqMultiErrorChecker Checker, string OriginalFileText)> _CreateCheckerWithPlannerAsync(
        string tempDir,
        ICoqChecker projectChecker,
        string[] lines,
        string[] classificationByAscendingIndexExclusive,
        int extraErrorCount)
    {
        var sentencesRecordList = CoqLineAlignedSentenceTestHelper.SentencesLineAlignedOnePerPhysicalLine(
            lines,
            classificationByAscendingIndexExclusive);
        var filePath = Path.Combine(tempDir, "A.v");
        var originalText = await File.ReadAllTextAsync(filePath).ConfigureAwait(false);
        var logger = TestInjectedLogger.CreateFatalOnly();
        var fileSystem = new ProjectFileSystem(tempDir);
        var targetCoqFileRelativePath = new RelativePath("A.v", fileSystem.Root);
        var sentenceSplitter = new FixedCoqSentenceSplitter(sentencesRecordList);
        var sentenceAnalyzer = new CoqSentenceAnalyzer(logger, sentenceSplitter);
        var bulletAnalyzer = new CoqBulletAnalyzer(logger, sentenceSplitter, sentenceAnalyzer);
        var planner = new CoqProofBulletIterationPlanner(logger, bulletAnalyzer, sentenceSplitter);
        var environment = new FixedCoqEnvironmentTextSource("env-fixed");
        var checker = new CoqMultiErrorChecker(
            logger,
            projectChecker,
            environment,
            targetCoqFileRelativePath,
            fileSystem,
            planner,
            _CheckTimeoutSeconds,
            checkCommand: "make",
            extraErrorCount);
        return (checker, originalText);
    }

    private static void _TryDeleteTempDir(string tempDir)
    {
        try
        {
            if (Directory.Exists(tempDir))
            {
                Directory.Delete(tempDir, recursive: true);
            }
        }
        catch
        {
            // best-effort cleanup
        }
    }
}
